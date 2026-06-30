"""실사용 시점 프리뷰: 환경(공항/숲) + 하늘 드론 + 지상→하늘 카메라 = 학습이미지가 어떻게 보일지."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1024, "height": 640})
import os, math, random, numpy as np, carb
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf, Sdf
import omni.usd, omni.replicator.core as rep

HDRI = "/home/karma/OSMtoUSD/assets/hdri/sky_kloofendal_43d_clear_ps.hdr"
DRONE = "/home/karma/OSMtoUSD/assets/drones/iris_quad.usd"
OUT = "/home/karma/OSMtoUSD/poc_city_render/env_scene_shots"
os.makedirs(OUT, exist_ok=True)
W, H = 1024, 640
HAP = 36.0
random.seed(3)
def focal_of(h): return (HAP/2)/math.tan(math.radians(h)/2)
s = carb.settings.get_settings(); s.set("/rtx/rendermode", "RaytracedLighting")
# env: (usd, n_instances=숲이면 여러그루)
ENVS = {"airport": ("/home/karma/OSMtoUSD/assets/env_airport/airport.usd", 1),
        "forest":  ("/home/karma/OSMtoUSD/assets/env_forest/tree.usd", 7)}

def basis(eye, Lp, wup):
    f = Gf.Vec3d(*Lp) - eye; f = f/f.GetLength()
    r = Gf.Cross(f, wup); r = r/r.GetLength(); u = Gf.Cross(r, f); return f, r, u

for name, (usd, ninst) in ENVS.items():
    omni.usd.get_context().new_stage()
    for _ in range(8): app.update()
    stage = omni.usd.get_context().get_stage()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    wup = Gf.Vec3d(0, 1, 0)
    dome = UsdLux.DomeLight.Define(stage, "/Sky"); dome.CreateIntensityAttr(600)
    dome.CreateTextureFileAttr(HDRI); UsdGeom.Xformable(dome.GetPrim()).AddRotateYOp().Set(40)
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    # 환경 1개 참조로 bbox 파악
    e0 = UsdGeom.Xform.Define(stage, "/EnvProbe"); e0.GetPrim().GetReferences().AddReference(usd)
    for _ in range(40): app.update()
    rng = cache.ComputeWorldBound(e0.GetPrim()).ComputeAlignedRange(); mn, mx = rng.GetMin(), rng.GetMax()
    E = max((mx[i]-mn[i]) for i in range(3)) or 1.0
    baseY = mn[1]
    stage.RemovePrim("/EnvProbe")
    # 배치: 숲=여러그루 줄세움, 공항=중앙 1개. 지면 y=0 기준
    insts = []
    if ninst == 1:
        insts = [(0.0, 0.0, 0.0)]
    else:
        for i in range(ninst):
            insts.append((random.uniform(-E*1.6, E*1.6), 0.0, random.uniform(-E*0.5, E*1.2)))
    for i, (px, _, pz) in enumerate(insts):
        ep = UsdGeom.Xform.Define(stage, f"/Env{i}"); epx = UsdGeom.Xformable(ep)
        epx.AddTranslateOp().Set(Gf.Vec3d(px, -baseY, pz)); epx.AddRotateYOp().Set(random.uniform(0, 360))
        ep.GetPrim().GetReferences().AddReference(usd)
    # 드론(inline) 하늘에
    drone = UsdGeom.Xform.Define(stage, "/Drone"); dpos = UsdGeom.Xformable(drone).AddTranslateOp()
    rs = UsdGeom.Xform.Define(stage, "/Drone/rs"); rsx = UsdGeom.Xformable(rs); sop = rsx.AddScaleOp(); rop = rsx.AddRotateXYZOp()
    cen = UsdGeom.Xform.Define(stage, "/Drone/rs/centered"); cop = UsdGeom.Xformable(cen).AddTranslateOp()
    _src = Usd.Stage.Open(DRONE); _flat = _src.Flatten()
    _sdp = _src.GetDefaultPrim().GetPath() if _src.GetDefaultPrim() else next(iter(_src.GetPseudoRoot().GetChildren())).GetPath()
    stage.DefinePrim("/Drone/rs/centered/geom", "Xform")
    Sdf.CopySpec(_flat, _sdp, stage.GetRootLayer(), Sdf.Path("/Drone/rs/centered/geom"))
    for _ in range(80): app.update()
    mb = cache.ComputeWorldBound(stage.GetPrimAtPath("/Drone/rs/centered")).ComputeAlignedRange()
    mmn, mmx = mb.GetMin(), mb.GetMax(); mc = [(mmn[i]+mmx[i])/2 for i in range(3)]; mext = max(mmx[i]-mmn[i] for i in range(3))
    cop.Set(Gf.Vec3d(-mc[0], -mc[1], -mc[2]))
    # 카메라
    camprim = UsdGeom.Camera.Define(stage, "/Cam"); camprim.CreateFocalLengthAttr(focal_of(60))
    camprim.CreateHorizontalApertureAttr(HAP); camprim.CreateClippingRangeAttr(Gf.Vec2f(0.05, 1e9))
    mop = UsdGeom.Xformable(camprim).MakeMatrixXform()
    rp = rep.create.render_product("/Cam", (W, H))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb"); rgb.attach([rp])
    for shot in range(2):
        # ★시선 앵커 = 환경 윗부분(환경이 하단 프레임에 들어오게). 드론은 그 위 하늘에.
        look = Gf.Vec3d(random.uniform(-E*0.2, E*0.2), E*0.45, random.uniform(-E*0.2, E*0.2))
        drone_pos = Gf.Vec3d(look[0]+random.uniform(-E*0.35, E*0.35), E*random.uniform(0.7, 1.0), look[2]+random.uniform(-E*0.35, E*0.35))
        dpos.Set(drone_pos)
        rop.Set(Gf.Vec3f(-90+random.uniform(-20, 20), random.uniform(0, 360), random.uniform(-20, 20)))
        # 카메라: 지상 낮은높이, 환경 가까이(하단 프레임 채움)
        cam_az = random.uniform(0, 360); cr = E*random.uniform(0.55, 0.85)
        eye = Gf.Vec3d(cr*math.cos(math.radians(cam_az)), E*0.05, cr*math.sin(math.radians(cam_az)))
        # 드론까지 거리 → 드론 크기(프레임 ~5%)
        dist = (drone_pos - eye).GetLength(); S_world = dist*0.05; sop.Set(Gf.Vec3f(S_world/mext, S_world/mext, S_world/mext))
        f, r, u = basis(eye, look, wup)   # ★드론 아닌 환경윗부분 조준 → 환경 하단+드론 상단
        mop.Set(Gf.Matrix4d(r[0], r[1], r[2], 0, u[0], u[1], u[2], 0, -f[0], -f[1], -f[2], 0, eye[0], eye[1], eye[2], 1))
        for _ in range(6): app.update()
        rep.orchestrator.step(rt_subframes=24); app.update()
        arr = np.array(rgb.get_data()[:, :, :3])
        Image.fromarray(arr).save(f"{OUT}/{name}_{shot}.png")
        print(f"[{name}_{shot}] E={E:.1f} mean={arr.mean():.1f}", flush=True)

print("SCENE_DONE", flush=True)
app.close()
