"""안티드론 탐지 시점 렌더: Shibuya 도시배경 + HDRI 하늘 + 드론 프록시(타겟).
- DomeLight에 Poly Haven HDRI(sky.hdr) → 실제 구름하늘 + 과노출 해소
- 드론 프록시: '+'형 쿼드콥터(축정렬, 회전 불필요), semantic 'drone'
- 카메라: 드론을 피사체로, 도시를 배경으로 (탐지 데이터 구도)
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1920, "height": 1080})

import os
import carb
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf, Vt
import omni.usd
import omni.replicator.core as rep

USD = "/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.usd"
HDRI = "/home/karma/OSMtoUSD/assets/hdri/sky.hdr"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
_logf = open(os.path.join(OUT, "run_drone.log"), "w")
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

# ── 조명: 태양(그림자) + HDRI 돔(하늘+앰비언트) ───────────────────────────────
sun = UsdLux.DistantLight.Define(stage, "/PoC_Sun")
sun.CreateIntensityAttr(3500.0); sun.CreateAngleAttr(0.53)
UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-45.0, 0.0, 30.0))
dome = UsdLux.DomeLight.Define(stage, "/PoC_Sky")
dome.CreateIntensityAttr(1000.0)
dome.CreateTextureFileAttr(HDRI)
UsdGeom.Xformable(dome.GetPrim()).AddRotateYOp().Set(150.0)   # 태양 방위 회전(프레임 밖)
log(f"HDRI 하늘={HDRI}")

# ── bbox ──────────────────────────────────────────────────────────────────────
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax()
ui = 1 if up == 'Y' else 2
g1, g2 = ([0, 2] if up == 'Y' else [0, 1])
def V(a, b, u):
    p = [0.0, 0.0, 0.0]; p[g1] = a; p[g2] = b; p[ui] = u; return tuple(p)
c1 = (mn[g1]+mx[g1])/2; c2 = (mn[g2]+mx[g2])/2
top = mx[ui]
gd = ((mx[g1]-mn[g1])**2 + (mx[g2]-mn[g2])**2) ** 0.5
log(f"up={up} center=({c1:.1f},{c2:.1f}) top={top:.1f} gd={gd:.1f}")

# ── 드론 프록시('+'형 쿼드, Z-up 로컬 → 부모에서 Y-up 매핑) ───────────────────
def cube(path, sx, sy, sz):
    c = UsdGeom.Cube.Define(stage, path)
    UsdGeom.Xformable(c).AddScaleOp().Set(Gf.Vec3f(sx, sy, sz))
    c.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(0.08, 0.08, 0.1)]))
    return c
def cube_at(path, sx, sy, sz, tx, ty, tz):
    c = UsdGeom.Cube.Define(stage, path)
    xf = UsdGeom.Xformable(c)
    xf.AddScaleOp().Set(Gf.Vec3f(sx, sy, sz))         # scale 먼저
    xf.AddTranslateOp().Set(Gf.Vec3d(tx, ty, tz))     # 그다음 translate
    c.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(0.05, 0.05, 0.07)]))
    return c

S = gd * 0.018                                        # 드론 크기(상대)
P = V(c1, c2, top*1.15)                               # 드론 위치(도시 위)
# 위치=부모(/Drone) translate만, 회전=자식(/Drone/tilt) — op 합성순서 혼선 방지
drone = UsdGeom.Xform.Define(stage, "/Drone")
UsdGeom.Xformable(drone).AddTranslateOp().Set(Gf.Vec3d(*P))
tilt = UsdGeom.Xform.Define(stage, "/Drone/tilt")
txf = UsdGeom.Xformable(tilt)
if up == 'Y':
    txf.AddRotateXOp().Set(-90.0)                     # 로컬 Z-up → 월드 Y-up
txf.AddRotateYOp().Set(25.0)                          # 뱅크(엣지온 방지)
cube("/Drone/tilt/body", S*0.45, S*0.45, S*0.16)
cube("/Drone/tilt/arm_x", S*1.0, S*0.07, S*0.05)
cube("/Drone/tilt/arm_y", S*0.07, S*1.0, S*0.05)
L = S*0.85
for nm, tx, ty in [("r0", L, 0), ("r1", -L, 0), ("r2", 0, L), ("r3", 0, -L)]:
    cube_at(f"/Drone/tilt/{nm}", S*0.3, S*0.3, S*0.04, tx, ty, S*0.08)
app.update(); app.update()
_dr = cache.ComputeWorldBound(stage.GetPrimAtPath("/Drone")).ComputeAlignedRange()
log(f"드론 목표P={tuple(round(v,1) for v in P)} 실제bbox={tuple(round(v,1) for v in _dr.GetMin())}~{tuple(round(v,1) for v in _dr.GetMax())} S={S:.2f}")

# semantic
try:
    from isaacsim.core.utils.semantics import add_update_semantics
    add_update_semantics(stage.GetPrimAtPath("/Drone"), "drone")
    log("semantic 'drone' 적용")
except Exception as e:
    log(f"semantic 스킵: {e}")

# ── 카메라: 도시 위에서 드론 내려다보기(드론 윗면+도시 배경) ─────────────────
shots = [
    ("overcity", V(c1 - gd*0.12, c2 - gd*0.45, top*2.1), P, 40.0),  # 높이 내려다봄
    ("approach", V(c1 + gd*0.10, c2 - gd*0.32, top*1.7), P, 50.0),  # 더 가까이, 여전히 위
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
        Image.fromarray(data[:, :, :3]).save(os.path.join(OUT, f"antidrone_{name}.png"))
        log(f"저장: antidrone_{name}.png")
    else:
        log(f"[경고] {name} RGB 없음")
    rgb.detach()
log("=== 완료 ===")
app.close()
