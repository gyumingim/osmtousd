"""격리실험4: 실제 cf2x 쿼드 setup(중첩 rs/centered + rop 회전) + 정중앙 배치 + 도시.
실패→쿼드/회전 범인. 성공→궤적 오프셋 범인."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1280, "height": 720})
import os, math, random, numpy as np
from PIL import Image
from pxr import UsdGeom, UsdLux, Gf, Usd
import omni.usd
import omni.replicator.core as rep
from isaacsim.storage.native import get_assets_root_path

OUT = "/home/karma/OSMtoUSD/poc_city_render"
def log(m): print(m, flush=True); open(OUT+"/run_mintest4.log", "a").write(str(m)+"\n")
open(OUT+"/run_mintest4.log", "w").close()
W, H, HAP = 1280, 720, 36.0
ui, g1, g2 = 1, 0, 2
_wup = Gf.Vec3d(0, 1, 0)
def focal_of(h): return (HAP/2)/math.tan(math.radians(h)/2)
random.seed(20)

omni.usd.get_context().open_stage("/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.usd")
for _ in range(15): app.update()
stage = omni.usd.get_context().get_stage()
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange(); mn, mx = rng.GetMin(), rng.GetMax()
c1 = (mn[g1]+mx[g1])/2; c2 = (mn[g2]+mx[g2])/2; top = mx[ui]; ground = mn[ui]
gd = ((mx[g1]-mn[g1])**2+(mx[g2]-mn[g2])**2)**0.5
UsdLux.DistantLight.Define(stage, "/Sun").CreateIntensityAttr(3500.0)
dm = UsdLux.DomeLight.Define(stage, "/Sky"); dm.CreateIntensityAttr(1000.0); dm.CreateColorAttr(Gf.Vec3f(0.6, 0.7, 0.95))

QUAD = get_assets_root_path()+"/Isaac/Robots/Bitcraze/Crazyflie/cf2x.usd"
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
UPX = -90.0
log(f"mext={mext:.3f} S_world={S_world:.1f}")

sensor = UsdGeom.Camera.Define(stage, "/SensorCam")
sensor.CreateClippingRangeAttr(Gf.Vec2f(0.05, 1e8)); sensor.CreateHorizontalApertureAttr(HAP); sensor.CreateVerticalApertureAttr(HAP*H/W)
s_fl = sensor.CreateFocalLengthAttr(35.0); s_xf = UsdGeom.Xformable(sensor.GetPrim()).AddTransformOp()
rp = rep.create.render_product("/SensorCam", (W, H))
rgb = rep.AnnotatorRegistry.get_annotator("rgb"); box = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
seg = rep.AnnotatorRegistry.get_annotator("semantic_segmentation", init_params={"colorize": False})
for a in (rgb, box, seg): a.attach([rp])

def look_basis(eye, tgt):
    f = (tgt-eye); f = f/f.GetLength(); r = Gf.Cross(f, _wup); r = r/r.GetLength(); u = Gf.Cross(r, f); return f, r, u
def set_cam(eye, f, r, u):
    M = Gf.Matrix4d(); M.SetRow(0, Gf.Vec4d(r[0], r[1], r[2], 0)); M.SetRow(1, Gf.Vec4d(u[0], u[1], u[2], 0))
    M.SetRow(2, Gf.Vec4d(-f[0], -f[1], -f[2], 0)); M.SetRow(3, Gf.Vec4d(eye[0], eye[1], eye[2], 1)); s_xf.Set(M)

for sq in range(12):
    bg = "building" if random.random() < 0.6 else "sky"
    hfov = 60.0; thw = math.tan(math.radians(hfov)/2); s_fl.Set(focal_of(hfov))
    Rr = gd*0.85; ang = random.uniform(0, 2*math.pi); ep = [0, 0, 0]
    ep[g1] = c1+Rr*math.cos(ang); ep[g2] = c2+Rr*math.sin(ang); ep[ui] = max(ground, 0)+top*0.2; eye = Gf.Vec3d(*ep)
    Lp = [0, 0, 0]; Lp[g1] = c1; Lp[g2] = c2; Lp[ui] = top*(1.1 if bg == "building" else 2.0)
    f, r, u = look_basis(eye, Gf.Vec3d(*Lp)); set_cam(eye, f, r, u)
    D = gd*random.uniform(0.18, 0.45); hw = D*thw; hh = hw*H/W
    o0 = (random.uniform(-0.35, 0.35)*hw, random.uniform(-0.30, 0.30)*hh)
    vel = (random.uniform(-0.08, 0.08)*hw, random.uniform(-0.07, 0.07)*hh)
    for fr in range(8):
        ox = o0[0]+vel[0]*fr; oy = o0[1]+vel[1]*fr
        ox = max(-0.85*hw, min(0.85*hw, ox)); oy = max(-0.85*hh, min(0.85*hh, oy))
        d3 = Gf.Vec3d(eye[0]+f[0]*D+r[0]*ox+u[0]*oy, eye[1]+f[1]*D+r[1]*ox+u[1]*oy, eye[2]+f[2]*D+r[2]*ox+u[2]*oy)
        dpos.Set(d3); rop.Set(Gf.Vec3f(UPX+random.uniform(-10, 10), (sq*37+fr*12) % 360, random.uniform(-12, 12)))
        for _ in range(6): app.update()
        rep.orchestrator.step(rt_subframes=10); app.update()
        bb = box.get_data(); sg = seg.get_data(); sd = np.asarray(sg["data"]); s2 = sg["info"]["idToLabels"]
        dids = [int(k) for k, v in s2.items() if "drone" in str(v).lower()]; npx = int(np.isin(sd, dids).sum())
        su = ox/hw; sv = oy/hh; found = bb["data"] is not None and len(bb["data"]) > 0
        log(f"sq{sq:02d}{bg[:3]} f{fr}: su={su:+.2f} sv={sv:+.2f} box={'Y' if found else 'N'} npx={npx}")
log("done"); app.close()
