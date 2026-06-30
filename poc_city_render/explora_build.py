"""eXplora 36개 STL 병합 → glb → USD 변환 → 다각도 렌더(형상 확인).
조립위치면 테일시터로, 프린트배치면 흩어진 조각으로 나옴 — 렌더로 판정.
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1280, "height": 1280})

import os, glob, asyncio
import numpy as np
import trimesh
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf
import omni.usd
import omni.replicator.core as rep
import omni.kit.asset_converter as ac

SRC = "/home/karma/OSMtoUSD/assets/explora_src/STL"
GLB = "/home/karma/OSMtoUSD/assets/explora_src/explora_merged.glb"
USD = "/home/karma/OSMtoUSD/assets/explora_src/explora.usd"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
_logf = open(os.path.join(OUT, "run_explora.log"), "w")
def log(m): print(m, flush=True); _logf.write(str(m)+"\n"); _logf.flush()

# ── 병합 ──────────────────────────────────────────────────────────────────────
files = sorted(glob.glob(os.path.join(SRC, "*.stl")))
log(f"STL {len(files)}개 로드 중...")
meshes = []
centroids = []
for fn in files:
    m = trimesh.load(fn, process=False)
    if isinstance(m, trimesh.Trimesh):
        meshes.append(m); centroids.append(m.centroid)
merged = trimesh.util.concatenate(meshes)
cen = np.array(centroids)
log(f"병합 완료: {len(merged.faces):,} faces")
log(f"전체 bbox: {np.round(merged.bounds[0],1)} ~ {np.round(merged.bounds[1],1)}")
# 파트 중심 산포(흩어짐 판정): 표준편차 vs 전체크기
size = merged.bounds[1] - merged.bounds[0]
log(f"전체 크기={np.round(size,1)}  파트중심 표준편차={np.round(cen.std(axis=0),1)}")
merged.export(GLB)
log(f"glb 저장: {GLB}")

# ── glb → USD ─────────────────────────────────────────────────────────────────
async def _conv(i, o):
    t = ac.get_instance().create_converter_task(i, o, lambda a, b: None, ac.AssetConverterContext())
    return await t.wait_until_finished(), t.get_status()
fut = asyncio.ensure_future(_conv(GLB, USD))
while not fut.done(): app.update()
ok, st = fut.result()
log(f"USD 변환 ok={ok} status={st}")

omni.usd.get_context().open_stage(USD)
for _ in range(10): app.update()
stage = omni.usd.get_context().get_stage()

# 조명(중립 밝은 돔 + 태양)
sun = UsdLux.DistantLight.Define(stage, "/L_Sun"); sun.CreateIntensityAttr(3000.0)
UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-40, 20, 10))
dome = UsdLux.DomeLight.Define(stage, "/L_Sky"); dome.CreateIntensityAttr(1500.0)
dome.CreateColorAttr(Gf.Vec3f(0.8, 0.8, 0.85))

cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax()
C = Gf.Vec3d((mn[0]+mx[0])/2, (mn[1]+mx[1])/2, (mn[2]+mx[2])/2)
R = (Gf.Vec3d(*mx) - Gf.Vec3d(*mn)).GetLength() / 2
log(f"USD bbox min={tuple(round(v,1) for v in mn)} max={tuple(round(v,1) for v in mx)} R={R:.1f}")

# 3각도 렌더
dirs = [("front", Gf.Vec3d(0.2, -1.0, 0.15)), ("side", Gf.Vec3d(1.0, -0.2, 0.15)),
        ("threeq", Gf.Vec3d(0.8, -0.8, 0.5))]
for name, d in dirs:
    pos = C + d.GetNormalized() * (R * 2.6)
    cam = rep.create.camera(position=(pos[0], pos[1], pos[2]), look_at=(C[0], C[1], C[2]), focal_length=35.0)
    rp = rep.create.render_product(cam, (1280, 1280))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb"); rgb.attach([rp])
    for _ in range(10): app.update()
    rep.orchestrator.step(rt_subframes=24); app.update()
    data = rgb.get_data()
    if data is not None and len(data) > 0:
        Image.fromarray(data[:, :, :3]).save(os.path.join(OUT, f"explora_{name}.png"))
        log(f"저장: explora_{name}.png")
    rgb.detach()
log("=== 완료 ===")
app.close()
