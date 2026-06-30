"""eXplora 단독 검증 — 정면/측면/평면/3-4 깔끔하게, 중립 배경."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1280, "height": 1280})
import os
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf
import omni.usd
import omni.replicator.core as rep

USD = "/home/karma/OSMtoUSD/assets/explora_src/explora.usd"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
def log(m): print(m, flush=True); open(os.path.join(OUT,"run_solo.log"),"a").write(str(m)+"\n")
open(os.path.join(OUT,"run_solo.log"),"w").close()

omni.usd.get_context().open_stage(USD)
for _ in range(15): app.update()
stage = omni.usd.get_context().get_stage()
log(f"upAxis={UsdGeom.GetStageUpAxis(stage)}")

sun = UsdLux.DistantLight.Define(stage, "/L_Sun"); sun.CreateIntensityAttr(2500.0)
UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-35, 25, 15))
dome = UsdLux.DomeLight.Define(stage, "/L_Sky"); dome.CreateIntensityAttr(1200.0)
dome.CreateColorAttr(Gf.Vec3f(0.85, 0.86, 0.9))

cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax()
C = Gf.Vec3d((mn[0]+mx[0])/2, (mn[1]+mx[1])/2, (mn[2]+mx[2])/2)
R = (Gf.Vec3d(*mx) - Gf.Vec3d(*mn)).GetLength()/2
log(f"bbox min={tuple(round(v,1) for v in mn)} max={tuple(round(v,1) for v in mx)}")
log(f"치수: X(폭)={mx[0]-mn[0]:.0f} Y={mx[1]-mn[1]:.0f} Z(길이)={mx[2]-mn[2]:.0f}")

# Y=두께(up), X=날개폭, Z=길이 가정. 약간씩 오프셋해 짐벌 회피
views = [
    ("planform", Gf.Vec3d(0.12, 1.0, 0.12)),   # 평면(날개 형상)
    ("front",    Gf.Vec3d(0.1, 0.18, 1.0)),    # 정면(노즈)
    ("side",     Gf.Vec3d(1.0, 0.18, 0.1)),    # 측면(윙팁)
    ("threeq",   Gf.Vec3d(0.8, 0.45, 0.8)),    # 3/4
]
for name, d in views:
    pos = C + d.GetNormalized()*(R*2.2)
    cam = rep.create.camera(position=(pos[0],pos[1],pos[2]), look_at=(C[0],C[1],C[2]), focal_length=50.0)
    rp = rep.create.render_product(cam, (1280,1280))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb"); rgb.attach([rp])
    for _ in range(10): app.update()
    rep.orchestrator.step(rt_subframes=24); app.update()
    data = rgb.get_data()
    if data is not None and len(data)>0:
        Image.fromarray(data[:,:,:3]).save(os.path.join(OUT, f"solo_{name}.png")); log(f"저장: solo_{name}.png")
    rgb.detach()
log("=== 완료 ===")
app.close()
