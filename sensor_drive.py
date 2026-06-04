from isaacsim import SimulationApp
# enable_motion_bvh: RTX 센서가 씬을 트레이스하는 가속구조 — 필수
app = SimulationApp({"headless": True, "enable_motion_bvh": True})

import os
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw
from pxr import UsdGeom, UsdLux, UsdPhysics, Gf, Sdf

import omni
import omni.kit.commands
import omni.replicator.core as rep
from isaacsim.core.utils.stage import open_stage, is_stage_loading
from isaacsim.core.api import SimulationContext
from isaacsim.sensors.rtx import LidarRtx, get_gmo_data
from isaacsim.sensors.physx import _range_sensor

STAGE_PATH = "/home/karma/OSMtoUSD/gumi.usda"
OUTPUT_DIR = "/home/karma/OSMtoUSD/output"
SPEED_MPS  = 100 / 3.6
DT         = 1.0 / 10
DIST_STEP  = SPEED_MPS * DT
NUM_FRAMES = 10
CAM_W, CAM_H = 640, 360
LIDAR_CONFIG = "Example_Rotary"   # 여러 예제에서 검증된 config

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── 1. 씬 직접 로드 ───────────────────────────────────────────────────────────
print("씬 로드...")
open_stage(STAGE_PATH)
while is_stage_loading():
    app.update()
for _ in range(5):
    app.update()
stage = omni.usd.get_context().get_stage()
print("씬 로드 완료")

# ── 2. SimulationContext + PhysicsScene 보장 ─────────────────────────────────
if not stage.GetPrimAtPath("/World/PhysicsScene").IsValid():
    UsdPhysics.Scene.Define(stage, Sdf.Path("/World/PhysicsScene"))
sim_ctx = SimulationContext(stage_units_in_meters=1.0,
                            physics_dt=1.0 / 60, rendering_dt=1.0 / 60)

# ── 3. 조명 ───────────────────────────────────────────────────────────────────
dome = UsdLux.DomeLight.Define(stage, "/World/DomeLight")
dome.CreateIntensityAttr(800.0)
sun = UsdLux.DistantLight.Define(stage, "/World/SunLight")
sun.CreateIntensityAttr(3000.0)
UsdGeom.XformCommonAPI(sun).SetRotate(
    Gf.Vec3f(-45, 0, 45), UsdGeom.XformCommonAPI.RotationOrderXYZ)


# ── 4. 경로 추출 ──────────────────────────────────────────────────────────────
def build_path():
    rg = stage.GetPrimAtPath("/World/RoadGraph")
    if not rg.IsValid():
        return None
    best, best_len = None, 0.0
    for c in rg.GetChildren():
        pts = c.GetAttribute("points").Get()
        if pts is None or len(pts) < 2:
            continue
        pts = np.array(pts)
        seg = np.linalg.norm(np.diff(pts[:, :2], axis=0), axis=1).sum()
        if seg > best_len:
            best, best_len = pts, seg
    if best is None:
        return None
    d = np.concatenate([[0], np.cumsum(
        np.linalg.norm(np.diff(best[:, :2], axis=0), axis=1))])
    s   = np.linspace(0, min(d[-1], DIST_STEP * NUM_FRAMES), NUM_FRAMES + 1)
    wx  = np.interp(s, d, best[:, 0])
    wy  = np.interp(s, d, best[:, 1])
    wz  = np.interp(s, d, best[:, 2]) + 0.5
    dx  = np.diff(wx, append=wx[-1] + (wx[-1] - wx[-2]))
    dy  = np.diff(wy, append=wy[-1] + (wy[-1] - wy[-2]))
    yaw = np.degrees(np.arctan2(dy, dx))
    return list(zip(wx, wy, wz, yaw))


waypoints = build_path()
if waypoints is None:
    waypoints = [(i * DIST_STEP, 0.0, 0.5, 0.0) for i in range(NUM_FRAMES + 1)]
x0, y0, z0, yaw0 = waypoints[0]
print(f"경로 {len(waypoints)}개  시작=({x0:.1f}, {y0:.1f})")

# ── 5. 에고 차량 ──────────────────────────────────────────────────────────────
ego_path = "/World/EgoVehicle"
ego_prim = UsdGeom.Xform.Define(stage, ego_path)


