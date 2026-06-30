"""모든 드론 모델 임포트 → 하늘배경에 한 장씩 렌더(어떤 모델이 이상한지 확인용).
inline(Sdf.CopySpec) 방식으로 geom 복사 — 참조 컷오프/누락 회피. 각 드론 stage 새로 열어 깨끗하게."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 900, "height": 600})
import os, numpy as np, carb
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf, Sdf
import omni.usd, omni.replicator.core as rep

DRONES = {
    "phantom":    "/home/karma/OSMtoUSD/assets/drones/phantom.usd",
    "iris":       "/home/karma/OSMtoUSD/assets/drones/iris_quad.usd",
    "px4vision":  "/home/karma/OSMtoUSD/assets/drones/px4vision_quad.usd",
    "tailsitter": "/home/karma/OSMtoUSD/assets/drones/tailsitter_vtol.usd",
    "techpod":    "/home/karma/OSMtoUSD/assets/drones/techpod_plane.usd",
}
OUTDIR = "/home/karma/OSMtoUSD/poc_city_render/drone_shots"
os.makedirs(OUTDIR, exist_ok=True)
W, H = 900, 600
HDRI = "/home/karma/OSMtoUSD/assets/hdri/sky_kloofendal_43d_clear_ps.hdr"
s = carb.settings.get_settings(); s.set("/rtx/rendermode", "RaytracedLighting")

for name, usd in DRONES.items():
    omni.usd.get_context().new_stage()
    for _ in range(8): app.update()
    stage = omni.usd.get_context().get_stage()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    dome = UsdLux.DomeLight.Define(stage, "/Sky")
    dome.CreateIntensityAttr(1200)
    if os.path.exists(HDRI): dome.CreateTextureFileAttr(HDRI)

    # inline 복사
    drone = UsdGeom.Xform.Define(stage, "/Drone")
    dx = UsdGeom.Xformable(drone)
    rotop = dx.AddRotateXYZOp(); scop = dx.AddScaleOp()
    try:
        _src = Usd.Stage.Open(usd); _flat = _src.Flatten()
        _sdp = (_src.GetDefaultPrim().GetPath() if _src.GetDefaultPrim()
                else next(iter(_src.GetPseudoRoot().GetChildren())).GetPath())
        geom = stage.DefinePrim("/Drone/geom", "Xform")
        Sdf.CopySpec(_flat, _sdp, stage.GetRootLayer(), Sdf.Path("/Drone/geom"))
        mode = "inline"
    except Exception as e:
        drone.GetPrim().GetReferences().AddReference(usd)
        mode = f"ref({e})"
    for _ in range(60): app.update()

    # 크기 정규화 → 화면에 꽉
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    rng = cache.ComputeWorldBound(drone.GetPrim()).ComputeAlignedRange()
    mn, mx = rng.GetMin(), rng.GetMax()
    ext = max((mx[i]-mn[i]) for i in range(3)) or 1.0
    scop.Set(Gf.Vec3f(3.0/ext, 3.0/ext, 3.0/ext))
    rotop.Set(Gf.Vec3f(15, 0, 35))  # 살짝 기울여 형태 보이게
    for _ in range(20): app.update()

    cam = rep.create.camera(position=(0, -7, 1.0), look_at=(0, 0, 0))
    rp = rep.create.render_product(cam, (W, H))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb"); rgb.attach([rp])
    for _ in range(5): app.update()
    rep.orchestrator.step(rt_subframes=32); app.update()
    arr = np.array(rgb.get_data()[:, :, :3])
    Image.fromarray(arr).save(f"{OUTDIR}/{name}.png")
    print(f"[{name}] mode={mode} ext={ext:.3f} mean={arr.mean():.1f} -> {name}.png", flush=True)

print("ALL_DONE", flush=True)
app.close()
