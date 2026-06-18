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
from pxr import UsdGeom, UsdPhysics, Gf, Sdf

import omni
import omni.kit.commands
import omni.replicator.core as rep
from isaacsim.core.utils.stage import (
    open_stage, is_stage_loading, add_reference_to_stage)
from isaacsim.core.api import SimulationContext
from isaacsim.sensors.rtx import LidarRtx, get_gmo_data
from isaacsim.core.utils.semantics import add_update_semantics
from isaacsim.storage.native import get_assets_root_path
from omni.physx import get_physx_scene_query_interface
from environment import apply_lighting, apply_weather

STAGE_PATH = "/home/karma/OSMtoUSD/gumi.usda"
# OUTPUT_SUBDIR 환경변수로 시나리오별 폴더 분리 (예: scenario_01/day_rain)
_BASE_OUT = "/home/karma/OSMtoUSD/output"
OUTPUT_DIR = os.path.join(_BASE_OUT, os.environ.get("OUTPUT_SUBDIR", ""))
SPEED_KPH  = float(os.environ.get("SPEED_KPH", "100"))  # AMR 등 저속 변주
SPEED_MPS  = SPEED_KPH / 3.6
DT         = 1.0 / 10
DIST_STEP  = SPEED_MPS * DT
NUM_FRAMES = int(os.environ.get("NUM_FRAMES", "10"))
CAM_W, CAM_H = 640, 360
LIDAR_CONFIG = "Example_Rotary"   # 여러 예제에서 검증된 config

LABELS_DIR = os.path.join(OUTPUT_DIR, "labels")
os.makedirs(LABELS_DIR, exist_ok=True)

# 즉시 flush되는 파일 로깅 (Isaac stdout 버퍼링 우회)
_LOGF = os.path.join(OUTPUT_DIR, "run.log")
open(_LOGF, "w").close()


def log(m):
    print(m, flush=True)
    with open(_LOGF, "a", encoding="utf-8") as f:
        f.write(str(m) + "\n")


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

# ── 3. 환경(조명·기상) 프리셋 — 환경변수로 변주 ──────────────────────────────
LIGHTING = os.environ.get("ENV_LIGHTING", "day")   # dawn/day/dusk/night
WEATHER  = os.environ.get("ENV_WEATHER", "clear")  # clear/cloudy/fog/rain
apply_lighting(stage, LIGHTING)
apply_weather(stage, WEATHER)
print(f"환경: 조명={LIGHTING}, 기상={WEATHER}")

# ── 3b. 씬 그룹 semantics (세그멘테이션용, 그룹→자식 전파) ────────────────────
_SCENE_LABELS = {
    "/World/Buildings": "building",
    "/World/GeneratedBuildings": "building",
    "/World/VworldBuildings": "building",
    "/World/Roads": "road",
    "/World/RoadMarkings": "road_marking",
    "/World/Crossings": "crosswalk",
    "/World/Sidewalks": "sidewalk",
    "/World/TrafficSignals": "traffic_sign",
}
for _path, _label in _SCENE_LABELS.items():
    _p = stage.GetPrimAtPath(_path)
    if _p.IsValid():
        add_update_semantics(_p, _label)
print("씬 그룹 semantics 적용")


# ── 4. 경로 추출 — 건물 밀집 구간에서 시작 ───────────────────────────────────
def _building_centroids():
    cents = []
    for grp in ["/World/Buildings", "/World/GeneratedBuildings",
                "/World/VworldBuildings"]:
        g = stage.GetPrimAtPath(grp)
        if g.IsValid():
            for c in g.GetChildren():
                pts = c.GetAttribute("points").Get()
                if pts and len(pts) > 0:
                    a = np.array(pts)
                    cents.append([a[:, 0].mean(), a[:, 1].mean()])
    return np.array(cents) if cents else np.zeros((0, 2))


