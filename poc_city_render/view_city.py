"""Isaac Sim GUI 뷰어 — 변환된 city_buildings.usd를 창으로 띄워 사용자가 직접 본다.
조명 추가 + 시작 카메라를 건물 쪽으로 프레이밍(Y-up/cm 대응). 창 닫으면 종료.
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": False, "width": 1600, "height": 900})

from pxr import UsdGeom, UsdLux, Usd, Gf
import omni.usd

USD = "/home/karma/OSMtoUSD/assets/city_buildings/city_buildings.usd"
ctx = omni.usd.get_context()
ctx.open_stage(USD)
for _ in range(40):
    app.update()
stage = ctx.get_stage()
up = UsdGeom.GetStageUpAxis(stage)

# 조명(USD엔 없음)
sun = UsdLux.DistantLight.Define(stage, "/PoC_Sun")
sun.CreateIntensityAttr(3000.0); sun.CreateAngleAttr(0.53)
UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-50.0, 0.0, 35.0))
sky = UsdLux.DomeLight.Define(stage, "/PoC_Sky")
sky.CreateIntensityAttr(1000.0); sky.CreateColorAttr(Gf.Vec3f(0.7, 0.82, 1.0))

# bbox 기준 시작 카메라
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
world_up = Gf.Vec3d(0, 1, 0) if up == 'Y' else Gf.Vec3d(0, 0, 1)
fwd = (tgt - eye).GetNormalized()
right = Gf.Cross(fwd, world_up).GetNormalized()
upv = Gf.Cross(right, fwd)
m = Gf.Matrix4d()
m.SetRow(0, Gf.Vec4d(right[0], right[1], right[2], 0))
m.SetRow(1, Gf.Vec4d(upv[0], upv[1], upv[2], 0))
m.SetRow(2, Gf.Vec4d(-fwd[0], -fwd[1], -fwd[2], 0))
m.SetRow(3, Gf.Vec4d(eye[0], eye[1], eye[2], 1))

persp = stage.GetPrimAtPath("/OmniverseKit_Persp")
if persp and persp.IsValid():
    xf = UsdGeom.Xformable(persp)
    xf.ClearXformOpOrder()
    xf.AddTransformOp().Set(m)
    UsdGeom.Camera(persp).GetClippingRangeAttr().Set(Gf.Vec2f(10.0, 5_000_000.0))

print(">>> VIEWER READY — Isaac Sim 창에서 도시를 보세요. (창 닫으면 종료)")
while app.is_running():
    app.update()
app.close()
