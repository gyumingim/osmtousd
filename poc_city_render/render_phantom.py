"""압축된 phantom.usd(115k, 재질색) → 하늘배경 여러각도 렌더 (Isaac 가벼움)."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1280, "height": 720})
import os, numpy as np, carb
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf
import omni.usd, omni.replicator.core as rep
USD = "/home/karma/OSMtoUSD/assets/drones/phantom.usd"
OUTDIR = "/home/karma/OSMtoUSD/poc_city_render/phantom_shots"
os.makedirs(OUTDIR, exist_ok=True)
W, H = 1280, 720
s = carb.settings.get_settings(); s.set("/rtx/rendermode", "RaytracedLighting")
omni.usd.get_context().new_stage()
for _ in range(10): app.update()
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
HDRI = "/home/karma/OSMtoUSD/assets/hdri/sky_kloofendal_43d_clear_ps.hdr"
dome = UsdLux.DomeLight.Define(stage, "/Sky"); dome.CreateIntensityAttr(1200); dome.CreateTextureFileAttr(HDRI)

drone = UsdGeom.Xform.Define(stage, "/Drone"); dx = UsdGeom.Xformable(drone)
rotop = dx.AddRotateXYZOp(); scop = dx.AddScaleOp()
drone.GetPrim().GetReferences().AddReference(USD)
for _ in range(120): app.update()
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
rng = cache.ComputeWorldBound(drone.GetPrim()).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax(); ext = max(mx[i]-mn[i] for i in range(3))
print("로드 ext:", round(ext, 3), flush=True)
scop.Set(Gf.Vec3f(3.0/ext, 3.0/ext, 3.0/ext))

cam = rep.create.camera(position=(0, -7, 1.2), look_at=(0, 0, 0))
rp = rep.create.render_product(cam, (W, H))
rgb = rep.AnnotatorRegistry.get_annotator("rgb"); rgb.attach([rp])
for a in (rgb,): a.attach([rp])

angles = [(0, 0, 0), (10, 0, 50), (20, 0, 130), (30, 0, 210), (15, 0, 300), (0, 0, 90)]
for i, (rx, ry, rz) in enumerate(angles):
    rotop.Set(Gf.Vec3f(rx, ry, rz))
    for _ in range(5): app.update()
    rep.orchestrator.step(rt_subframes=28); app.update()
    Image.fromarray(np.array(rgb.get_data()[:, :, :3])).save(f"{OUTDIR}/phantom_{i}.png")
    print(f"  shot {i}", flush=True)
print("렌더완료", flush=True)
app.close()