def build_path():
    rg = stage.GetPrimAtPath("/World/RoadGraph")
    if not rg.IsValid():
        return None
    bcent = _building_centroids()

    # 40m내 건물 최다 도로점이 속한 커브 선택 + 그 지점부터 시작
    best_curve, best_i, best_cnt = None, 0, -1
    for c in rg.GetChildren():
        pts = c.GetAttribute("points").Get()
        if pts is None or len(pts) < 2:
            continue
        a = np.array(pts)
        if len(bcent) == 0:
            best_curve, best_i = a, 0
            break
        for i in range(0, len(a), 2):
            cnt = int((np.linalg.norm(bcent - a[i, :2], axis=1) < 40).sum())
            if cnt > best_cnt:
                best_cnt, best_curve, best_i = cnt, a, i
    if best_curve is None:
        return None
    print(f"  밀집 시작: 40m내 건물 {best_cnt}개")

    # 시작점부터 끝까지 경로 (모자라면 처음으로 순환)
    seg = best_curve[best_i:]
    if len(seg) < 2:
        seg = best_curve
    d = np.concatenate([[0], np.cumsum(
        np.linalg.norm(np.diff(seg[:, :2], axis=0), axis=1))])
    s   = np.linspace(0, min(d[-1], DIST_STEP * NUM_FRAMES), NUM_FRAMES + 1)
    wx  = np.interp(s, d, seg[:, 0])
    wy  = np.interp(s, d, seg[:, 1])
    wz  = np.interp(s, d, seg[:, 2]) + 0.5
    dx  = np.diff(wx, append=wx[-1] + (wx[-1] - wx[-2]))
    dy  = np.diff(wy, append=wy[-1] + (wy[-1] - wy[-2]))
    yaw = np.degrees(np.arctan2(dy, dx))
    return list(zip(wx, wy, wz, yaw))


waypoints = build_path()
if waypoints is None:
    waypoints = [(i * DIST_STEP, 0.0, 0.5, 0.0) for i in range(NUM_FRAMES + 1)]
x0, y0, z0, yaw0 = waypoints[0]
print(f"경로 {len(waypoints)}개  시작=({x0:.1f}, {y0:.1f})")


# ── 4b. 동적 객체(차량/보행자) 배치 + semantics ──────────────────────────────
ASSETS_ROOT = get_assets_root_path()
VEHICLE_USD = ASSETS_ROOT + "/Isaac/Props/Forklift/forklift.usd"
PED_USDS = [
    ASSETS_ROOT + "/Isaac/People/Characters/"
    "original_male_adult_construction_01/male_adult_construction_01.usd",
    ASSETS_ROOT + "/Isaac/People/Characters/F_Business_02/F_Business_02.usd",
]


ACTOR_MODE = os.environ.get("ACTOR_MODE", "static")  # static / vru
_ACTORS = []  # [{"path","prim","x","y","z","yaw","vx","vy","label","behavior"}]


def _make_actor(path, usd, x, y, z, yaw, label, vx=0.0, vy=0.0,
                behavior="static"):
    parent = UsdGeom.Xform.Define(stage, path)
    add_reference_to_stage(usd_path=usd, prim_path=path + "/model")
    api = UsdGeom.XformCommonAPI(parent)
    api.SetTranslate(Gf.Vec3d(x, y, z))
    api.SetRotate(Gf.Vec3f(0, 0, yaw),
                  UsdGeom.XformCommonAPI.RotationOrderXYZ)
    add_update_semantics(parent.GetPrim(), label)
    _ACTORS.append({"path": path, "prim": parent, "x": x, "y": y, "z": z,
                    "yaw": yaw, "vx": vx, "vy": vy, "label": label,
                    "behavior": behavior})


def _spawn_static(wps):
    plan = [
        (2,  4.0, "vehicle", VEHICLE_USD, 0),
        (4, -4.0, "vehicle", VEHICLE_USD, 180),
        (6,  4.0, "vehicle", VEHICLE_USD, 0),
        (3,  3.0, "pedestrian", PED_USDS[0], 0),
        (5, -3.0, "pedestrian", PED_USDS[1], 0),
    ]
    for idx, lat, label, usd, dyaw in plan:
        if idx >= len(wps):
            continue
        x, y, z, yaw = wps[idx]
        yr = np.radians(yaw)
        _make_actor(f"/World/Actors/{label}_{idx}", usd,
                    x + np.sin(yr) * lat, y - np.cos(yr) * lat, z - 0.5,
                    yaw + dyaw, label)


