"""Isaac Sim GUI 뷰어 v2 — Path Tracing 자동 설정 + 검은화면 픽스.
- 렌더모드를 코드에서 PathTracing으로 (carb /rtx/rendermode)
- 전용 카메라 /PoC_Cam 만들어 뷰포트에 지정(기본 persp 덮어쓰기 문제 회피)
- Y-up/cm 좌표 대응 look-at 행렬(헤드리스에서 검증된 프레이밍과 동일 좌표)
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": False, "width": 1600, "height": 900})

import sys
import carb
from pxr import UsdGeom, UsdLux, Usd, Gf
import omni.usd
import omni.kit.viewport.utility as vpu

def log(m): print(m, flush=True)

# ── 렌더모드: Path Tracing ────────────────────────────────────────────────────
s = carb.settings.get_settings()
s.set("/rtx/rendermode", "PathTracing")
s.set("/rtx/pathtracing/totalSpp", 128)        # 누적 목표 샘플
try: s.set_bool("/rtx/pathtracing/optixDenoiser/enabled", True)
except Exception: pass
log("렌더모드=PathTracing 설정")

USD = "/home/karma/OSMtoUSD/assets/city_buildings/city_buildings.usd"
ctx = omni.usd.get_context()
ctx.open_stage(USD)
for _ in range(40):
    app.update()
stage = ctx.get_stage()
up = UsdGeom.GetStageUpAxis(stage)

# ── 조명 ──────────────────────────────────────────────────────────────────────
sun = UsdLux.DistantLight.Define(stage, "/PoC_Sun")
sun.CreateIntensityAttr(3000.0); sun.CreateAngleAttr(0.53)
UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-50.0, 0.0, 35.0))
sky = UsdLux.DomeLight.Define(stage, "/PoC_Sky")
sky.CreateIntensityAttr(1000.0); sky.CreateColorAttr(Gf.Vec3f(0.7, 0.82, 1.0))

# ── bbox → look-at 행렬 ───────────────────────────────────────────────────────
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                          [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax()
ui = 1 if up == 'Y' else 2
g1, g2 = ([0, 2] if up == 'Y' else [0, 1])
def V(a, b, u):
    p = [0.0, 0.0, 0.0]; p[g1] = a; p[g2] = b; p[ui] = u; return Gf.Vec3d(*p)
c1 = (mn[g1]+mx[g1])/2; c2 = (mn[g2]+mx[g2])/2
gd = ((mx[g1]-mn[g1])**2 + (mx[g2]-mn[g2])**2) ** 0.5

eye = V(c1, c2 - gd*0.9, gd*0.4)
tgt = V(c1, c2, gd*0.02)
wup = Gf.Vec3d(0, 1, 0) if up == 'Y' else Gf.Vec3d(0, 0, 1)
fwd = (tgt - eye).GetNormalized()
right = Gf.Cross(fwd, wup).GetNormalized()
upv = Gf.Cross(right, fwd)
m = Gf.Matrix4d()
m.SetRow(0, Gf.Vec4d(right[0], right[1], right[2], 0))
m.SetRow(1, Gf.Vec4d(upv[0], upv[1], upv[2], 0))
m.SetRow(2, Gf.Vec4d(-fwd[0], -fwd[1], -fwd[2], 0))
m.SetRow(3, Gf.Vec4d(eye[0], eye[1], eye[2], 1))
log(f"up={up} eye={tuple(round(v,1) for v in eye)} tgt={tuple(round(v,1) for v in tgt)} gd={gd:.0f}")

# ── 전용 카메라 + 뷰포트 지정 ─────────────────────────────────────────────────
cam = UsdGeom.Camera.Define(stage, "/PoC_Cam")
cam.CreateFocalLengthAttr(18.0)
cam.CreateClippingRangeAttr(Gf.Vec2f(10.0, 5_000_000.0))
xf = UsdGeom.Xformable(cam.GetPrim()); xf.ClearXformOpOrder(); xf.AddTransformOp().Set(m)

vp = vpu.get_active_viewport()
if vp:
    vp.camera_path = "/PoC_Cam"
log(">>> VIEWER READY — Path Tracing. 카메라=/PoC_Cam. (창 닫으면 종료)")

frame = 0
while app.is_running():
    app.update()
    if frame < 120 and vp:        # 초기 몇 초간 카메라 재적용(뷰포트 덮어쓰기 방지)
        vp.camera_path = "/PoC_Cam"
    frame += 1
app.close()
