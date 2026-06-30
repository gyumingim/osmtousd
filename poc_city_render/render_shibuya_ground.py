"""지상 시점 안티드론: 지상 카메라가 위(하늘)의 드론을 올려다봄 + 자동 GT.
슬라이드5 케이스: 하늘배경 / 빌딩배경. 드론 물리크기 고정 → 거리에 따라 화면크기 변화(멀티스케일).
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
_logf = open(os.path.join(OUT, "run_ground.log"), "w")
def log(m): print(m, flush=True); _logf.write(str(m)+"\n"); _logf.flush()

s = carb.settings.get_settings()
s.set("/rtx/rendermode", "PathTracing")
s.set("/rtx/pathtracing/totalSpp", 96)
try: s.set_bool("/rtx/pathtracing/optixDenoiser/enabled", True)
except Exception: pass

omni.usd.get_context().open_stage(USD)
for _ in range(15): app.update()
stage = omni.usd.get_context().get_stage()
up = UsdGeom.GetStageUpAxis(stage)

sun = UsdLux.DistantLight.Define(stage, "/PoC_Sun")
sun.CreateIntensityAttr(3500.0); sun.CreateAngleAttr(0.53)
UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-55.0, 0.0, 20.0))
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
c1 = (mn[g1]+mx[g1])/2; c2 = (mn[g2]+mx[g2])/2; top = mx[ui]; ground = mn[ui]
gd = ((mx[g1]-mn[g1])**2 + (mx[g2]-mn[g2])**2) ** 0.5

# 드론 1회 생성(위치=부모 translate, 매 컷마다 갱신)
def cube(path, sx, sy, sz, col=(0.06,0.06,0.08)):
    c = UsdGeom.Cube.Define(stage, path)
    UsdGeom.Xformable(c).AddScaleOp().Set(Gf.Vec3f(sx, sy, sz))
    c.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*col)]))
def cube_at(path, sx, sy, sz, tx, ty, tz, col=(0.04,0.04,0.05)):
    c = UsdGeom.Cube.Define(stage, path); xf = UsdGeom.Xformable(c)
    xf.AddScaleOp().Set(Gf.Vec3f(sx, sy, sz)); xf.AddTranslateOp().Set(Gf.Vec3d(tx, ty, tz))
    c.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*col)]))
S = gd * 0.012
drone = UsdGeom.Xform.Define(stage, "/Drone")
dpos = UsdGeom.Xformable(drone).AddTranslateOp()
tilt = UsdGeom.Xform.Define(stage, "/Drone/tilt"); txf = UsdGeom.Xformable(tilt)
if up == 'Y': txf.AddRotateXOp().Set(-90.0)
txf.AddRotateYOp().Set(20.0)
cube("/Drone/tilt/body", S*0.45, S*0.45, S*0.16)
cube("/Drone/tilt/arm_x", S*1.0, S*0.07, S*0.05)
cube("/Drone/tilt/arm_y", S*0.07, S*1.0, S*0.05)
L = S*0.85
for nm, tx, ty in [("r0", L, 0), ("r1", -L, 0), ("r2", 0, L), ("r3", 0, -L)]:
    cube_at(f"/Drone/tilt/{nm}", S*0.3, S*0.3, S*0.04, tx, ty, S*0.08)
from isaacsim.core.utils.semantics import add_update_semantics
add_update_semantics(stage.GetPrimAtPath("/Drone"), "drone")

edge = mn[g2]                          # 도시 -g2 가장자리
cam_g2 = edge - gd*0.40                 # 도시 밖(건물 가림 방지)
cam_h = max(ground, 0.0) + top*0.20     # 저고도 지상센서
log(f"ground={ground:.1f} top={top:.1f} edge={edge:.1f} cam_g2={cam_g2:.1f} cam_h={cam_h:.1f}")
# (이름, 드론위치, 카메라위치, 초점) — 도시 밖 저고도에서 위 올려다봄
shots = [
    ("sky",      V(c1, c2,             top*2.8), V(c1, cam_g2, cam_h), 28.0),
    ("building", V(c1, edge + gd*0.25, top*1.20), V(c1, cam_g2, cam_h), 50.0),
]

def dump_gt(name, rgb, bb, seg):
    img = Image.fromarray(rgb[:, :, :3]).convert("RGB")
    img.save(os.path.join(OUT, f"ground_{name}_rgb.png"))
    recs = bb["data"]; id2 = bb["info"]["idToLabels"]
    def lab(sid):
        v = id2.get(sid, id2.get(str(sid), None))
        return v.get("class", str(v)) if isinstance(v, dict) else str(v)
    boxes = [{"class": lab(int(r["semanticId"])), "x_min": int(r["x_min"]), "y_min": int(r["y_min"]),
              "x_max": int(r["x_max"]), "y_max": int(r["y_max"])} for r in recs]
    json.dump(boxes, open(os.path.join(OUT, f"ground_{name}_boxes.json"), "w"), indent=2)
    sd = np.asarray(seg["data"]); s2 = seg["info"]["idToLabels"]
    dids = [int(k) for k, v in s2.items() if "drone" in str(v).lower()]
    mask = np.isin(sd, dids).astype(np.uint8)*255
    Image.fromarray(mask).save(os.path.join(OUT, f"ground_{name}_mask.png"))
    ov = img.copy(); dr = ImageDraw.Draw(ov)
    for b in boxes:
        if "drone" in b["class"].lower():
            dr.rectangle([b["x_min"], b["y_min"], b["x_max"], b["y_max"]], outline=(255,0,0), width=4)
            dr.text((b["x_min"], max(0, b["y_min"]-14)), "drone", fill=(255,0,0))
    ov.save(os.path.join(OUT, f"ground_{name}_overlay.png"))
    log(f"[{name}] 박스={boxes} 드론픽셀={int((mask>0).sum())}")

for name, P, campos, focal in shots:
    dpos.Set(Gf.Vec3d(*P))
    cam = rep.create.camera(position=campos, look_at=P, focal_length=focal)
    rp = rep.create.render_product(cam, (1920, 1080))
    rgb_a = rep.AnnotatorRegistry.get_annotator("rgb")
    box_a = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
    seg_a = rep.AnnotatorRegistry.get_annotator("semantic_segmentation", init_params={"colorize": False})
    for a in (rgb_a, box_a, seg_a): a.attach([rp])
    for _ in range(15): app.update()
    rep.orchestrator.step(rt_subframes=48); app.update()
    dump_gt(name, rgb_a.get_data(), box_a.get_data(), seg_a.get_data())
    for a in (rgb_a, box_a, seg_a): a.detach()

log("=== 완료 ===")
app.close()