def _spawn_vru(wps):
    """보행자 횡단(정상/무단) + 이륜차 끼어들기 — ego 전방을 가로지름."""
    x0_, y0_, z0_, yaw0_ = wps[0]
    yr = np.radians(yaw0_)
    fwd = np.array([np.cos(yr), np.sin(yr)])         # 진행방향
    left = np.array([-np.sin(yr), np.cos(yr)])       # 좌측
    base = np.array([x0_, y0_]) + fwd * 14           # 전방 14m 횡단지점
    # (라벨, USD, 시작측면offset, 속도방향, 속력 m/s, 행동)
    plan = [
        ("pedestrian", PED_USDS[0],  10.0, -left, 1.4, "normal_cross"),
        ("pedestrian", PED_USDS[1], -8.0,  left, 1.8, "jaywalk"),
        ("cyclist",    PED_USDS[0],  6.0, fwd * -1, 4.5, "cutin"),
    ]
    for i, (label, usd, off, vdir, spd, beh) in enumerate(plan):
        start = base + left * off
        vel = vdir / (np.linalg.norm(vdir) + 1e-9) * spd
        head = float(np.degrees(np.arctan2(vel[1], vel[0])))
        _make_actor(f"/World/Actors/{label}_{i}", usd,
                    float(start[0]), float(start[1]), z0_ - 0.5,
                    head, label, float(vel[0]), float(vel[1]), beh)


def spawn_actors(wps):
    UsdGeom.Xform.Define(stage, "/World/Actors")
    (_spawn_vru if ACTOR_MODE == "vru" else _spawn_static)(wps)
    return len(_ACTORS)


def move_actors():
    """속도 있는 액터를 DT만큼 전진 (VRU 모션)."""
    for a in _ACTORS:
        if a["vx"] == 0 and a["vy"] == 0:
            continue
        a["x"] += a["vx"] * DT
        a["y"] += a["vy"] * DT
        UsdGeom.XformCommonAPI(a["prim"]).SetTranslate(
            Gf.Vec3d(a["x"], a["y"], a["z"]))


n_actors = spawn_actors(waypoints)
log(f"동적 객체(실모델) {n_actors}개 배치 — 에셋 스트리밍 대기...")
# 원격 에셋 로딩 대기
for _ in range(60):
    app.update()
    if not is_stage_loading():
        break
log("에셋 로딩 완료")

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
front_rp = None
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
    if name == "front":
        front_rp = rp
print("카메라 4대 생성")

# ── 6b. 자동 라벨 annotator (front 카메라) ────────────────────────────────────
seg_an = rep.AnnotatorRegistry.get_annotator(
    "semantic_segmentation", init_params={"colorize": True})
inst_an = rep.AnnotatorRegistry.get_annotator(
    "instance_segmentation_fast", init_params={"colorize": True})
depth_an = rep.AnnotatorRegistry.get_annotator("distance_to_camera")
bbox3d_an = rep.AnnotatorRegistry.get_annotator("bounding_box_3d")
for a in (seg_an, inst_an, depth_an, bbox3d_an):
    a.attach([front_rp])
print("자동 라벨 annotator 4종 부착 (front)")

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

