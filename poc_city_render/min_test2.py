"""격리실험2: 도시 없이, 생성기의 카메라+드론배치 로직 그대로 12회.
가릴 게 없으므로 box=N이 나오면 'basis/배치 불일치' 확정(가림 아님)."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1280, "height": 720})
import os, math, random, numpy as np
from PIL import Image
from pxr import UsdGeom, UsdLux, Gf, Vt
import omni.usd
import omni.replicator.core as rep

OUT = "/home/karma/OSMtoUSD/poc_city_render"
def log(m): print(m, flush=True); open(OUT+"/run_mintest2.log", "a").write(str(m)+"\n")
open(OUT+"/run_mintest2.log", "w").close()
W, H, HAP = 1280, 720, 36.0
gd, top, ground, c1, c2 = 535.0, 127.0, -43.0, 0.0, 0.0
ui, g1, g2 = 1, 0, 2
_wup = Gf.Vec3d(0, 1, 0)
def focal_of(h): return (HAP/2)/math.tan(math.radians(h)/2)
random.seed(20)

omni.usd.get_context().new_stage()
for _ in range(5): app.update()
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
dome = UsdLux.DomeLight.Define(stage, "/Sky"); dome.CreateIntensityAttr(1000.0); dome.CreateColorAttr(Gf.Vec3f(0.5, 0.6, 0.9))
sun = UsdLux.DistantLight.Define(stage, "/Sun"); sun.CreateIntensityAttr(3000.0)
cube = UsdGeom.Cube.Define(stage, "/Drone")
dpos = UsdGeom.Xformable(cube).AddTranslateOp()
UsdGeom.Xformable(cube).AddScaleOp().Set(Gf.Vec3f(8, 8, 8))   # 16 units
cube.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(0.9, 0.1, 0.1)]))
from isaacsim.core.utils.semantics import add_update_semantics
add_update_semantics(stage.GetPrimAtPath("/Drone"), "drone")

# 생성기와 동일: 영구 카메라 + set_cam(내 행렬)
sensor = UsdGeom.Camera.Define(stage, "/SensorCam")
sensor.CreateClippingRangeAttr(Gf.Vec2f(0.05, 1e8)); sensor.CreateHorizontalApertureAttr(HAP); sensor.CreateVerticalApertureAttr(HAP*H/W)
s_fl = sensor.CreateFocalLengthAttr(35.0); s_xf = UsdGeom.Xformable(sensor.GetPrim()).AddTransformOp()
rp = rep.create.render_product("/SensorCam", (W, H))
rgb = rep.AnnotatorRegistry.get_annotator("rgb"); box = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
seg = rep.AnnotatorRegistry.get_annotator("semantic_segmentation", init_params={"colorize": False})
for a in (rgb, box, seg): a.attach([rp])

def look_basis(eye, tgt):
    f = (tgt-eye); f = f/f.GetLength(); r = Gf.Cross(f, _wup); r = r/r.GetLength(); u = Gf.Cross(r, f); return f, r, u
def set_cam(eye, f, r, u):
    M = Gf.Matrix4d(); M.SetRow(0, Gf.Vec4d(r[0], r[1], r[2], 0)); M.SetRow(1, Gf.Vec4d(u[0], u[1], u[2], 0))
    M.SetRow(2, Gf.Vec4d(-f[0], -f[1], -f[2], 0)); M.SetRow(3, Gf.Vec4d(eye[0], eye[1], eye[2], 1)); s_xf.Set(M)

S_world = gd*0.03
for sq in range(12):
    bg = "building" if random.random() < 0.6 else "sky"
    hfov = 60.0; thw = math.tan(math.radians(hfov)/2); s_fl.Set(focal_of(hfov))
    Rr = gd*0.85; ang = random.uniform(0, 2*math.pi); ep = [0, 0, 0]
    ep[g1] = c1+Rr*math.cos(ang); ep[g2] = c2+Rr*math.sin(ang); ep[ui] = max(ground, 0)+top*0.2
    eye = Gf.Vec3d(*ep)
    Lp = [0, 0, 0]; Lp[g1] = c1; Lp[g2] = c2; Lp[ui] = top*(1.1 if bg == "building" else 2.0)
    f, r, u = look_basis(eye, Gf.Vec3d(*Lp)); set_cam(eye, f, r, u)
    D = gd*random.uniform(0.18, 0.45)
    d3 = Gf.Vec3d(eye[0]+f[0]*D, eye[1]+f[1]*D, eye[2]+f[2]*D)
    dpos.Set(d3)
    for _ in range(6): app.update()
    rep.orchestrator.step(rt_subframes=8); app.update()
    bb = box.get_data(); sg = seg.get_data(); sd = np.asarray(sg["data"]); s2 = sg["info"]["idToLabels"]
    dids = [int(k) for k, v in s2.items() if "drone" in str(v).lower()]; npx = int(np.isin(sd, dids).sum())
    rel = d3-eye; fc = rel[0]*f[0]+rel[1]*f[1]+rel[2]*f[2]
    su = (rel[0]*r[0]+rel[1]*r[1]+rel[2]*r[2])/fc/thw; sv = (rel[0]*u[0]+rel[1]*u[1]+rel[2]*u[2])/fc/(thw*H/W)
    found = bb["data"] is not None and len(bb["data"]) > 0
    log(f"sq{sq:02d} {bg:8s}: su={su:+.2f} sv={sv:+.2f} D={D:.0f} box={'Y' if found else 'N'} npx={npx}")
    if sq in (0, 3, 6): Image.fromarray(rgb.get_data()[:, :, :3]).save(OUT+f"/mintest2_{sq}.png")
log("done")
app.close()
