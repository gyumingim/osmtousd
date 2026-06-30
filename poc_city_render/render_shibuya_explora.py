"""지상시점 안티드론 — 타겟을 eXplora 테일시터(실모델)로 교체 + 자동 GT.
모델 배치: 참조 → 실측 bbox로 중심정렬 → 도시 대비 크기 스케일 → 위치/자세.
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1920, "height": 1080})

import os, json
import numpy as np
import carb
from PIL import Image, ImageDraw
from pxr import UsdGeom, UsdLux, Usd, Gf
import omni.usd
import omni.replicator.core as rep

USD = "/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.usd"
EXPLORA = "/home/karma/OSMtoUSD/assets/explora_src/explora.usd"
HDRI = "/home/karma/OSMtoUSD/assets/hdri/sky.hdr"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
_logf = open(os.path.join(OUT, "run_explora_scene.log"), "w")
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

# ── eXplora 참조 + 중심정렬/스케일/자세 ───────────────────────────────────────
drone = UsdGeom.Xform.Define(stage, "/Drone")
dpos = UsdGeom.Xformable(drone).AddTranslateOp()           # 위치(컷마다)
rs = UsdGeom.Xform.Define(stage, "/Drone/rs")
rsx = UsdGeom.Xformable(rs); sop = rsx.AddScaleOp(); rop = rsx.AddRotateXYZOp()
centered = UsdGeom.Xform.Define(stage, "/Drone/rs/centered")
cop = UsdGeom.Xformable(centered).AddTranslateOp()
centered.GetPrim().GetReferences().AddReference(EXPLORA)
for _ in range(25): app.update()
# 참조 모델 실측 bbox(파생 변환 0인 상태)
mb = cache.ComputeWorldBound(stage.GetPrimAtPath("/Drone/rs/centered")).ComputeAlignedRange()
mmn, mmx = mb.GetMin(), mb.GetMax()
mc = ((mmn[0]+mmx[0])/2, (mmn[1]+mmx[1])/2, (mmn[2]+mmx[2])/2)
mext = max(mmx[0]-mmn[0], mmx[1]-mmn[1], mmx[2]-mmn[2])   # 최대 변(=날개폭)
target = gd * 0.03                                         # 도시 대비 타겟 크기
sc = target / mext
cop.Set(Gf.Vec3d(-mc[0], -mc[1], -mc[2]))                 # 중심 정렬
sop.Set(Gf.Vec3f(sc, sc, sc))
rop.Set(Gf.Vec3f(0.0, 0.0, 20.0))                         # 자세(우선 뱅크 20°, 보고 조정)
from isaacsim.core.utils.semantics import add_update_semantics
add_update_semantics(stage.GetPrimAtPath("/Drone"), "drone")
app.update(); app.update()
db = cache.ComputeWorldBound(stage.GetPrimAtPath("/Drone")).ComputeAlignedRange()
log(f"모델 mext={mext:.1f} sc={sc:.6f} target={target:.1f}")
log(f"배치 후 드론 bbox={tuple(round(v,1) for v in db.GetMin())}~{tuple(round(v,1) for v in db.GetMax())}")

edge = mn[g2]; cam_g2 = edge - gd*0.40; cam_h = max(ground, 0.0) + top*0.20
shots = [
    ("sky",      V(c1, c2,             top*2.8), V(c1, cam_g2, cam_h), 28.0),
    ("building", V(c1, edge + gd*0.25, top*1.20), V(c1, cam_g2, cam_h), 50.0),
]

def dump_gt(name, rgb, bb, seg):
    img = Image.fromarray(rgb[:, :, :3]).convert("RGB")
    img.save(os.path.join(OUT, f"explora_scene_{name}_rgb.png"))
    recs = bb["data"]; id2 = bb["info"]["idToLabels"]
    def lab(sid):
        v = id2.get(sid, id2.get(str(sid), None))
        return v.get("class", str(v)) if isinstance(v, dict) else str(v)
    boxes = [{"class": lab(int(r["semanticId"])), "x_min": int(r["x_min"]), "y_min": int(r["y_min"]),
              "x_max": int(r["x_max"]), "y_max": int(r["y_max"])} for r in recs]
    json.dump(boxes, open(os.path.join(OUT, f"explora_scene_{name}_boxes.json"), "w"), indent=2)
    sd = np.asarray(seg["data"]); s2 = seg["info"]["idToLabels"]
    dids = [int(k) for k, v in s2.items() if "drone" in str(v).lower()]
    mask = np.isin(sd, dids).astype(np.uint8)*255
    Image.fromarray(mask).save(os.path.join(OUT, f"explora_scene_{name}_mask.png"))
    ov = img.copy(); drw = ImageDraw.Draw(ov)
    for b in boxes:
        if "drone" in b["class"].lower():
            drw.rectangle([b["x_min"], b["y_min"], b["x_max"], b["y_max"]], outline=(255,0,0), width=4)
            drw.text((b["x_min"], max(0, b["y_min"]-14)), "drone", fill=(255,0,0))
    ov.save(os.path.join(OUT, f"explora_scene_{name}_overlay.png"))
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