# ── 9. 근접센서 → PhysX 직접 raycast (검증 완료: 건물까지 실거리) ───────────
# LightBeam은 OG 노드 의존 + 짧은 range로 부적합 → 순수 raycast로 대체.
# 각 센서: ego 로컬 오프셋 + 로컬 방향 (매 프레임 yaw로 회전).
physx_query = get_physx_scene_query_interface()
# 8방향 근접 레이 (전/후/좌/우 + 4 대각) — 측면 건물도 커버
US_DEFS = [
    ("F",  (3.0,  0.0, 0.0), (1.0,  0.0, 0.0)),
    ("B",  (-3.0, 0.0, 0.0), (-1.0, 0.0, 0.0)),
    ("L",  (0.0,  1.5, 0.0), (0.0,  1.0, 0.0)),
    ("R",  (0.0, -1.5, 0.0), (0.0, -1.0, 0.0)),
    ("FL", (2.0,  1.0, 0.0), (1.0,  1.0, 0.0)),
    ("FR", (2.0, -1.0, 0.0), (1.0, -1.0, 0.0)),
    ("BL", (-2.0, 1.0, 0.0), (-1.0, 1.0, 0.0)),
    ("BR", (-2.0,-1.0, 0.0), (-1.0,-1.0, 0.0)),
]
US_MAX = 120.0
print("근접 raycast 4방향 설정 (max 50m)")

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


# 악천후 센서 성능 저하 (비/안개 → LiDAR 노이즈 + 포인트 드롭)
_WEATHER_NOISE = {"rain": (0.10, 0.25), "fog": (0.05, 0.50)}


def degrade_lidar(pts):
    """WEATHER에 따라 거리 노이즈 + 랜덤 포인트 드롭."""
    if pts is None or WEATHER not in _WEATHER_NOISE:
        return pts
    sigma, drop = _WEATHER_NOISE[WEATHER]
    pts = pts + np.random.normal(0, sigma, pts.shape).astype(pts.dtype)
    keep = np.random.random(len(pts)) > drop
    return pts[keep]


def raycast_us(ex, ey, ez, yaw_deg):
    """ego 포즈 기준 4방향 raycast. (label, dist) 리스트 반환."""
    yr = np.radians(yaw_deg)
    cos, sin = np.cos(yr), np.sin(yr)
    out = []
    for label, off, d in US_DEFS:
        ox, oy, oz = off
        wx = ex + ox * cos - oy * sin
        wy = ey + ox * sin + oy * cos
        wz = ez + oz
        dx = d[0] * cos - d[1] * sin
        dy = d[0] * sin + d[1] * cos
        dn = np.array([dx, dy, d[2]])
        dn = dn / np.linalg.norm(dn)
        try:
            hit = physx_query.raycast_closest(
                [wx, wy, wz], list(dn), US_MAX)
            if hit and hit.get("hit"):
                out.append((label, float(hit["distance"])))
            else:
                out.append((label, US_MAX))
        except Exception:
            out.append((label, US_MAX))
    return out


# ── bbox 파싱 (numpy structured array → dict 리스트) ─────────────────────────
def parse_bboxes(bbox):
    out = []
    if not bbox or "data" not in bbox or len(bbox["data"]) == 0:
        return out
    id2label = bbox.get("info", {}).get("idToLabels", {})
    for bb in bbox["data"]:
        sid = int(bb["semanticId"])
        lab = id2label.get(sid, id2label.get(str(sid), ""))
        if isinstance(lab, dict):
            lab = lab.get("class") or next(iter(lab.values()), "")
        out.append({
            "label": str(lab),
            "x_min": int(bb["x_min"]), "y_min": int(bb["y_min"]),
            "x_max": int(bb["x_max"]), "y_max": int(bb["y_max"]),
        })
    return out


# ── 라벨(세그/깊이/3D) 처리 ──────────────────────────────────────────────────
def seg_to_rgb(seg_data):
    """semantic/instance seg (colorize=True) → RGB ndarray."""
    if seg_data is None:
        return None
    arr = seg_data["data"] if isinstance(seg_data, dict) else seg_data
    arr = np.asarray(arr)
    if arr.ndim == 3 and arr.shape[2] >= 3:
        return arr[:, :, :3].astype(np.uint8)
    return None


def depth_to_rgb(depth, max_m=60.0):
    """거리맵 → jet 컬러맵 RGB (가까움=빨강)."""
    if depth is None:
        return None
    d = np.asarray(depth, dtype=np.float32)
    d = np.where(np.isfinite(d), d, max_m)
    d = np.clip(d, 0, max_m) / max_m
    rgba = plt.cm.jet_r(d)
    return (rgba[:, :, :3] * 255).astype(np.uint8)


