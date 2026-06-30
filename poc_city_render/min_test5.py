"""격리5: 도시 로드 + 카메라 고정(1회 생성, 안 움직임) + 드론만 화면 가로질러 25회.
25/25면 '카메라 고정'이 해법(=프로세스당 1시점)."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1280, "height": 720})
import math, numpy as np
from pxr import UsdGeom, UsdLux, Gf, Vt, Usd
import omni.usd
import omni.replicator.core as rep

OUT = "/home/karma/OSMtoUSD/poc_city_render"
def log(m): print(m, flush=True); open(OUT+"/run_mintest5.log", "a").write(str(m)+"\n")
open(OUT+"/run_mintest5.log", "w").close()
W, H, HAP = 1280, 720, 36.0
ui, g1, g2 = 1, 0, 2
_wup = Gf.Vec3d(0, 1, 0)
def focal_of(h): return (HAP/2)/math.tan(math.radians(h)/2)

omni.usd.get_context().open_stage("/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.usd")
for _ in range(15): app.update()
stage = omni.usd.get_context().get_stage()
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange(); mn, mx = rng.GetMin(), rng.GetMax()
c1 = (mn[g1]+mx[g1])/2; c2 = (mn[g2]+mx[g2])/2; top = mx[ui]; ground = mn[ui]
gd = ((mx[g1]-mn[g1])**2+(mx[g2]-mn[g2])**2)**0.5
UsdLux.DistantLight.Define(stage, "/Sun").CreateIntensityAttr(3500.0)
dm = UsdLux.DomeLight.Define(stage, "/Sky"); dm.CreateIntensityAttr(1000.0); dm.CreateColorAttr(Gf.Vec3f(0.6, 0.7, 0.95))

cube = UsdGeom.Cube.Define(stage, "/Drone"); dpos = UsdGeom.Xformable(cube).AddTranslateOp()
UsdGeom.Xformable(cube).AddScaleOp().Set(Gf.Vec3f(gd*0.015, gd*0.015, gd*0.015))
cube.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(0.9, 0.1, 0.1)]))
from isaacsim.core.utils.semantics import add_update_semantics
add_update_semantics(stage.GetPrimAtPath("/Drone"), "drone")

# 카메라 1회 생성, 고정(절대 안 움직임)
hfov = 60.0; thw = math.tan(math.radians(hfov)/2)
ep = [0, 0, 0]; Rr = gd*0.85; ep[g1] = c1+Rr; ep[g2] = c2; ep[ui] = max(ground, 0)+top*0.2; eye = Gf.Vec3d(*ep)
Lp = [0, 0, 0]; Lp[g1] = c1; Lp[g2] = c2; Lp[ui] = top*1.4
cam = rep.create.camera(position=tuple(eye), look_at=tuple(Lp), focal_length=focal_of(hfov), horizontal_aperture=HAP, clipping_range=(0.05, 1e8))
rp = rep.create.render_product(cam, (W, H))
rgb = rep.AnnotatorRegistry.get_annotator("rgb"); box = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
seg = rep.AnnotatorRegistry.get_annotator("semantic_segmentation", init_params={"colorize": False})
for a in (rgb, box, seg): a.attach([rp])
f = (Gf.Vec3d(*Lp)-eye); f = f/f.GetLength(); r = Gf.Cross(f, _wup); r = r/r.GetLength(); u = Gf.Cross(r, f)
D = gd*0.3; hw = D*thw; hh = hw*H/W

for i in range(25):
    ox = ((i-12)/12.0)*0.6*hw; oy = math.sin(i*0.5)*0.4*hh
    d3 = Gf.Vec3d(eye[0]+f[0]*D+r[0]*ox+u[0]*oy, eye[1]+f[1]*D+r[1]*ox+u[1]*oy, eye[2]+f[2]*D+r[2]*ox+u[2]*oy)
    dpos.Set(d3)
    for _ in range(6): app.update()
    rep.orchestrator.step(rt_subframes=10); app.update()
    bb = box.get_data(); sg = seg.get_data(); sd = np.asarray(sg["data"]); s2 = sg["info"]["idToLabels"]
    dids = [int(k) for k, v in s2.items() if "drone" in str(v).lower()]; npx = int(np.isin(sd, dids).sum())
    found = bb["data"] is not None and len(bb["data"]) > 0
    log(f"iter{i:02d}: su={ox/hw:+.2f} sv={oy/hh:+.2f} box={'Y' if found else 'N'} npx={npx}")
log("done"); app.close()
