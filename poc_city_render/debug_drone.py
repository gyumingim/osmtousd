"""드론 프록시 진단: 월드 bbox 확인 + 코앞 클로즈업 렌더."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1280, "height": 1280})
import os
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf, Vt
import omni.usd
import omni.replicator.core as rep

USD = "/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.usd"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
def log(m): print(m, flush=True); open(os.path.join(OUT,"run_debug.log"),"a").write(str(m)+"\n")
open(os.path.join(OUT,"run_debug.log"),"w").close()

omni.usd.get_context().open_stage(USD)
for _ in range(15): app.update()
stage = omni.usd.get_context().get_stage()
up = UsdGeom.GetStageUpAxis(stage)

sun = UsdLux.DistantLight.Define(stage, "/PoC_Sun")
sun.CreateIntensityAttr(4000.0)
dome = UsdLux.DomeLight.Define(stage, "/PoC_Sky"); dome.CreateIntensityAttr(1500.0)

cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax()
ui = 1 if up=='Y' else 2
g1, g2 = ([0,2] if up=='Y' else [0,1])
def V(a,b,u):
    p=[0.0,0.0,0.0]; p[g1]=a; p[g2]=b; p[ui]=u; return tuple(p)
c1=(mn[g1]+mx[g1])/2; c2=(mn[g2]+mx[g2])/2; top=mx[ui]
gd=((mx[g1]-mn[g1])**2+(mx[g2]-mn[g2])**2)**0.5

# 드론 빌드(실제와 동일)
def cube(path, sx, sy, sz):
    c=UsdGeom.Cube.Define(stage, path)
    UsdGeom.Xformable(c).AddScaleOp().Set(Gf.Vec3f(sx,sy,sz))
    c.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(0.9,0.1,0.1)]))  # 빨강(눈에 띄게)
def cube_at(path, sx,sy,sz, tx,ty,tz):
    c=UsdGeom.Cube.Define(stage, path)
    xf=UsdGeom.Xformable(c); xf.AddScaleOp().Set(Gf.Vec3f(sx,sy,sz)); xf.AddTranslateOp().Set(Gf.Vec3d(tx,ty,tz))
    c.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(0.9,0.1,0.1)]))

S=gd*0.018
P=V(c1, c2, top*1.15)
drone=UsdGeom.Xform.Define(stage,"/Drone"); dxf=UsdGeom.Xformable(drone)
dxf.AddRotateYOp().Set(25.0)
if up=='Y': dxf.AddRotateXOp().Set(-90.0)
dxf.AddTranslateOp().Set(Gf.Vec3d(*P))
cube("/Drone/body", S*0.45,S*0.45,S*0.16)
cube("/Drone/arm_x", S*1.0,S*0.07,S*0.05)
cube("/Drone/arm_y", S*0.07,S*1.0,S*0.05)
L=S*0.85
for nm,tx,ty in [("r0",L,0),("r1",-L,0),("r2",0,L),("r3",0,-L)]:
    cube_at(f"/Drone/{nm}", S*0.3,S*0.3,S*0.04, tx,ty,S*0.08)

app.update(); app.update()
# 드론 월드 bbox
drng = cache.ComputeWorldBound(stage.GetPrimAtPath("/Drone")).ComputeAlignedRange()
dmn, dmx = drng.GetMin(), drng.GetMax()
log(f"P(목표 위치)={tuple(round(v,1) for v in P)}  S={S:.2f}")
log(f"/Drone 월드 bbox min={tuple(round(v,1) for v in dmn)} max={tuple(round(v,1) for v in dmx)}")
log(f"드론 자식 수: {len(list(stage.GetPrimAtPath('/Drone').GetChildren()))}")
log(f"body prim valid: {stage.GetPrimAtPath('/Drone/body').IsValid()}")

# 코앞 클로즈업: P에서 g2로 -8S, 위로 3S
campos = V(P[g1], P[g2]-S*8, P[ui]+S*3)
cam = rep.create.camera(position=campos, look_at=P, focal_length=35.0)
rp = rep.create.render_product(cam, (1280,1280))
rgb = rep.AnnotatorRegistry.get_annotator("rgb"); rgb.attach([rp])
for _ in range(12): app.update()
rep.orchestrator.step(rt_subframes=16); app.update()
data = rgb.get_data()
if data is not None and len(data)>0:
    Image.fromarray(data[:,:,:3]).save(os.path.join(OUT,"debug_drone.png")); log("저장: debug_drone.png")
else: log("[경고] RGB 없음")
log("=== 완료 ===")
app.close()
