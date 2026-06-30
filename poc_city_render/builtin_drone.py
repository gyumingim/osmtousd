"""Isaac 기본 드론 에셋 탐색 + 단독 렌더. 서버 카탈로그 조회 → 드론 후보 참조 → 렌더."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1280, "height": 1280})
import os
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf
import omni.usd, omni.client
import omni.replicator.core as rep

OUT = "/home/karma/OSMtoUSD/poc_city_render"
def log(m): print(m, flush=True); open(os.path.join(OUT,"run_builtin.log"),"a").write(str(m)+"\n")
open(os.path.join(OUT,"run_builtin.log"),"w").close()

try:
    from isaacsim.storage.native import get_assets_root_path
except Exception:
    from omni.isaac.nucleus import get_assets_root_path
root = get_assets_root_path()
log(f"assets_root = {root}")

def listing(url):
    r, ents = omni.client.list(url)
    return [e.relative_path for e in ents] if str(r) == "Result.OK" else []

# /Isaac/Robots 카탈로그
robots = listing(root + "/Isaac/Robots")
log(f"/Isaac/Robots ({len(robots)}): {robots}")
# 드론 키워드 폴더 + 드론 제조 벤더(폴더가 벤더명이라 키워드 누락 방지)
kw = ("crazy", "quad", "drone", "copter", "uav", "iris", "fly", "ingenuity")
forced = ("bitcraze", "nasa", "isaacsim", "nvidia")
drone_dirs = [d for d in robots if any(k in d.lower() for k in kw) or d.rstrip("/").lower() in forced]
log(f"드론 후보 폴더: {drone_dirs}")

# 재귀 탐색(폴더 trailing-slash 의존 X)
def walk(base, depth):
    found = []
    r, ents = omni.client.list(base)
    if str(r) != "Result.OK": return found
    for e in ents:
        nm = e.relative_path.rstrip("/")
        full = base + "/" + nm
        if nm.lower().endswith((".usd", ".usda", ".usdc")):
            found.append(full)
        elif depth > 0 and "." not in nm:
            found += walk(full, depth - 1)
    return found

candidates = []
for d in drone_dirs:
    base = root + "/Isaac/Robots/" + d.rstrip("/")
    fnd = walk(base, 2)
    log(f"  {d}: {[c.split('/')[-1] for c in fnd][:12]}")
    candidates += fnd
def score(p):
    pl = p.lower()
    for i, k in enumerate(("crazyflie", "cf2", "quad", "drone", "copter", "ingenuity")):
        if k in pl: return i
    return 99
candidates.sort(key=score)
log(f"드론 USD 후보({len(candidates)}) 정렬후 top: {[c.split('/')[-1] for c in candidates[:8]]}")

if not candidates:
    log("[중단] 드론 USD 못 찾음"); app.close(); raise SystemExit(0)

# 첫 후보 참조 + 렌더
pick = candidates[0]
log(f"선택: {pick}")
stage = omni.usd.get_context().get_stage() or omni.usd.get_context().new_stage()
omni.usd.get_context().new_stage()
for _ in range(5): app.update()
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
d = UsdGeom.Xform.Define(stage, "/Drone")
d.GetPrim().GetReferences().AddReference(pick)
# 로드 대기(에셋 스트리밍 — 고정 프레임)
for _ in range(150):
    app.update()

sun = UsdLux.DistantLight.Define(stage, "/L_Sun"); sun.CreateIntensityAttr(2500.0)
UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-35,25,15))
dome = UsdLux.DomeLight.Define(stage, "/L_Sky"); dome.CreateIntensityAttr(1200.0)
dome.CreateColorAttr(Gf.Vec3f(0.85,0.86,0.9))

cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
rng = cache.ComputeWorldBound(stage.GetPrimAtPath("/Drone")).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax()
C = Gf.Vec3d((mn[0]+mx[0])/2,(mn[1]+mx[1])/2,(mn[2]+mx[2])/2)
R = (Gf.Vec3d(*mx)-Gf.Vec3d(*mn)).GetLength()/2 or 1.0
log(f"드론 bbox min={tuple(round(v,3) for v in mn)} max={tuple(round(v,3) for v in mx)} R={R:.3f}")

for name, vd in [("3q", Gf.Vec3d(0.8,-0.8,0.5)), ("side", Gf.Vec3d(1,-0.1,0.15))]:
    pos = C + vd.GetNormalized()*(R*2.4)
    cam = rep.create.camera(position=(pos[0],pos[1],pos[2]), look_at=(C[0],C[1],C[2]), focal_length=50.0, clipping_range=(0.001, 1000.0))
    rp = rep.create.render_product(cam, (1280,1280))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb"); rgb.attach([rp])
    for _ in range(10): app.update()
    rep.orchestrator.step(rt_subframes=24); app.update()
    dt = rgb.get_data()
    if dt is not None and len(dt)>0:
        Image.fromarray(dt[:,:,:3]).save(os.path.join(OUT, f"builtin_{name}.png")); log(f"저장: builtin_{name}.png")
    rgb.detach()
log("=== 완료 ===")
app.close()
