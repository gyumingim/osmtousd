"""변환된 city_buildings.usd 재렌더(재변환 X) — 카메라 프레이밍 수정판.
v1 문제: 스트레이 지오메트리로 bbox Y(높이)가 462m로 부풀어 고도 과대 → 탑다운.
수정: 고도/거리를 지면 footprint(gdiag) 기준, 지면 중심 조준(H 미사용 → 스트레이 영향 차단).
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1920, "height": 1080})

import os
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf
import omni.usd
import omni.replicator.core as rep

USD = "/home/karma/OSMtoUSD/assets/city_buildings/city_buildings.usd"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
_logf = open(os.path.join(OUT, "run_fbxcity_v2.log"), "w")
def log(m):
    print(m); _logf.write(str(m) + "\n"); _logf.flush()

omni.usd.get_context().open_stage(USD)
for _ in range(10):
    app.update()
stage = omni.usd.get_context().get_stage()
up = UsdGeom.GetStageUpAxis(stage)

# 조명
sun = UsdLux.DistantLight.Define(stage, "/PoC_Sun")
sun.CreateIntensityAttr(3000.0); sun.CreateAngleAttr(0.53)
UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-50.0, 0.0, 35.0))
sky = UsdLux.DomeLight.Define(stage, "/PoC_Sky")
sky.CreateIntensityAttr(1000.0); sky.CreateColorAttr(Gf.Vec3f(0.7, 0.82, 1.0))

cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                          [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
target = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(target).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax()

ui = 1 if up == 'Y' else 2
g1, g2 = ([0, 2] if up == 'Y' else [0, 1])
def V(gv1, gv2, uv):
    p = [0.0, 0.0, 0.0]; p[g1] = gv1; p[g2] = gv2; p[ui] = uv; return tuple(p)

c1 = (mn[g1] + mx[g1]) / 2
c2 = (mn[g2] + mx[g2]) / 2
gd = ((mx[g1]-mn[g1])**2 + (mx[g2]-mn[g2])**2) ** 0.5   # 지면 대각(스케일 기준)
log(f"up={up} ground_center=({c1:.1f},{c2:.1f}) gdiag={gd:.1f}  (cm 단위)")

# 전부 footprint 상대 — 지면 중심 조준, 오블리크 각도 형성
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
    for _ in range(10):
        app.update()
    rep.orchestrator.step(rt_subframes=48)
    app.update()
    data = rgb.get_data()
    if data is not None and len(data) > 0:
        Image.fromarray(data[:, :, :3]).save(os.path.join(OUT, f"fbxcity2_{name}.png"))
        log(f"저장: fbxcity2_{name}.png pos={tuple(round(v,1) for v in pos)}")
    else:
        log(f"[경고] {name} RGB 없음")
    rgb.detach()

log("=== 완료 ===")
app.close()
