"""변환된 환경 USD 미리보기 렌더 (텍스처/지오메트리 확인)."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1024, "height": 640})
import os, math, numpy as np, carb
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf
import omni.usd, omni.replicator.core as rep

HDRI = "/home/karma/OSMtoUSD/assets/hdri/sky_kloofendal_43d_clear_ps.hdr"
OUT = "/home/karma/OSMtoUSD/poc_city_render/env_shots"
os.makedirs(OUT, exist_ok=True)
W, H = 1024, 640
ENVS = {"airport": "/home/karma/OSMtoUSD/assets/env_airport/airport.usd",
        "tree": "/home/karma/OSMtoUSD/assets/env_forest/tree.usd"}
s = carb.settings.get_settings(); s.set("/rtx/rendermode", "RaytracedLighting")

for name, usd in ENVS.items():
    omni.usd.get_context().new_stage()
    for _ in range(8): app.update()
    stage = omni.usd.get_context().get_stage()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    dome = UsdLux.DomeLight.Define(stage, "/Sky"); dome.CreateIntensityAttr(900)
    dome.CreateTextureFileAttr(HDRI)
    env = UsdGeom.Xform.Define(stage, "/Env")
    env.GetPrim().GetReferences().AddReference(usd)
    for _ in range(60): app.update()
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    rng = cache.ComputeWorldBound(env.GetPrim()).ComputeAlignedRange()
    mn, mx = rng.GetMin(), rng.GetMax()
    c = [(mn[i]+mx[i])/2 for i in range(3)]
    ext = max((mx[i]-mn[i]) for i in range(3)) or 1.0
    # 카메라: 비스듬히 내려다보며 전체 프레임
    d = ext*1.4
    eye = (c[0]+d*0.7, c[1]+ext*0.5, c[2]+d*0.7)
    cam = rep.create.camera(position=eye, look_at=(c[0], c[1], c[2]))
    rp = rep.create.render_product(cam, (W, H))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb"); rgb.attach([rp])
    for _ in range(5): app.update()
    rep.orchestrator.step(rt_subframes=28); app.update()
    arr = np.array(rgb.get_data()[:, :, :3])
    Image.fromarray(arr).save(f"{OUT}/{name}.png")
    print(f"[{name}] ext={ext:.1f} mean={arr.mean():.1f} -> {name}.png", flush=True)

print("PREVIEW_DONE", flush=True)
app.close()
