"""통제 실험: 빈 스테이지 + 큐브 1개를 12번 이동하며 박스 잡히나.
가릴 건물 없음 → 박스가 앞 몇 개만 잡히면 'transform 전파 버그' 확정.
방식 A: dpos.Set (USD 직접쓰기) / 방식 B: XFormPrim.set_world_pose (Fabric)."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 800, "height": 800})
import os, numpy as np
from PIL import Image
from pxr import UsdGeom, UsdLux, Gf, Vt
import omni.usd
import omni.replicator.core as rep

OUT = "/home/karma/OSMtoUSD/poc_city_render"
def log(m): print(m, flush=True); open(OUT+"/run_mintest.log", "a").write(str(m)+"\n")
open(OUT+"/run_mintest.log", "w").close()
MODE = os.environ.get("MOVE_MODE", "usd")   # usd | fabric

omni.usd.get_context().new_stage()
for _ in range(5): app.update()
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
dome = UsdLux.DomeLight.Define(stage, "/Sky"); dome.CreateIntensityAttr(1000.0); dome.CreateColorAttr(Gf.Vec3f(0.5, 0.6, 0.9))
sun = UsdLux.DistantLight.Define(stage, "/Sun"); sun.CreateIntensityAttr(3000.0)

cube = UsdGeom.Cube.Define(stage, "/Drone")
op = UsdGeom.Xformable(cube).AddTranslateOp()
UsdGeom.Xformable(cube).AddScaleOp().Set(Gf.Vec3f(0.5, 0.5, 0.5))
cube.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(0.9, 0.1, 0.1)]))
from isaacsim.core.utils.semantics import add_update_semantics
add_update_semantics(stage.GetPrimAtPath("/Drone"), "drone")

xprim = None
if MODE == "fabric":
    from isaacsim.core.prims import SingleXFormPrim
    xprim = SingleXFormPrim("/Drone")

cam = rep.create.camera(position=(0, -20, 2), look_at=(0, 0, 2), focal_length=35, clipping_range=(0.01, 1e6))
rp = rep.create.render_product(cam, (800, 800))
rgb = rep.AnnotatorRegistry.get_annotator("rgb")
box = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
seg = rep.AnnotatorRegistry.get_annotator("semantic_segmentation", init_params={"colorize": False})
for a in (rgb, box, seg): a.attach([rp])
log(f"MODE={MODE}")

for i in range(25):
    x = (i-12)*0.35
    if MODE == "fabric":
        xprim.set_world_pose(position=np.array([x, 0.0, 2.0]))
    else:
        op.Set(Gf.Vec3d(x, 0, 2))
    for _ in range(6): app.update()
    rep.orchestrator.step(rt_subframes=8); app.update()
    bb = box.get_data(); sg = seg.get_data()
    sd = np.asarray(sg["data"]); s2 = sg["info"]["idToLabels"]
    dids = [int(k) for k, v in s2.items() if "drone" in str(v).lower()]
    npx = int(np.isin(sd, dids).sum())
    found = bb["data"] is not None and len(bb["data"]) > 0
    log(f"iter{i:02d}: x={x:+.1f} box={'Y' if found else 'N'} npx={npx}")
    if i in (0, 12, 24):
        Image.fromarray(rgb.get_data()[:, :, :3]).save(OUT+f"/mintest_{MODE}_{i}.png")
log("done")
app.close()
