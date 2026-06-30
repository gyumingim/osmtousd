"""동결 재현 정밀화: 실제 참조 드론(cf2x) + 매 프레임 회전(MODE=dronerot) / 카메라 이동(MODE=cammove).
generator와 동일 구조(참조+중심정렬+스케일). 박스 npx가 매 스텝 변하면 OK, 정지=동결."""
import os
MODE = os.environ.get("MODE", "dronerot")
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1280, "height": 720})
import math, numpy as np
from pxr import UsdGeom, UsdLux, Gf, Usd
import omni.usd
import omni.replicator.core as rep
from isaacsim.storage.native import get_assets_root_path

OUT = "/home/karma/OSMtoUSD/poc_city_render"; LOG = f"{OUT}/run_mt7_{MODE}.log"
def log(m): print(m, flush=True); open(LOG, "a").write(str(m)+"\n")
open(LOG, "w").close()
W, H, HAP = 1280, 720, 36.0; ui, g1, g2 = 1, 0, 2; _wup = Gf.Vec3d(0, 1, 0)
def focal_of(h): return (HAP/2)/math.tan(math.radians(h)/2)
QUAD = get_assets_root_path() + "/Isaac/Robots/Bitcraze/Crazyflie/cf2x.usd"

omni.usd.get_context().open_stage("/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.usd")
for _ in range(15): app.update()
stage = omni.usd.get_context().get_stage()
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange(); mn, mx = rng.GetMin(), rng.GetMax()
c1 = (mn[g1]+mx[g1])/2; c2 = (mn[g2]+mx[g2])/2; top = mx[ui]; ground = mn[ui]
gd = ((mx[g1]-mn[g1])**2+(mx[g2]-mn[g2])**2)**0.5
UsdLux.DistantLight.Define(stage, "/Sun").CreateIntensityAttr(3500.0)
UsdLux.DomeLight.Define(stage, "/Sky").CreateIntensityAttr(1000.0)

drone = UsdGeom.Xform.Define(stage, "/Drone"); dpos = UsdGeom.Xformable(drone).AddTranslateOp()
rs = UsdGeom.Xform.Define(stage, "/Drone/rs"); rsx = UsdGeom.Xformable(rs); sop = rsx.AddScaleOp(); rop = rsx.AddRotateXYZOp()
cen = UsdGeom.Xform.Define(stage, "/Drone/rs/centered"); cop = UsdGeom.Xformable(cen).AddTranslateOp()
cen.GetPrim().GetReferences().AddReference(QUAD)
for _ in range(120): app.update()
mb = cache.ComputeWorldBound(stage.GetPrimAtPath("/Drone/rs/centered")).ComputeAlignedRange()
mmn, mmx = mb.GetMin(), mb.GetMax(); mc = [(mmn[i]+mmx[i])/2 for i in range(3)]; mext = max(mmx[i]-mmn[i] for i in range(3))
cop.Set(Gf.Vec3d(-mc[0], -mc[1], -mc[2])); S_world = gd*0.03; sop.Set(Gf.Vec3f(S_world/mext, S_world/mext, S_world/mext))
from isaacsim.core.utils.semantics import add_update_semantics
add_update_semantics(stage.GetPrimAtPath("/Drone"), "drone")

hfov = 60.0; thw = math.tan(math.radians(hfov)/2)
ep = [0, 0, 0]; Rr = gd*0.85; ep[g1] = c1+Rr; ep[g2] = c2; ep[ui] = max(ground, 0)+top*0.2; eye = Gf.Vec3d(*ep)
Lp = [0, 0, 0]; Lp[g1] = c1; Lp[g2] = c2; Lp[ui] = top*1.4
cam = rep.create.camera(position=tuple(eye), look_at=tuple(Lp), focal_length=focal_of(hfov), horizontal_aperture=HAP, clipping_range=(0.05, 1e8))
rp = rep.create.render_product(cam, (W, H))
for _ in range(5): app.update()
cam_t = None
if MODE == "cammove":
    for p in stage.Traverse():
        if p.IsA(UsdGeom.Camera):
            cxf = UsdGeom.Xformable(p)
            for op in cxf.GetOrderedXformOps():
                if op.GetOpType() == UsdGeom.XformOp.TypeTranslate: cam_t = op
            if cam_t is None: cam_t = cxf.AddTranslateOp()
            log(f"camera prim: {p.GetPath()}"); break
    if cam_t is None: log("카메라 prim 못찾음")
seg = rep.AnnotatorRegistry.get_annotator("semantic_segmentation", init_params={"colorize": False})
box = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight");
for a in (box, seg): a.attach([rp])
f = (Gf.Vec3d(*Lp)-eye); f = f/f.GetLength(); r = Gf.Cross(f, _wup); r = r/r.GetLength(); u = Gf.Cross(r, f)
D = gd*0.3; hw = D*thw; hh = hw*H/W
dpos.Set(Gf.Vec3d(eye[0]+f[0]*D, eye[1]+f[1]*D, eye[2]+f[2]*D)); rop.Set(Gf.Vec3f(-90, 0, 0))
log(f"MODE={MODE}")

prev = -1; frozen = None
for i in range(30):
    if MODE == "dronerot":
        ox = ((i-15)/15.0)*0.5*hw; oy = math.sin(i*0.4)*0.35*hh
        dpos.Set(Gf.Vec3d(eye[0]+f[0]*D+r[0]*ox+u[0]*oy, eye[1]+f[1]*D+r[1]*ox+u[1]*oy, eye[2]+f[2]*D+r[2]*ox+u[2]*oy))
        rop.Set(Gf.Vec3f(-90+math.sin(i*0.3)*30, i*15.0 % 360, math.cos(i*0.3)*20))   # 매 프레임 회전
    elif MODE == "cammove":                                                            # 카메라 좌우 패닝
        pan = math.sin(i*0.2)*gd*0.15
        cam_t.Set(Gf.Vec3d(eye[0]+r[0]*pan, eye[1]+r[1]*pan, eye[2]+r[2]*pan))
    for _ in range(6): app.update()
    rep.orchestrator.step(rt_subframes=12); app.update()
    sg = seg.get_data(); sd = np.asarray(sg["data"]); s2 = sg["info"]["idToLabels"]
    dids = [int(k) for k, v in s2.items() if "drone" in str(v).lower()]; npx = int(np.isin(sd, dids).sum())
    bb = box.get_data(); found = bb["data"] is not None and len(bb["data"]) > 0
    st = "Y" if npx != prev else "STUCK"; prev = npx
    if st == "STUCK" and frozen is None and i > 2: frozen = i
    log(f"step{i:02d}: box={'Y' if found else 'N'} npx={npx} {st}")
log(f"=== MODE={MODE} | 동결시작 step={frozen} (None=30/30 정상) ===")
app.close()
