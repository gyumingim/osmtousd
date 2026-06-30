"""OSM 도시(gumi.usda) 품질 판단용 PoC 렌더.
replicator_test.py(검증된 Isaac 5.1 패턴) 기반. 변경점:
  - headless=True (배치 캡처)
  - gumi.usda엔 조명이 없어 Sun(DistantLight)+Sky(DomeLight) 추가
  - 빌딩 bbox 자동 계산 → 드론 시점 3컷(공중/오블리크/저공)
  - 파일 로그(stdout은 segfault 시 유실 — ISAAC_SIM_TIPS §9)
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1920, "height": 1080})

import os
import numpy as np
from PIL import Image
from pxr import UsdGeom, UsdLux, Gf, Usd
import omni.usd
import omni.replicator.core as rep

STAGE = "/home/karma/OSMtoUSD/kmit/gumi.usda"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
os.makedirs(OUT, exist_ok=True)
_logf = open(os.path.join(OUT, "run.log"), "w")
def log(m):
    print(m); _logf.write(str(m) + "\n"); _logf.flush()

log("씬 로드 중...")
omni.usd.get_context().open_stage(STAGE)
for _ in range(5):
    app.update()
stage = omni.usd.get_context().get_stage()

# ── 조명 추가 (gumi.usda엔 조명 없음 → 안 넣으면 깜깜) ──────────────────────────
sun = UsdLux.DistantLight.Define(stage, "/World/PoC_Sun")
sun.CreateIntensityAttr(3000.0)
sun.CreateAngleAttr(0.53)
UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-50.0, 0.0, 35.0))
sky = UsdLux.DomeLight.Define(stage, "/World/PoC_Sky")
sky.CreateIntensityAttr(1000.0)
sky.CreateColorAttr(Gf.Vec3f(0.7, 0.82, 1.0))  # 옅은 하늘색 앰비언트
log("조명(Sun+Sky) 추가 완료")

# ── 빌딩 bbox로 카메라 자동 배치 ───────────────────────────────────────────────
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                          [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
rng = cache.ComputeWorldBound(stage.GetPrimAtPath("/World/Buildings")).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax()
cx, cy, cz = (mn[0]+mx[0])/2, (mn[1]+mx[1])/2, (mn[2]+mx[2])/2
diag = (Gf.Vec3d(mx) - Gf.Vec3d(mn)).GetLength()
log(f"Buildings bbox min={tuple(round(v,1) for v in mn)} "
    f"max={tuple(round(v,1) for v in mx)} center=({cx:.1f},{cy:.1f},{cz:.1f}) diag={diag:.1f}m")
center = (cx, cy, cz)

# (이름, 카메라위치, look_at, 초점거리mm)
shots = [
    ("1_aerial",  (cx,            cy - diag*0.35, cz + diag*0.30), center,                       24.0),
    ("2_oblique", (cx - diag*0.20, cy - diag*0.20, cz + diag*0.10), center,                       28.0),
    ("3_lowalt",  (cx,            cy - diag*0.10, cz + 40.0),       (cx, cy + diag*0.15, cz+15),  20.0),
]

for name, pos, look, focal in shots:
    cam = rep.create.camera(position=pos, look_at=look, focal_length=focal)
    rp = rep.create.render_product(cam, (1920, 1080))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach([rp])
    for _ in range(8):
        app.update()
    rep.orchestrator.step(rt_subframes=32)  # 스틸 누적으로 노이즈 감소
    app.update()
    data = rgb.get_data()
    if data is not None and len(data) > 0:
        Image.fromarray(data[:, :, :3]).save(os.path.join(OUT, f"city_{name}.png"))
        log(f"저장: city_{name}.png  pos={tuple(round(v,1) for v in pos)} focal={focal}mm")
    else:
        log(f"[경고] {name} RGB 데이터 없음")
    rgb.detach()

log("=== 완료 ===")
app.close()