def parse_bbox3d(b3):
    out = []
    if not b3 or "data" not in b3 or len(b3["data"]) == 0:
        return out
    id2label = b3.get("info", {}).get("idToLabels", {})
    for bb in b3["data"]:
        sid = int(bb["semanticId"])
        lab = id2label.get(sid, id2label.get(str(sid), ""))
        if isinstance(lab, dict):
            lab = lab.get("class") or next(iter(lab.values()), "")
        out.append({
            "label": str(lab),
            "x_min": float(bb["x_min"]), "y_min": float(bb["y_min"]),
            "z_min": float(bb["z_min"]), "x_max": float(bb["x_max"]),
            "y_max": float(bb["y_max"]), "z_max": float(bb["z_max"]),
        })
    return out


# ── 시각화 ────────────────────────────────────────────────────────────────────
def draw_bboxes(rgb, boxes):
    img  = Image.fromarray(rgb[:, :, :3])
    draw = ImageDraw.Draw(img)
    for b in boxes:
        col = (0, 255, 0) if b["label"] == "vehicle" else (0, 200, 255)
        draw.rectangle([b["x_min"], b["y_min"], b["x_max"], b["y_max"]],
                       outline=col, width=2)
        if b["label"]:
            draw.text((b["x_min"], max(0, b["y_min"] - 12)),
                      b["label"], fill=col)
    return np.array(img)


def lidar_topdown(pts, max_r=120):
    fig, ax = plt.subplots(figsize=(4, 4), facecolor="black")
    ax.set_facecolor("black")
    if pts is not None and len(pts) > 0:
        x, y = pts[:, 0], pts[:, 1]
        dist = np.sqrt(x**2 + y**2)
        m = (dist < max_r) & (dist > 0.5)
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


def us_viz(us_vals, max_r=120):
    labels = [lbl for lbl, _ in us_vals]
    vals   = [v for _, v in us_vals]
    fig, ax = plt.subplots(figsize=(4, 2), facecolor="black")
    ax.set_facecolor("black")
    colors = ["#00ff00" if v < 20 else "#ffff00" if v < 60 else "#ff4444"
              for v in vals]
    bars = ax.barh(labels, vals, color=colors)
    ax.set_xlim(0, max_r)
    ax.set_title("Proximity raycast (m)", color="white", fontsize=9)
    ax.tick_params(colors="white")
    for bar, v in zip(bars, vals):
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                f"{v:.1f}m", va="center", color="white", fontsize=8)
    fig.tight_layout(pad=0.3)
    fig.canvas.draw()
    out = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
    plt.close(fig)
    return out


def make_composite(cam_imgs, ld_img, us_img, seg_img, depth_img, fi):
    W, H = 1280, 860
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

    # 라벨 패널 (front 세그/깊이)
    for j, (im, title) in enumerate([(seg_img, "Semantic Seg"),
                                     (depth_img, "Depth")]):
        x = 640 + j * 320
        if im is not None:
            canvas.paste(Image.fromarray(im).resize((300, 168)), (x + 10, 420))
        draw.text((x + 10, 405), title, fill=(255, 255, 0))

    draw.rectangle([0, 640, 640, H], fill=(10, 10, 30))
    draw.text((20,  650), f"Frame {fi:02d}/{NUM_FRAMES-1}", fill=(200, 200, 255))
    draw.text((20,  672), f"Speed: {SPEED_KPH:.0f} km/h", fill=(0, 255, 100))
    draw.text((20,  694), f"Dist: {fi * DIST_STEP:.1f}m", fill=(255, 200, 0))
    draw.text((220, 650), f"Light: {LIGHTING}", fill=(255, 220, 120))
    draw.text((220, 672), f"Weather: {WEATHER}", fill=(150, 200, 255))
    return np.array(canvas)


