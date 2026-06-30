"""동결버그 스파이크: 무거운 도시씬에서 드론을 매 프레임 '이동+회전'.
METHOD=usd  → 기존 방식(USD xformOp.Set) = ~17-20스텝서 동결 예상(베이스라인 재확인)
METHOD=fabric → USDRT/Fabric 쓰기 = 동결 회피되면 30/30 유지(=해법)
박스가 매 스텝 갱신되면 OK, 옛 위치 고정(box=N 또는 npx 정지)이면 동결."""
import os
METHOD = os.environ.get("METHOD", "fabric")
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1280, "height": 720})
import math, numpy as np
from pxr import UsdGeom, UsdLux, Gf, Vt, Usd
import omni.usd
import omni.replicator.core as rep

OUT = "/home/karma/OSMtoUSD/poc_city_render"
LOG = f"{OUT}/run_mintest6_{METHOD}.log"
def log(m): print(m, flush=True); open(LOG, "a").write(str(m)+"\n")
open(LOG, "w").close()
W, H, HAP = 1280, 720, 36.0
ui, g1, g2 = 1, 0, 2; _wup = Gf.Vec3d(0, 1, 0)
def focal_of(h): return (HAP/2)/math.tan(math.radians(h)/2)

omni.usd.get_context().open_stage("/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.usd")
for _ in range(15): app.update()
stage = omni.usd.get_context().get_stage()
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange(); mn, mx = rng.GetMin(), rng.GetMax()
c1 = (mn[g1]+mx[g1])/2; c2 = (mn[g2]+mx[g2])/2; top = mx[ui]; ground = mn[ui]
gd = ((mx[g1]-mn[g1])**2+(mx[g2]-mn[g2])**2)**0.5
UsdLux.DistantLight.Define(stage, "/Sun").CreateIntensityAttr(3500.0)
dm = UsdLux.DomeLight.Define(stage, "/Sky"); dm.CreateIntensityAttr(1000.0)

cube = UsdGeom.Cube.Define(stage, "/Drone"); xf = UsdGeom.Xformable(cube)
top_op = xf.AddTranslateOp(); rot_op = xf.AddRotateXYZOp(); xf.AddScaleOp().Set(Gf.Vec3f(gd*0.02, gd*0.02, gd*0.02))
cube.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(0.9, 0.1, 0.1)]))
from isaacsim.core.utils.semantics import add_update_semantics
add_update_semantics(stage.GetPrimAtPath("/Drone"), "drone")

hfov = 60.0; thw = math.tan(math.radians(hfov)/2)
ep = [0, 0, 0]; Rr = gd*0.85; ep[g1] = c1+Rr; ep[g2] = c2; ep[ui] = max(ground, 0)+top*0.2; eye = Gf.Vec3d(*ep)
Lp = [0, 0, 0]; Lp[g1] = c1; Lp[g2] = c2; Lp[ui] = top*1.4
cam = rep.create.camera(position=tuple(eye), look_at=tuple(Lp), focal_length=focal_of(hfov), horizontal_aperture=HAP, clipping_range=(0.05, 1e8))
rp = rep.create.render_product(cam, (W, H))
box = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
seg = rep.AnnotatorRegistry.get_annotator("semantic_segmentation", init_params={"colorize": False})
for a in (box, seg): a.attach([rp])
f = (Gf.Vec3d(*Lp)-eye); f = f/f.GetLength(); r = Gf.Cross(f, _wup); r = r/r.GetLength(); u = Gf.Cross(r, f)
D = gd*0.3; hw = D*thw; hh = hw*H/W

rt_t = rt_r = None
if METHOD == "fabric":
    try:
        import usdrt
        from usdrt import Usd as RtUsd, Gf as RtGf, Sdf as RtSdf
        for _ in range(3): app.update()
        sid = omni.usd.get_context().get_stage_id()
        rt_stage = RtUsd.Stage.Attach(sid)
        rt_drone = rt_stage.GetPrimAtPath("/Drone")
        rt_t = rt_drone.GetAttribute("xformOp:translate")
        rt_r = rt_drone.GetAttribute("xformOp:rotateXYZ")
        log(f"USDRT attach OK | translate attr valid={rt_t.IsValid() if rt_t else None} rotate valid={rt_r.IsValid() if rt_r else None}")
        _RtGf = RtGf
    except Exception as e:
        log(f"USDRT 실패 → USD로 폴백: {e}"); METHOD = "usd"

prev_npx = -1; frozen_at = None
for i in range(30):
    ox = ((i-15)/15.0)*0.6*hw; oy = math.sin(i*0.4)*0.4*hh
    pos = Gf.Vec3d(eye[0]+f[0]*D+r[0]*ox+u[0]*oy, eye[1]+f[1]*D+r[1]*ox+u[1]*oy, eye[2]+f[2]*D+r[2]*ox+u[2]*oy)
    rot = (i*12.0 % 360, i*23.0 % 360, i*7.0 % 360)
    if METHOD == "fabric" and rt_t is not None:
        try:
            rt_t.Set(_RtGf.Vec3d(pos[0], pos[1], pos[2]))
            if rt_r and rt_r.IsValid(): rt_r.Set(_RtGf.Vec3f(*rot))
        except Exception as e:
            log(f"fabric write 실패: {e}"); break
    else:
        top_op.Set(pos); rot_op.Set(Gf.Vec3f(*rot))
    for _ in range(6): app.update()
    rep.orchestrator.step(rt_subframes=10); app.update()
    sg = seg.get_data(); sd = np.asarray(sg["data"]); s2 = sg["info"]["idToLabels"]
    dids = [int(k) for k, v in s2.items() if "drone" in str(v).lower()]
    npx = int(np.isin(sd, dids).sum())
    bb = box.get_data(); found = bb["data"] is not None and len(bb["data"]) > 0
    moved = "Y" if npx != prev_npx else "STUCK"; prev_npx = npx
    if moved == "STUCK" and npx > 0 and frozen_at is None and i > 2: frozen_at = i
    log(f"step{i:02d}: box={'Y' if found else 'N'} npx={npx} {moved}")
log(f"=== METHOD={METHOD} | 동결시작 step={frozen_at} (None이면 30/30 정상=해법) ===")
app.close()
