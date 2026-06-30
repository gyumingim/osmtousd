"""FBX 도시 → USD 변환 + 렌더 (독립 프로젝트, 사용자 제공 에셋).
- omni.kit.asset_converter로 FBX→USD (ISAAC_SIM_TIPS §5 패턴)
- 방향: 지오메트리 회전 대신 stage up축을 읽어 카메라를 맞춤(Y-up/Z-up 무관)
- 고도: 건물 높이 상대값 → cm/m 스케일 무관
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1920, "height": 1080})

import os, asyncio
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf
import omni.usd
import omni.replicator.core as rep
import omni.kit.asset_converter as ac

FBX = "/home/karma/OSMtoUSD/assets/city_buildings/city_buildings.fbx"
USD = "/home/karma/OSMtoUSD/assets/city_buildings/city_buildings.usd"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
os.makedirs(OUT, exist_ok=True)
_logf = open(os.path.join(OUT, "run_fbxcity.log"), "w")
def log(m):
    print(m); _logf.write(str(m) + "\n"); _logf.flush()

# ── FBX → USD 변환 ────────────────────────────────────────────────────────────
async def _convert(inp, outp):
    task = ac.get_instance().create_converter_task(inp, outp, lambda a, b: None,
                                                   ac.AssetConverterContext())
    ok = await task.wait_until_finished()
    return ok, task.get_status(), task.get_error_message()

log("FBX→USD 변환 중...")
fut = asyncio.ensure_future(_convert(FBX, USD))
while not fut.done():
    app.update()
ok, status, err = fut.result()
log(f"변환 결과 ok={ok} status={status} err={err}")
if not ok:
    log("[중단] 변환 실패"); app.close(); raise SystemExit(1)

# ── 변환된 USD 로드 ───────────────────────────────────────────────────────────
omni.usd.get_context().open_stage(USD)
for _ in range(10):
    app.update()
stage = omni.usd.get_context().get_stage()

up = UsdGeom.GetStageUpAxis(stage)            # 'Y' 또는 'Z'
log(f"stage upAxis={up}  metersPerUnit={UsdGeom.GetStageMetersPerUnit(stage)}")

# ── 조명 (없으면 추가) ────────────────────────────────────────────────────────
has_light = any(p.IsA(UsdLux.DistantLight) or p.IsA(UsdLux.DomeLight) or
                p.IsA(UsdLux.SphereLight) or p.IsA(UsdLux.RectLight)
                for p in stage.Traverse())
log(f"기존 조명={has_light}")
if not has_light:
    sun = UsdLux.DistantLight.Define(stage, "/PoC_Sun")
    sun.CreateIntensityAttr(3000.0); sun.CreateAngleAttr(0.53)
    UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-50.0, 0.0, 35.0))
    sky = UsdLux.DomeLight.Define(stage, "/PoC_Sky")
    sky.CreateIntensityAttr(1000.0); sky.CreateColorAttr(Gf.Vec3f(0.7, 0.82, 1.0))

# ── bbox + up축 기준 카메라 ───────────────────────────────────────────────────
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                          [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
target = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(target).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax()
log(f"bbox min={tuple(round(v,1) for v in mn)} max={tuple(round(v,1) for v in mx)}")

ui = 1 if up == 'Y' else 2                     # up축 인덱스
g1, g2 = ([0, 2] if up == 'Y' else [0, 1])     # 지면 두 축
def V(gv1, gv2, uv):
    p = [0.0, 0.0, 0.0]; p[g1] = gv1; p[g2] = gv2; p[ui] = uv; return tuple(p)

c1 = (mn[g1] + mx[g1]) / 2
c2 = (mn[g2] + mx[g2]) / 2
H = mx[ui] - max(mn[ui], 0)                    # 건물 높이(대략)
gdiag = ((mx[g1]-mn[g1])**2 + (mx[g2]-mn[g2])**2) ** 0.5
log(f"ground_center=({c1:.1f},{c2:.1f}) H={H:.1f} gdiag={gdiag:.1f}")

# (이름, 카메라, look_at, 초점) — 전부 상대값(스케일 무관)
shots = [
    ("1_skyline", V(c1 - gdiag*0.40, c2 - gdiag*0.40, H*1.8),  V(c1, c2, H*0.35), 24.0),
    ("2_drone",   V(c1 - gdiag*0.25, c2 - gdiag*0.25, H*1.1),  V(c1, c2, H*0.40), 28.0),
    ("3_street",  V(c1 - gdiag*0.10, c2 - gdiag*0.10, H*0.25), V(c1, c2, H*0.30), 20.0),
]

for name, pos, look, focal in shots:
    cam = rep.create.camera(position=pos, look_at=look, focal_length=focal)
    rp = rep.create.render_product(cam, (1920, 1080))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach([rp])
    for _ in range(10):
        app.update()
    rep.orchestrator.step(rt_subframes=48)
    app.update()
    data = rgb.get_data()
    if data is not None and len(data) > 0:
        Image.fromarray(data[:, :, :3]).save(os.path.join(OUT, f"fbxcity_{name}.png"))
        log(f"저장: fbxcity_{name}.png pos={tuple(round(v,1) for v in pos)}")
    else:
        log(f"[경고] {name} RGB 없음")
    rgb.detach()

log("=== 완료 ===")
app.close()