# ── 메인 루프 ─────────────────────────────────────────────────────────────────
import traceback
log(f"=== 수집 시작: {NUM_FRAMES}프레임 ===")
for fi in range(NUM_FRAMES):
  try:
    x, y, z, yaw = waypoints[fi]
    move_ego(x, y, z, yaw)
    move_actors()  # VRU 모션 (정적 액터는 무변화)

    for name in _CAM_LOCAL:
        pos, look = cam_pose(name, x, y, z, yaw)
        with cameras[name]:
            rep.modify.pose(position=pos, look_at=look)

    for _ in range(10):
        sim_ctx.step(render=True)
    log(f"  frame {fi}: 스텝 완료")

    # 카메라
    cam_imgs, bbox_json = {}, {}
    for name in _CAM_LOCAL:
        rgb  = rgb_an[name].get_data()
        boxes = parse_bboxes(bbox_an[name].get_data())
        if rgb is not None and rgb.size > 0 and rgb.max() > 0:
            cam_imgs[name] = draw_bboxes(rgb, boxes)
        if boxes:
            bbox_json[name] = boxes
    n_bb = sum(len(v) for v in bbox_json.values())
    log(f"  frame {fi}: 카메라 {len(cam_imgs)}장 bbox={n_bb}")

    # LiDAR / 근접 raycast
    pts = degrade_lidar(get_lidar_pts(fi))
    us_vals = raycast_us(x, y, z, yaw)

    # 자동 라벨 (front): 세그/인스턴스/깊이/3D박스
    seg_img = seg_to_rgb(seg_an.get_data())
    inst_img = seg_to_rgb(inst_an.get_data())
    depth_raw = depth_an.get_data()
    depth_img = depth_to_rgb(depth_raw)
    boxes3d = parse_bbox3d(bbox3d_an.get_data())
    # 라벨 파일 저장
    if seg_img is not None:
        Image.fromarray(seg_img).save(
            os.path.join(LABELS_DIR, f"frame_{fi:04d}_seg.png"))
    if inst_img is not None:
        Image.fromarray(inst_img).save(
            os.path.join(LABELS_DIR, f"frame_{fi:04d}_inst.png"))
    if depth_img is not None:
        Image.fromarray(depth_img).save(
            os.path.join(LABELS_DIR, f"frame_{fi:04d}_depth.png"))
    log(f"  frame {fi}: lidar={0 if pts is None else len(pts)} "
        f"seg={'O' if seg_img is not None else 'X'} "
        f"bbox3d={len(boxes3d)}")

    # JSON
    meta = {
        "frame": fi,
        "environment": {"lighting": LIGHTING, "weather": WEATHER},
        "ego": {"x": float(x), "y": float(y), "z": float(z),
                "yaw_deg": float(yaw)},
        "speed_kph": SPEED_KPH,
        "distance_m": float(fi * DIST_STEP),
        "bbox2d": bbox_json,
        "bbox3d": boxes3d,
        "actors": [{"label": a["label"], "behavior": a["behavior"],
                    "x": round(a["x"], 2), "y": round(a["y"], 2),
                    "yaw": round(a["yaw"], 1)} for a in _ACTORS],
        "lidar_pts": int(len(pts)) if pts is not None else 0,
        "proximity_m": {lbl: float(v) for lbl, v in us_vals},
        "labels": {
            "semantic_seg": f"labels/frame_{fi:04d}_seg.png",
            "instance_seg": f"labels/frame_{fi:04d}_inst.png",
            "depth": f"labels/frame_{fi:04d}_depth.png",
        },
    }
    with open(os.path.join(OUTPUT_DIR, f"frame_{fi:04d}.json"), "w",
              encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    Image.fromarray(
        make_composite(cam_imgs, lidar_topdown(pts), us_viz(us_vals),
                       seg_img, depth_img, fi)
    ).save(os.path.join(OUTPUT_DIR, f"frame_{fi:04d}.png"))
    log(f"  frame {fi}: 저장 완료")
  except Exception as e:
    log(f"  frame {fi} 예외: {e}\n{traceback.format_exc()}")

sim_ctx.stop()
print(f"\n=== 완료: output/frame_0000~{NUM_FRAMES-1:04d}.png/.json ===")
app.close()
