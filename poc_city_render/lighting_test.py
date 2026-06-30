"""조명 비교: 같은 숲+드론 씬을 3가지 조명으로 렌더.
v0=순수IBL(현재,역광실루엣) / v1=돔+강한키 / v2=돔밝게(전방향)+키+약한front필 → 역광제거."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1024, "height": 640})
import os, math, random, numpy as np, carb
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf, Sdf
import omni.usd, omni.replicator.core as rep

HDRI = "/home/karma/OSMtoUSD/assets/hdri/sky_kloofendal_43d_clear_ps.hdr"
DRONE = "/home/karma/OSMtoUSD/assets/drones/iris_quad.usd"
TREE = "/home/karma/OSMtoUSD/assets/env_forest/tree.usd"
OUT = "/home/karma/OSMtoUSD/poc_city_render/light_shots"
os.makedirs(OUT, exist_ok=True)
W, H = 1024, 640
HAP = 36.0
random.seed(11)
def focal_of(h): return (HAP/2)/math.tan(math.radians(h)/2)
s = carb.settings.get_settings(); s.set("/rtx/rendermode", "RaytracedLighting")

omni.usd.get_context().new_stage()
for _ in range(8): app.update()
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y); wup = Gf.Vec3d(0, 1, 0)
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
# 나무 bbox
e0 = UsdGeom.Xform.Define(stage, "/Probe"); e0.GetPrim().GetReferences().AddReference(TREE)
for _ in range(40): app.update()
rng = cache.ComputeWorldBound(e0.GetPrim()).ComputeAlignedRange(); mn, mx = rng.GetMin(), rng.GetMax()
E = max((mx[i]-mn[i]) for i in range(3)) or 1.0; baseY = mn[1]; stage.RemovePrim("/Probe")
# 나무 7그루
for i in range(7):
    px = random.uniform(-E*1.6, E*1.6); pz = random.uniform(-E*0.3, E*1.2)
    ep = UsdGeom.Xform.Define(stage, f"/Tree{i}"); epx = UsdGeom.Xformable(ep)
    epx.AddTranslateOp().Set(Gf.Vec3d(px, -baseY, pz)); epx.AddRotateYOp().Set(random.uniform(0, 360))
    ep.GetPrim().GetReferences().AddReference(TREE)
# 드론
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

def basis(eye, Lp):
    f = Gf.Vec3d(*Lp) - eye; f = f/f.GetLength()
    r = Gf.Cross(f, wup); r = r/r.GetLength(); u = Gf.Cross(r, f); return f, r, u

# 카메라/드론 고정 (역광 상황: 카메라가 태양쪽 봄)
look = Gf.Vec3d(0, E*0.45, E*0.3)
drone_pos = Gf.Vec3d(E*0.1, E*0.85, E*0.3); dpos.Set(drone_pos)
rop.Set(Gf.Vec3f(-90, 30, 0))
eye = Gf.Vec3d(0, E*0.05, -E*0.7)
dist = (drone_pos - eye).GetLength(); S_world = dist*0.05; sop.Set(Gf.Vec3f(S_world/mext, S_world/mext, S_world/mext))
cf, cr, cu = basis(eye, look)
camprim = UsdGeom.Camera.Define(stage, "/Cam"); camprim.CreateFocalLengthAttr(focal_of(60))
camprim.CreateHorizontalApertureAttr(HAP); camprim.CreateClippingRangeAttr(Gf.Vec2f(0.05, 1e9))
mop = UsdGeom.Xformable(camprim).MakeMatrixXform()
mop.Set(Gf.Matrix4d(cr[0], cr[1], cr[2], 0, cu[0], cu[1], cu[2], 0, -cf[0], -cf[1], -cf[2], 0, eye[0], eye[1], eye[2], 1))
rp = rep.create.render_product("/Cam", (W, H))
rgb = rep.AnnotatorRegistry.get_annotator("rgb"); rgb.attach([rp])

dome = UsdLux.DomeLight.Define(stage, "/Sky"); dome.CreateTextureFileAttr(HDRI)
UsdGeom.Xformable(dome.GetPrim()).AddRotateYOp().Set(40)

def orient_light(prim, Ldir):
    """라이트 emit(-Z)이 Ldir 향하게 행렬 세팅."""
    Z = -Ldir; Z = Z/Z.GetLength()
    up = Gf.Vec3d(0, 1, 0) if abs(Z[1]) < 0.95 else Gf.Vec3d(1, 0, 0)
    X = Gf.Cross(up, Z); X = X/X.GetLength(); Y = Gf.Cross(Z, X)
    UsdGeom.Xformable(prim).MakeMatrixXform().Set(
        Gf.Matrix4d(X[0], X[1], X[2], 0, Y[0], Y[1], Y[2], 0, Z[0], Z[1], Z[2], 0, 0, 0, 0, 1))

# key: 위-앞에서 내려오는 강한 빛(태양). 카메라 앞쪽(+f 방향)에서 와서 나무 앞면 비춤
keydir = Gf.Vec3d(cf[0]*0.5, -0.8, cf[2]*0.5)   # 아래+카메라전방 → 나무 앞면 조명
filldir = Gf.Vec3d(cf[0], -0.2, cf[2])           # 거의 정면(카메라쪽)에서 약하게

def render_save(tag):
    for _ in range(6): app.update()
    rep.orchestrator.step(rt_subframes=28); app.update()
    arr = np.array(rgb.get_data()[:, :, :3])
    Image.fromarray(arr).save(f"{OUT}/{tag}.png")
    print(f"[{tag}] mean={arr.mean():.1f}", flush=True)
    return arr.mean()

def clear_lights():
    for p in ("/Key", "/Fill"):
        if stage.GetPrimAtPath(p): stage.RemovePrim(p)

# v0: 순수 IBL (현재)
dome.GetIntensityAttr().Set(600) if dome.GetIntensityAttr() else dome.CreateIntensityAttr(600)
clear_lights(); render_save("v0_ibl")
# v1: 돔 + 강한 키
key = UsdLux.DistantLight.Define(stage, "/Key"); key.CreateIntensityAttr(3000); key.CreateAngleAttr(1.0)
orient_light(key.GetPrim(), keydir)
render_save("v1_dome_key")
# v2: 돔 밝게(전방향 채움) + 키 + 약한 front 필
dome.GetIntensityAttr().Set(1300)
fill = UsdLux.DistantLight.Define(stage, "/Fill"); fill.CreateIntensityAttr(1500); fill.CreateAngleAttr(3.0)
orient_light(fill.GetPrim(), filldir)
render_save("v2_allfill_key")

print("LIGHT_DONE", flush=True)
app.close()
