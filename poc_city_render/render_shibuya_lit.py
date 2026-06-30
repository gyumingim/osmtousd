"""Shibuya 재렌더 — 조명 강제 추가(자체 조명 약해서 깜깜했음). 재변환 X.
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1920, "height": 1080})

import os
import carb
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf
import omni.usd
import omni.replicator.core as rep

USD = "/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.usd"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
_logf = open(os.path.join(OUT, "run_shibuya_lit.log"), "w")
def log(m): print(m, flush=True); _logf.write(str(m)+"\n"); _logf.flush()

s = carb.settings.get_settings()
s.set("/rtx/rendermode", "PathTracing")
s.set("/rtx/pathtracing/totalSpp", 128)
try: s.set_bool("/rtx/pathtracing/optixDenoiser/enabled", True)
except Exception: pass

omni.usd.get_context().open_stage(USD)
for _ in range(15):
    app.update()
stage = omni.usd.get_context().get_stage()
up = UsdGeom.GetStageUpAxis(stage)

# 조명 강제 추가(밝게) — 자체 조명 무시하고 주광 확보
sun = UsdLux.DistantLight.Define(stage, "/PoC_Sun")
sun.CreateIntensityAttr(5000.0); sun.CreateAngleAttr(0.53)
UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-45.0, 0.0, 30.0))
sky = UsdLux.DomeLight.Define(stage, "/PoC_Sky")
sky.CreateIntensityAttr(2000.0); sky.CreateColorAttr(Gf.Vec3f(0.75, 0.85, 1.0))
log("강한 Sun(5000)+Sky(2000) 추가")

cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax()
ui = 1 if up == 'Y' else 2
g1, g2 = ([0, 2] if up == 'Y' else [0, 1])
def V(a, b, u):
    p = [0.0, 0.0, 0.0]; p[g1] = a; p[g2] = b; p[ui] = u; return tuple(p)
c1 = (mn[g1]+mx[g1])/2; c2 = (mn[g2]+mx[g2])/2
gd = ((mx[g1]-mn[g1])**2 + (mx[g2]-mn[g2])**2) ** 0.5
log(f"up={up} center=({c1:.1f},{c2:.1f}) gd={gd:.1f}")

shots = [
    ("1_far",  V(c1, c2 - gd*1.00, gd*0.45), V(c1, c2, gd*0.02), 24.0),
    ("2_mid",  V(c1, c2 - gd*0.55, gd*0.22), V(c1, c2, gd*0.02), 28.0),
    ("3_near", V(c1, c2 - gd*0.28, gd*0.09), V(c1, c2, gd*0.04), 24.0),
]
for name, pos, look, focal in shots:
    cam = rep.create.camera(position=pos, look_at=look, focal_length=focal)
    rp = rep.create.render_product(cam, (1920, 1080))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach([rp])
    for _ in range(12):
        app.update()
    rep.orchestrator.step(rt_subframes=64)
    app.update()
    data = rgb.get_data()
    if data is not None and len(data) > 0:
        Image.fromarray(data[:, :, :3]).save(os.path.join(OUT, f"shibuya_lit_{name}.png"))
        log(f"저장: shibuya_lit_{name}.png")
    else:
        log(f"[경고] {name} RGB 없음")
    rgb.detach()
log("=== 완료 ===")
app.close()