def move_ego(x, y, z, yaw_deg):
    api = UsdGeom.XformCommonAPI(ego_prim)
    api.SetTranslate(Gf.Vec3d(x, y, z))
    api.SetRotate(Gf.Vec3f(0, 0, yaw_deg),
                  UsdGeom.XformCommonAPI.RotationOrderXYZ)


move_ego(x0, y0, z0, yaw0)

# ── 6. 카메라 4대 (작동 확인됨) ──────────────────────────────────────────────
_CAM_LOCAL = {
    "front": {"pos": (2.0,  0.0, 1.5), "dir": (1,  0, 0)},
    "back":  {"pos": (-2.0, 0.0, 1.5), "dir": (-1, 0, 0)},
    "left":  {"pos": (0.0,  1.5, 1.5), "dir": (0,  1, 0)},
    "right": {"pos": (0.0, -1.5, 1.5), "dir": (0, -1, 0)},
}


def cam_pose(name, ex, ey, ez, yaw_deg):
    yr = np.radians(yaw_deg)
    px, py, pz = _CAM_LOCAL[name]["pos"]
    lx, ly, _  = _CAM_LOCAL[name]["dir"]
    cx = ex + px * np.cos(yr) - py * np.sin(yr)
    cy = ey + px * np.sin(yr) + py * np.cos(yr)
    cz = ez + pz
    tx = cx + (lx * np.cos(yr) - ly * np.sin(yr)) * 20
    ty = cy + (lx * np.sin(yr) + ly * np.cos(yr)) * 20
    return (cx, cy, cz), (tx, ty, cz)


cameras, rgb_an, bbox_an = {}, {}, {}
for name in _CAM_LOCAL:
    pos, look = cam_pose(name, x0, y0, z0, yaw0)
    cam = rep.create.camera(position=pos, look_at=look, focal_length=18.0)
    rp  = rep.create.render_product(cam, (CAM_W, CAM_H))
    r   = rep.AnnotatorRegistry.get_annotator("rgb")
    b   = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
    r.attach([rp])
    b.attach([rp])
    cameras[name] = cam
    rgb_an[name]  = r
    bbox_an[name] = b
print("카메라 4대 생성")

# ── 7. 뷰포트 chase cam ───────────────────────────────────────────────────────
chase = UsdGeom.Camera.Define(stage, ego_path + "/ChaseCam")
UsdGeom.XformCommonAPI(chase).SetTranslate(Gf.Vec3d(-20, 0, 10))
UsdGeom.XformCommonAPI(chase).SetRotate(
    Gf.Vec3f(-25, 0, 0), UsdGeom.XformCommonAPI.RotationOrderXYZ)
chase.CreateFocalLengthAttr(24.0)
try:
    import omni.kit.viewport.utility as vpu
    vp = vpu.get_active_viewport()
    if vp:
        vp.camera_path = ego_path + "/ChaseCam"
except Exception:
    pass

# ── 8. LiDAR — 공식 패턴: LidarRtx 직접 생성 → OmniLidar 프림 ────────────────
lidar = LidarRtx(
    prim_path=ego_path + "/Lidar",
    name="lidar",
    translation=np.array([0.0, 0.0, 2.2]),
    orientation=np.array([1.0, 0.0, 0.0, 0.0]),
    config_file_name=LIDAR_CONFIG,
)
lidar.initialize()
lidar.attach_annotator("GenericModelOutput")
print("LiDAR 생성 (OmniLidar)")

# ── 9. Ultrasonic → PhysX LightBeam ×4 (RTX 초음파 config 없음 → 대체) ───────
ls_iface = _range_sensor.acquire_lightbeam_sensor_interface()
US_DEFS = [
    ("FL", Gf.Vec3d(3,  1, 0.5), Gf.Vec3d(1,  0.4, 0)),
    ("FR", Gf.Vec3d(3, -1, 0.5), Gf.Vec3d(1, -0.4, 0)),
    ("RL", Gf.Vec3d(-3, 1, 0.5), Gf.Vec3d(-1, 0.4, 0)),
    ("RR", Gf.Vec3d(-3,-1, 0.5), Gf.Vec3d(-1,-0.4, 0)),
]
us_paths = []
for label, trans, fwd in US_DEFS:
    spath = f"{ego_path}/US_{label}"
    omni.kit.commands.execute(
        "IsaacSensorCreateLightBeamSensor",
        path=f"/US_{label}",
        parent=ego_path,
        min_range=0.2,
        max_range=10.0,
        translation=trans,
        orientation=Gf.Quatd(1, 0, 0, 0),
        forward_axis=fwd,
        num_rays=3,
        curtain_length=0.5,
    )
    us_paths.append((label, spath))
