"""자동 GT 데모: 시부야+드론 씬 → RGB + 2D BBox + 세그마스크 자동 생성.
사람 라벨링 0. semantic 'drone' 태그를 Replicator가 읽어 박스/마스크 자동 출력.
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1920, "height": 1080})

import os, json
import numpy as np
import carb
from PIL import Image, ImageDraw
from pxr import UsdGeom, UsdLux, Usd, Gf, Vt
import omni.usd
import omni.replicator.core as rep

USD = "/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.usd"
HDRI = "/home/karma/OSMtoUSD/assets/hdri/sky.hdr"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
_logf = open(os.path.join(OUT, "run_gt.log"), "w")
def log(m): print(m, flush=True); _logf.write(str(m)+"\n"); _logf.flush()

s = carb.settings.get_settings()
s.set("/rtx/rendermode", "PathTracing")
s.set("/rtx/pathtracing/totalSpp", 128)
try: s.set_bool("/rtx/pathtracing/optixDenoiser/enabled", True)
except Exception: pass

omni.usd.get_context().open_stage(USD)
for _ in range(15): app.update()
stage = omni.usd.get_context().get_stage()
up = UsdGeom.GetStageUpAxis(stage)

# 조명: 태양 + HDRI 돔
sun = UsdLux.DistantLight.Define(stage, "/PoC_Sun")
sun.CreateIntensityAttr(3500.0); sun.CreateAngleAttr(0.53)
UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-45.0, 0.0, 30.0))
dome = UsdLux.DomeLight.Define(stage, "/PoC_Sky")
dome.CreateIntensityAttr(1000.0); dome.CreateTextureFileAttr(HDRI)
UsdGeom.Xformable(dome.GetPrim()).AddRotateYOp().Set(150.0)

cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax()
ui = 1 if up == 'Y' else 2
g1, g2 = ([0, 2] if up == 'Y' else [0, 1])
def V(a, b, u):
    p = [0.0, 0.0, 0.0]; p[g1] = a; p[g2] = b; p[ui] = u; return tuple(p)
c1 = (mn[g1]+mx[g1])/2; c2 = (mn[g2]+mx[g2])/2; top = mx[ui]
gd = ((mx[g1]-mn[g1])**2 + (mx[g2]-mn[g2])**2) ** 0.5

# 드론(위치=부모 translate, 회전=자식 tilt)
def cube(path, sx, sy, sz, col=(0.08,0.08,0.1)):
    c = UsdGeom.Cube.Define(stage, path)
    UsdGeom.Xformable(c).AddScaleOp().Set(Gf.Vec3f(sx, sy, sz))
    c.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*col)]))
def cube_at(path, sx, sy, sz, tx, ty, tz, col=(0.05,0.05,0.07)):
    c = UsdGeom.Cube.Define(stage, path); xf = UsdGeom.Xformable(c)
    xf.AddScaleOp().Set(Gf.Vec3f(sx, sy, sz)); xf.AddTranslateOp().Set(Gf.Vec3d(tx, ty, tz))
    c.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*col)]))
S = gd * 0.018
P = V(c1, c2, top*1.15)
drone = UsdGeom.Xform.Define(stage, "/Drone")
UsdGeom.Xformable(drone).AddTranslateOp().Set(Gf.Vec3d(*P))
tilt = UsdGeom.Xform.Define(stage, "/Drone/tilt"); txf = UsdGeom.Xformable(tilt)
if up == 'Y': txf.AddRotateXOp().Set(-90.0)
txf.AddRotateYOp().Set(25.0)
cube("/Drone/tilt/body", S*0.45, S*0.45, S*0.16)
cube("/Drone/tilt/arm_x", S*1.0, S*0.07, S*0.05)
cube("/Drone/tilt/arm_y", S*0.07, S*1.0, S*0.05)
L = S*0.85
for nm, tx, ty in [("r0", L, 0), ("r1", -L, 0), ("r2", 0, L), ("r3", 0, -L)]:
    cube_at(f"/Drone/tilt/{nm}", S*0.3, S*0.3, S*0.04, tx, ty, S*0.08)
from isaacsim.core.utils.semantics import add_update_semantics
add_update_semantics(stage.GetPrimAtPath("/Drone"), "drone")
log("드론+semantic 'drone' 적용")

# 카메라 + annotator(자동 GT)
cam = rep.create.camera(position=V(c1 - gd*0.12, c2 - gd*0.45, top*2.1), look_at=P, focal_length=40.0)
rp = rep.create.render_product(cam, (1920, 1080))
rgb_a = rep.AnnotatorRegistry.get_annotator("rgb")
box_a = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
seg_a = rep.AnnotatorRegistry.get_annotator("semantic_segmentation", init_params={"colorize": False})
for a in (rgb_a, box_a, seg_a): a.attach([rp])
for _ in range(15): app.update()
rep.orchestrator.step(rt_subframes=64); app.update()

rgb = rgb_a.get_data(); bb = box_a.get_data(); seg = seg_a.get_data()

# RGB 저장
img = Image.fromarray(rgb[:, :, :3]).convert("RGB")
img.save(os.path.join(OUT, "gt_rgb.png"))

# 2D BBox 파싱(구조화 배열)
log(f"bbox raw keys={list(bb.keys()) if isinstance(bb,dict) else type(bb)}")
recs = bb["data"]; id2lab = bb["info"]["idToLabels"]
def lab_of(sid):
    v = id2lab.get(sid, id2lab.get(str(sid), id2lab.get(int(sid), None)))
    if isinstance(v, dict): return v.get("class", str(v))
    return str(v)
boxes = []
for r in recs:
    boxes.append({"class": lab_of(int(r["semanticId"])),
                  "x_min": int(r["x_min"]), "y_min": int(r["y_min"]),
                  "x_max": int(r["x_max"]), "y_max": int(r["y_max"])})
json.dump(boxes, open(os.path.join(OUT, "gt_boxes.json"), "w"), indent=2, ensure_ascii=False)
log(f"자동 박스 {len(boxes)}개: {boxes}")

# 세그마스크(드론 픽셀)
segdata = np.asarray(seg["data"]); seg2lab = seg["info"]["idToLabels"]
drone_ids = [int(k) for k, v in seg2lab.items() if "drone" in str(v).lower()]
log(f"세그 라벨맵={seg2lab} drone_ids={drone_ids} segshape={segdata.shape}")
mask = np.isin(segdata, drone_ids).astype(np.uint8) * 255
Image.fromarray(mask).save(os.path.join(OUT, "gt_mask.png"))
log(f"드론 픽셀 수={int((mask>0).sum())}")

# 오버레이(RGB + 자동박스 + 마스크 틴트)
ov = img.copy(); dr = ImageDraw.Draw(ov)
for b in boxes:
    if "drone" in b["class"].lower():
        dr.rectangle([b["x_min"], b["y_min"], b["x_max"], b["y_max"]], outline=(255, 0, 0), width=4)
        dr.text((b["x_min"], max(0, b["y_min"]-14)), "drone (auto-GT)", fill=(255, 0, 0))
ov.save(os.path.join(OUT, "gt_overlay.png"))
log("저장: gt_rgb / gt_overlay / gt_mask / gt_boxes.json")
log("=== 완료 ===")
app.close()
