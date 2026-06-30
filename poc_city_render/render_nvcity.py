"""NVIDIA City Demo(CityEngine) USD 품질 판단용 PoC 렌더 — 독립 프로젝트 에셋.
Isaac 5.1 검증 패턴(replicator). 지난 gumi 렌더의 교훈 반영:
  - 카메라 고도 상한(<=200m)으로 드론 현실 범위 유지(1798m 같은 탑다운 방지)
  - gumi(kmit) 무관, NVIDIA 공식 무료 도시팩 사용
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1920, "height": 1080})

import os
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf
import omni.usd
import omni.replicator.core as rep

STAGE = "/home/karma/OSMtoUSD/assets/nvidia_city_demo/Demos/AEC/TowerDemo/CityDemopack/World_CityDemopack.usd"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
os.makedirs(OUT, exist_ok=True)
_logf = open(os.path.join(OUT, "run_nvcity.log"), "w")
def log(m):
    print(m); _logf.write(str(m) + "\n"); _logf.flush()

log("씬 로드 중...")
omni.usd.get_context().open_stage(STAGE)
for _ in range(10):
    app.update()
stage = omni.usd.get_context().get_stage()

# 기존 조명 유무 확인
has_light = any(p.IsA(UsdLux.DistantLight) or p.IsA(UsdLux.DomeLight) or
                p.IsA(UsdLux.SphereLight) or p.IsA(UsdLux.RectLight)
                for p in stage.Traverse())
log(f"기존 조명 존재: {has_light}")
if not has_light:
    sun = UsdLux.DistantLight.Define(stage, "/World/PoC_Sun")
    sun.CreateIntensityAttr(3000.0); sun.CreateAngleAttr(0.53)
    UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-50.0, 0.0, 35.0))
    sky = UsdLux.DomeLight.Define(stage, "/World/PoC_Sky")
    sky.CreateIntensityAttr(1000.0); sky.CreateColorAttr(Gf.Vec3f(0.7, 0.82, 1.0))
    log("조명(Sun+Sky) 추가")

# bbox: defaultPrim 우선, 없으면 최상위 prim 합집합
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                          [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
target = stage.GetDefaultPrim()
if not target or not target.IsValid():
    target = next((c for c in stage.GetPseudoRoot().GetChildren()), None)
rng = cache.ComputeWorldBound(target).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax()
cx, cy = (mn[0]+mx[0])/2, (mn[1]+mx[1])/2
top = mx[2]                                   # 가장 높은 건물 z
diagxy = ((mx[0]-mn[0])**2 + (mx[1]-mn[1])**2) ** 0.5
log(f"defaultPrim={target.GetPath()} bbox min={tuple(round(v,1) for v in mn)} "
    f"max={tuple(round(v,1) for v in mx)} top={top:.1f} diagXY={diagxy:.1f}m")

# 고도 상한 200m로 드론 현실 범위 유지
def clamp(v, lo, hi): return max(lo, min(hi, v))
d = clamp(diagxy * 0.35, 80, 500)             # 중심에서 수평 거리
alt_hi = clamp(top * 2.0, 120, 200)           # 스카이라인 고도
shots = [
    ("1_skyline", (cx - d,        cy - d,        alt_hi),    (cx, cy, top*0.35), 24.0),
    ("2_drone",   (cx - d*0.5,    cy - d*0.5,    clamp(top*1.2, 80, 150)), (cx, cy, top*0.4), 28.0),
    ("3_street",  (cx - d*0.2,    cy - d*0.2,    clamp(top*0.3, 12, 30)),  (cx, cy, top*0.3), 20.0),
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
        Image.fromarray(data[:, :, :3]).save(os.path.join(OUT, f"nvcity_{name}.png"))
        log(f"저장: nvcity_{name}.png pos={tuple(round(v,1) for v in pos)} focal={focal}")
    else:
        log(f"[경고] {name} RGB 없음")
    rgb.detach()

log("=== 완료 ===")
app.close()