print("LightBeam(초음파) 4개 생성")

# ── 10. 초기화 + 워밍업 ──────────────────────────────────────────────────────
sim_ctx.reset()
sim_ctx.play()
print("워밍업 (30 steps)...")
for _ in range(30):
    sim_ctx.step(render=True)
print("워밍업 완료")


# ── 파싱 ──────────────────────────────────────────────────────────────────────
def get_lidar_pts(fi):
    frame = lidar.get_current_frame()
    if fi == 0:
        print(f"  [LiDAR keys]: {list(frame.keys())}")
    data = frame.get("GenericModelOutput")
    if data is None or len(data) == 0:
        return None
    try:
        gmo = get_gmo_data(data)
        x = np.array(gmo.x)
        y = np.array(gmo.y)
        z = np.array(gmo.z)
        if len(x) > 0:
            return np.stack([x, y, z], axis=1)
    except Exception as e:
        if fi == 0:
            print(f"  [LiDAR parse err]: {e}")
    return None


def get_us_dist(label, spath):
    try:
        depth = ls_iface.get_linear_depth_data(spath)
        if depth is not None and len(depth) > 0:
            arr = np.array(depth).flatten()
            valid = arr[(arr > 0.2) & (arr < 10.0)]
            if len(valid) > 0:
                return float(valid.min())
    except Exception:
        pass
    return 10.0


# ── 시각화 ────────────────────────────────────────────────────────────────────
def draw_bboxes(rgb, bbox):
    img  = Image.fromarray(rgb[:, :, :3])
    draw = ImageDraw.Draw(img)
    if bbox and "data" in bbox:
        for bb in bbox["data"]:
            draw.rectangle([bb.get("x_min", 0), bb.get("y_min", 0),
                            bb.get("x_max", 0), bb.get("y_max", 0)],
                           outline=(0, 255, 0), width=2)
            lbl = bb.get("semanticLabel", "")
            if lbl:
                draw.text((bb["x_min"], max(0, bb["y_min"] - 12)),
                          lbl, fill=(0, 255, 0))
    return np.array(img)


def lidar_topdown(pts, max_r=80):
    fig, ax = plt.subplots(figsize=(4, 4), facecolor="black")
    ax.set_facecolor("black")
    if pts is not None and len(pts) > 0:
        x, y = pts[:, 0], pts[:, 1]
        dist = np.sqrt(x**2 + y**2)
        m = dist < max_r
        sc = ax.scatter(x[m], y[m], c=dist[m], cmap="jet",
                        s=0.5, vmin=0, vmax=max_r)
        plt.colorbar(sc, ax=ax, label="m")
        ax.set_title(f"LiDAR ({m.sum()} pts)", color="white", fontsize=9)
    else:
        ax.set_title("LiDAR (no data)", color="red", fontsize=9)
    ax.set_xlim(-max_r, max_r)
    ax.set_ylim(-max_r, max_r)
    ax.tick_params(colors="white")
    fig.tight_layout(pad=0.3)
    fig.canvas.draw()
    out = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
    plt.close(fig)
    return out


def us_viz(us_vals, max_r=10):
    labels = [l for l, _ in us_vals]
    vals   = [v for _, v in us_vals]
    fig, ax = plt.subplots(figsize=(4, 2), facecolor="black")
    ax.set_facecolor("black")
    colors = ["#00ff00" if v < 3 else "#ffff00" if v < 6 else "#ff4444"
              for v in vals]
    bars = ax.barh(labels, vals, color=colors)
    ax.set_xlim(0, max_r)
    ax.set_title("LightBeam dist (m)", color="white", fontsize=9)
    ax.tick_params(colors="white")
    for bar, v in zip(bars, vals):
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                f"{v:.1f}m", va="center", color="white", fontsize=8)
    fig.tight_layout(pad=0.3)
    fig.canvas.draw()
    out = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
    plt.close(fig)
    return out


