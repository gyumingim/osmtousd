"""멀티카메라 생성속도 벤치: NCAM대 카메라 = 한 step에 NCAM장 동시렌더.
NCAM=1 vs NCAM=3 각각 K장 생성, 렌더루프 wall-time 측정 → images/sec 비교.
같은 K장이라도 NCAM=3은 step·드론배치·정착 오버헤드를 1/3로 분산(레이트레이싱은 동일)."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1280, "height": 720})
import os, time, math, random, numpy as np, carb
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf, Sdf
import omni.usd, omni.replicator.core as rep

W, H = 1280, 720
NCAM = int(os.environ.get("NCAM", "3"))
KIMG = int(os.environ.get("KIMG", "18"))          # 총 생성 장수(NCAM의 배수)
SUB = int(os.environ.get("SUB", "4"))             # rt_subframes
CITY = "/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.usd"
HDRI_DIR = "/home/karma/OSMtoUSD/assets/hdri"
MODEL = "/home/karma/OSMtoUSD/assets/drones/iris_quad.usd"
OUT = "/home/karma/OSMtoUSD/poc_city_render/multicam_shots"
os.makedirs(OUT, exist_ok=True)
HAP = 36.0
random.seed(7)
def focal_of(h): return (HAP/2)/math.tan(math.radians(h)/2)
s = carb.settings.get_settings(); s.set("/rtx/rendermode", "RaytracedLighting")

omni.usd.get_context().open_stage(CITY)
for _ in range(15): app.update()
stage = omni.usd.get_context().get_stage()
up = UsdGeom.GetStageUpAxis(stage)
ui = 1 if up == 'Y' else 2; g1, g2 = ([0, 2] if up == 'Y' else [0, 1])
_wup = Gf.Vec3d(0, 1, 0) if up == 'Y' else Gf.Vec3d(0, 0, 1)
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange(); mn, mx = rng.GetMin(), rng.GetMax()
c1 = (mn[g1]+mx[g1])/2; c2 = (mn[g2]+mx[g2])/2; top = mx[ui]; ground = mn[ui]
gd = ((mx[g1]-mn[g1])**2+(mx[g2]-mn[g2])**2)**0.5

HDRIS = sorted(f for f in os.listdir(HDRI_DIR) if f.endswith(".hdr"))
dome = UsdLux.DomeLight.Define(stage, "/Sky"); dome.CreateIntensityAttr(550)
dome.CreateTextureFileAttr(os.path.join(HDRI_DIR, HDRIS[0]))
UsdGeom.Xformable(dome.GetPrim()).AddRotateYOp().Set(60)

drone = UsdGeom.Xform.Define(stage, "/Drone"); dpos = UsdGeom.Xformable(drone).AddTranslateOp()
rs = UsdGeom.Xform.Define(stage, "/Drone/rs"); rsx = UsdGeom.Xformable(rs); sop = rsx.AddScaleOp(); rop = rsx.AddRotateXYZOp()
cen = UsdGeom.Xform.Define(stage, "/Drone/rs/centered"); cop = UsdGeom.Xformable(cen).AddTranslateOp()
_src = Usd.Stage.Open(MODEL); _flat = _src.Flatten()
_sdp = _src.GetDefaultPrim().GetPath() if _src.GetDefaultPrim() else next(iter(_src.GetPseudoRoot().GetChildren())).GetPath()
stage.DefinePrim("/Drone/rs/centered/geom", "Xform")
Sdf.CopySpec(_flat, _sdp, stage.GetRootLayer(), Sdf.Path("/Drone/rs/centered/geom"))
for _ in range(120): app.update()
mb = cache.ComputeWorldBound(stage.GetPrimAtPath("/Drone/rs/centered")).ComputeAlignedRange()
mmn, mmx = mb.GetMin(), mb.GetMax(); mc = [(mmn[i]+mmx[i])/2 for i in range(3)]; mext = max(mmx[i]-mmn[i] for i in range(3))
cop.Set(Gf.Vec3d(-mc[0], -mc[1], -mc[2])); S_world = gd*0.05; sop.Set(Gf.Vec3f(S_world/mext, S_world/mext, S_world/mext))
UPX = -90.0 if up == 'Y' else 0.0

def basis(eye, Lp):
    f = Gf.Vec3d(*Lp) - eye; f = f/f.GetLength()
    r = Gf.Cross(f, _wup); r = r/r.GetLength(); u = Gf.Cross(r, f); return f, r, u

cams = []
for i in range(NCAM):
    cp = UsdGeom.Camera.Define(stage, f"/Cam{i}")
    cp.CreateFocalLengthAttr(focal_of(60)); cp.CreateHorizontalApertureAttr(HAP)
    cp.CreateClippingRangeAttr(Gf.Vec2f(0.05, 1e8))
    mop = UsdGeom.Xformable(cp).MakeMatrixXform()
    rp = rep.create.render_product(f"/Cam{i}", (W, H))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb"); rgb.attach([rp])
    cams.append((mop, rgb))

def place_cam(mop, eye, f, r, u):
    mop.Set(Gf.Matrix4d(r[0], r[1], r[2], 0, u[0], u[1], u[2], 0,
                        -f[0], -f[1], -f[2], 0, eye[0], eye[1], eye[2], 1))

def new_drone_pos():
    P = [0, 0, 0]; az = random.uniform(0, 360); Rr = gd*random.uniform(0.0, 0.15)
    P[g1] = c1+Rr*math.cos(math.radians(az)); P[g2] = c2+Rr*math.sin(math.radians(az)); P[ui] = top*random.uniform(0.3, 0.8)
    return P

def cam_looking_at(P):
    az = random.uniform(0, 360); Rr = gd*random.uniform(0.06, 0.28)
    e = [0, 0, 0]; e[g1] = P[g1]+Rr*math.cos(math.radians(az)); e[g2] = P[g2]+Rr*math.sin(math.radians(az))
    e[ui] = max(ground, 0)+top*random.uniform(0.0, 0.12)
    eye = Gf.Vec3d(*e); f, r, u = basis(eye, Gf.Vec3d(*P)); return eye, f, r, u

# warmup (제외)
P = new_drone_pos(); dpos.Set(Gf.Vec3d(*P)); rop.Set(Gf.Vec3f(UPX, 0, 0))
for (mop, rgb) in cams:
    e, f, r, u = cam_looking_at(P); place_cam(mop, e, f, r, u)
for _ in range(5): app.update()
rep.orchestrator.step(rt_subframes=SUB); app.update()

# ---- 벤치(렌더루프만 타이밍) ----
iters = KIMG // NCAM
t0 = time.time(); saved = 0
for it in range(iters):
    P = new_drone_pos()
    dpos.Set(Gf.Vec3d(*P)); rop.Set(Gf.Vec3f(UPX+random.uniform(-25, 25), random.uniform(0, 360), random.uniform(-25, 25)))
    for (mop, rgb) in cams:
        e, f, r, u = cam_looking_at(P); place_cam(mop, e, f, r, u)
    for _ in range(3): app.update()
    rep.orchestrator.step(rt_subframes=SUB); app.update()
    for ci, (mop, rgb) in enumerate(cams):
        arr = np.array(rgb.get_data()[:, :, :3])
        if it < 2:   # 처음 2반복만 저장(보여주기용)
            Image.fromarray(arr).save(f"{OUT}/n{NCAM}_it{it}_c{ci}.jpg"); saved += 1
el = time.time() - t0
print(f"RESULT NCAM={NCAM} KIMG={KIMG} iters={iters} sub={SUB} | {el:.2f}s 총 | {el/KIMG*1000:.0f}ms/장 | {KIMG/el:.2f} img/s | saved={saved}", flush=True)
app.close()
