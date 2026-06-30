"""Shibuya large map FBX → USD 변환 + Path Tracing 렌더.
- 텍스처 504장 매칭 확인됨(Large map-*)
- 렌더모드 PathTracing (고퀄), rt_subframes로 누적 수렴
- 카메라: 지면 footprint 기준(스트레이 지오메트리 영향 차단), Y-up/cm 대응
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1920, "height": 1080})

import os, asyncio
import carb
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf
import omni.usd
import omni.replicator.core as rep
import omni.kit.asset_converter as ac

FBX = "/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.fbx"
USD = "/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.usd"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
_logf = open(os.path.join(OUT, "run_shibuya.log"), "w")
def log(m): print(m, flush=True); _logf.write(str(m)+"\n"); _logf.flush()

# Path Tracing
s = carb.settings.get_settings()
s.set("/rtx/rendermode", "PathTracing")
s.set("/rtx/pathtracing/totalSpp", 128)
try: s.set_bool("/rtx/pathtracing/optixDenoiser/enabled", True)
except Exception: pass
log("렌더모드=PathTracing")

# 변환
async def _convert(inp, outp):
    t = ac.get_instance().create_converter_task(inp, outp, lambda a, b: None, ac.AssetConverterContext())
    ok = await t.wait_until_finished()
    return ok, t.get_status(), t.get_error_message()
log("FBX→USD 변환 중(98MB, 좀 걸림)...")
fut = asyncio.ensure_future(_convert(FBX, USD))
while not fut.done():
    app.update()
ok, status, err = fut.result()
log(f"변환 ok={ok} status={status} err={err}")
if not ok:
    log("[중단] 변환 실패"); app.close(); raise SystemExit(1)

omni.usd.get_context().open_stage(USD)
for _ in range(15):
    app.update()
stage = omni.usd.get_context().get_stage()
up = UsdGeom.GetStageUpAxis(stage)
log(f"upAxis={up} metersPerUnit={UsdGeom.GetStageMetersPerUnit(stage)}")

# 조명
has_light = any(p.IsA(UsdLux.DistantLight) or p.IsA(UsdLux.DomeLight) or
                p.IsA(UsdLux.SphereLight) or p.IsA(UsdLux.RectLight) for p in stage.Traverse())
log(f"기존 조명={has_light}")
if not has_light:
    sun = UsdLux.DistantLight.Define(stage, "/PoC_Sun")
    sun.CreateIntensityAttr(3000.0); sun.CreateAngleAttr(0.53)
    UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-50.0, 0.0, 35.0))
    sky = UsdLux.DomeLight.Define(stage, "/PoC_Sky")
    sky.CreateIntensityAttr(1000.0); sky.CreateColorAttr(Gf.Vec3f(0.7, 0.82, 1.0))

# bbox + 카메라(지면 기준)
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax()
log(f"bbox min={tuple(round(v,1) for v in mn)} max={tuple(round(v,1) for v in mx)}")
ui = 1 if up == 'Y' else 2
g1, g2 = ([0, 2] if up == 'Y' else [0, 1])
def V(a, b, u):
    p = [0.0, 0.0, 0.0]; p[g1] = a; p[g2] = b; p[ui] = u; return tuple(p)
c1 = (mn[g1]+mx[g1])/2; c2 = (mn[g2]+mx[g2])/2
gd = ((mx[g1]-mn[g1])**2 + (mx[g2]-mn[g2])**2) ** 0.5
log(f"ground_center=({c1:.1f},{c2:.1f}) gdiag={gd:.1f}")

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
    rep.orchestrator.step(rt_subframes=64)   # PT 수렴
    app.update()
    data = rgb.get_data()
    if data is not None and len(data) > 0:
        Image.fromarray(data[:, :, :3]).save(os.path.join(OUT, f"shibuya_{name}.png"))
        log(f"저장: shibuya_{name}.png pos={tuple(round(v,1) for v in pos)}")
    else:
        log(f"[경고] {name} RGB 없음")
    rgb.detach()
log("=== 완료 ===")
app.close()