def make_composite(cam_imgs, ld_img, us_img, fi):
    W, H = 1280, 800
    canvas = Image.new("RGB", (W, H), (20, 20, 20))
    draw = ImageDraw.Draw(canvas)
    for i, name in enumerate(["front", "left", "right", "back"]):
        if name in cam_imgs:
            tile = Image.fromarray(cam_imgs[name]).resize((320, 180))
        else:
            tile = Image.new("RGB", (320, 180), (40, 0, 0))
            ImageDraw.Draw(tile).text((10, 80), f"{name}\nNO DATA",
                                      fill=(255, 80, 80))
        canvas.paste(tile, (i * 320, 0))
        draw.text((i * 320 + 5, 5), name.upper(), fill=(255, 255, 0))
    canvas.paste(Image.fromarray(ld_img).resize((640, 450)), (0, 185))
    canvas.paste(Image.fromarray(us_img).resize((640, 220)), (640, 185))
    draw.rectangle([0, 640, W, H], fill=(10, 10, 30))
    draw.text((20,  650), f"Frame {fi:02d}/{NUM_FRAMES-1}", fill=(200, 200, 255))
    draw.text((200, 650), "Speed: 100 km/h", fill=(0, 255, 100))
    draw.text((420, 650), f"Dist: {fi * DIST_STEP:.1f}m", fill=(255, 200, 0))
    return np.array(canvas)


# ── 메인 루프 ─────────────────────────────────────────────────────────────────
print(f"\n=== 수집 시작: {NUM_FRAMES}프레임 ===")
for fi in range(NUM_FRAMES):
    x, y, z, yaw = waypoints[fi]
    move_ego(x, y, z, yaw)

    for name in _CAM_LOCAL:
        pos, look = cam_pose(name, x, y, z, yaw)
        with cameras[name]:
            rep.modify.pose(position=pos, look_at=look)

    for _ in range(10):
        sim_ctx.step(render=True)

    # 카메라
    cam_imgs, bbox_json = {}, {}
    for name in _CAM_LOCAL:
        rgb  = rgb_an[name].get_data()
        bbox = bbox_an[name].get_data()
        if rgb is not None and rgb.size > 0 and rgb.max() > 0:
            cam_imgs[name] = draw_bboxes(rgb, bbox)
        if bbox and "data" in bbox:
            bbox_json[name] = [
                {"label": b.get("semanticLabel", ""),
                 "x_min": int(b.get("x_min", 0)), "y_min": int(b.get("y_min", 0)),
                 "x_max": int(b.get("x_max", 0)), "y_max": int(b.get("y_max", 0))}
                for b in bbox["data"]]

    # LiDAR / LightBeam
    pts = get_lidar_pts(fi)
    us_vals = [(lbl, get_us_dist(lbl, sp)) for lbl, sp in us_paths]

    # JSON
    meta = {
        "frame": fi,
        "ego": {"x": float(x), "y": float(y), "z": float(z),
                "yaw_deg": float(yaw)},
        "speed_kph": 100.0,
        "distance_m": float(fi * DIST_STEP),
        "bbox2d": bbox_json,
        "lidar_pts": int(len(pts)) if pts is not None else 0,
        "lightbeam_m": {lbl: float(v) for lbl, v in us_vals},
    }
    with open(os.path.join(OUTPUT_DIR, f"frame_{fi:04d}.json"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    Image.fromarray(
        make_composite(cam_imgs, lidar_topdown(pts), us_viz(us_vals), fi)
    ).save(os.path.join(OUTPUT_DIR, f"frame_{fi:04d}.png"))

    n_bbox = sum(len(v) for v in bbox_json.values())
    print(f"  [{fi+1}/{NUM_FRAMES}] cams={len(cam_imgs)} "
          f"lidar={meta['lidar_pts']}pts bbox={n_bbox} "
          f"lb={[round(v, 1) for _, v in us_vals]}")

sim_ctx.stop()
print(f"\n=== 완료: output/frame_0000~{NUM_FRAMES-1:04d}.png/.json ===")
app.close()
