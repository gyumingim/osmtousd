from isaacsim import SimulationApp
# 센서는 PhysX raycast 기반(RTX 센서 미사용). motion_bvh는 무해하게 유지.
app = SimulationApp({"headless": True, "enable_motion_bvh": True})

import os
import json
import yaml
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
ACTOR_MODE = os.environ.get("ACTOR_MODE", "static")  # static/vru/collision/traffic/amr
EGO_REACT = os.environ.get("EGO_REACT", "1") == "1"  # 0=전방장애물 무반응(사고)
# 배경 밀도(씬을 붐비게): 주변 차량·보행자 수 (시나리오 액터에 추가)
AMBIENT_VEH = int(os.environ.get("AMBIENT_VEH", "10"))
AMBIENT_PED = int(os.environ.get("AMBIENT_PED", "10"))
CAM_W, CAM_H = 640, 360

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

    # traffic/collision은 긴 차로 필요 → 가장 긴 커브. 그 외엔 건물 밀집 구간.
    if ACTOR_MODE in ("traffic", "collision"):
        best_curve, best_i, best_len = None, 0, -1.0
        for c in rg.GetChildren():
            pts = c.GetAttribute("points").Get()
            if pts is None or len(pts) < 2:
                continue
            a = np.array(pts)
            ln = np.linalg.norm(np.diff(a[:, :2], axis=0), axis=1).sum()
            if ln > best_len:
                best_len, best_curve, best_i = ln, a, 0
        print(f"  traffic 차로: 최장 커브 {best_len:.1f}m")
    else:
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
        print(f"  밀집 시작: 40m내 건물 {best_cnt}개")
    if best_curve is None:
        return None

    # 시작점부터 끝까지 경로 (모자라면 처음으로 순환)
    seg = best_curve[best_i:]
    if len(seg) < 2:
        seg = best_curve
    d = np.concatenate([[0], np.cumsum(
        np.linalg.norm(np.diff(seg[:, :2], axis=0), axis=1))])
    global _LANE, _LANE_CUM
    _LANE, _LANE_CUM = seg, d   # 차로(arc-length) — traffic 차량 주행용
    s   = np.linspace(0, min(d[-1], DIST_STEP * NUM_FRAMES), NUM_FRAMES + 1)
    wx  = np.interp(s, d, seg[:, 0])
    wy  = np.interp(s, d, seg[:, 1])
    wz  = np.interp(s, d, seg[:, 2]) + 0.5
    dx  = np.diff(wx, append=wx[-1] + (wx[-1] - wx[-2]))
    dy  = np.diff(wy, append=wy[-1] + (wy[-1] - wy[-2]))
    yaw = np.degrees(np.arctan2(dy, dx))
    return list(zip(wx, wy, wz, yaw))


_LANE = None
_LANE_CUM = None


def lane_at(s):
    """차로 arc-length s → (x, y, z, yaw)."""
    s = float(max(0.0, min(s, _LANE_CUM[-1])))
    x = float(np.interp(s, _LANE_CUM, _LANE[:, 0]))
    y = float(np.interp(s, _LANE_CUM, _LANE[:, 1]))
    z = float(np.interp(s, _LANE_CUM, _LANE[:, 2]))
    s2 = min(s + 1.0, float(_LANE_CUM[-1]))
    x2 = float(np.interp(s2, _LANE_CUM, _LANE[:, 0]))
    y2 = float(np.interp(s2, _LANE_CUM, _LANE[:, 1]))
    return x, y, z, float(np.degrees(np.arctan2(y2 - y, x2 - x)))


waypoints = build_path()
if waypoints is None:
    waypoints = [(i * DIST_STEP, 0.0, 0.5, 0.0) for i in range(NUM_FRAMES + 1)]
x0, y0, z0, yaw0 = waypoints[0]
print(f"경로 {len(waypoints)}개  시작=({x0:.1f}, {y0:.1f})")


# ── 4b. 동적 객체(차량/보행자) 배치 + semantics ──────────────────────────────
ASSETS_ROOT = get_assets_root_path()
# 산단(공장) 맥락이라 차량=지게차가 적절(에셋서버에 승용차·자전거 에셋 없음).
VEHICLE_USD = ASSETS_ROOT + "/Isaac/Props/Forklift/forklift.usd"
_PCHAR = ASSETS_ROOT + "/Isaac/People/Characters/"
# 실제 캐릭터 변종 다양화 (반복 2종 → 작업자/사무/의료 5종)
PED_USDS = [
    _PCHAR + "original_male_adult_construction_01/male_adult_construction_01.usd",
    _PCHAR + "original_male_adult_construction_02/male_adult_construction_02.usd",
    _PCHAR + "F_Business_02/F_Business_02.usd",
    _PCHAR + "original_female_adult_police_01/female_adult_police_01.usd",
    _PCHAR + "original_male_adult_medical_01/male_adult_medical_01.usd",
]


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


# ── 차량/이륜차 ──────────────────────────────────────────────────────────────
# 실제 CC0 모델: 승용차·트럭=Kenney Car Kit(Y-up→Rx90 보정), 버스=Poly Pizza(Z-up).
#   소스마다 축/스케일이 달라 종류별 cfg(files·scale·rx·rz). rx/rz는 이동 시 유지.
_VEH_USD = "/home/karma/OSMtoUSD/assets/vehicles/usd/"
_VEH_CFG = {
    "car":   {"files": ["sedan", "suv", "hatchback-sports", "taxi", "police",
                        "van", "suv-luxury", "sedan-sports"],
              "scale": (1.2, 1.12, 1.73), "rx": 90.0, "rz": 90.0},
    "truck": {"files": ["truck", "delivery", "garbage-truck", "firetruck",
                        "ambulance", "truck-flat", "tractor"],
              "scale": (1.2, 1.12, 1.73), "rx": 90.0, "rz": 90.0},
    "bus":   {"files": ["bus"],          # Poly Pizza CC-BY, 이미 Z-up
              "scale": (0.05, 0.066, 0.076), "rx": 0.0, "rz": 90.0},
}
# 오토바이·자전거: 쓸만한 CC0 실모델 부재 → 박스 프록시(2륜 실루엣). 라벨은 정확.
_PROXY_TYPES = {
    "motorcycle": ((2.1, 0.5, 0.95), None, (0.10, 0.10, 0.12)),
    "bicycle":    ((1.7, 0.35, 1.05), None, (0.75, 0.20, 0.20)),
}
import random as _rnd
_rnd.seed(7)


def _box(parent_path, name, L, W, H, cx, cy, cz, color):
    c = UsdGeom.Cube.Define(stage, parent_path + "/" + name)
    c.CreateSizeAttr(1.0)                          # 단위큐브 → scale로 박스
    a = UsdGeom.XformCommonAPI(c)
    a.SetTranslate(Gf.Vec3d(cx, cy, cz))
    a.SetScale(Gf.Vec3f(L, W, H))
    c.CreateDisplayColorAttr([Gf.Vec3f(*color)])


def _make_vehicle(path, kind, x, y, z, yaw, vx=0.0, vy=0.0, behavior="static"):
    """차량/이륜차 배치 + 클래스 라벨. car/truck=실모델, bus/이륜차=프록시."""
    parent = UsdGeom.Xform.Define(stage, path)
    api = UsdGeom.XformCommonAPI(parent)
    api.SetTranslate(Gf.Vec3d(x, y, z))
    rx, rz_off = 0.0, 0.0
    if kind in _VEH_CFG:                            # 실제 CC0 모델
        cfg = _VEH_CFG[kind]
        f = _rnd.choice(cfg["files"])
        add_reference_to_stage(usd_path=_VEH_USD + f + ".usd",
                               prim_path=path + "/model")
        rx, rz_off = cfg["rx"], cfg["rz"]
        api.SetScale(Gf.Vec3f(*cfg["scale"]))
    else:                                          # 박스 프록시(오토바이/자전거)
        (L, W, H), cabin, color = _PROXY_TYPES.get(kind,
                                                   _PROXY_TYPES["motorcycle"])
        _box(path, "body", L, W, H, 0.0, 0.0, H / 2, color)
        if cabin:
            cl, cw, ch, cx = cabin
            _box(path, "cabin", cl, cw, ch, cx, 0.0, H + ch / 2, color)
        else:                                      # 이륜차: 바퀴 2개
            for wi, wx in enumerate((L / 2 - 0.3, -L / 2 + 0.3)):
                _box(path, f"wheel{wi}", 0.5, W + 0.1, 0.5, wx, 0.0, 0.25,
                     (0.05, 0.05, 0.05))
    api.SetRotate(Gf.Vec3f(rx, 0.0, yaw + rz_off),
                  UsdGeom.XformCommonAPI.RotationOrderXYZ)
    add_update_semantics(parent.GetPrim(), kind)
    _ACTORS.append({"path": path, "prim": parent, "x": x, "y": y, "z": z,
                    "yaw": yaw, "vx": vx, "vy": vy, "label": kind,
                    "behavior": behavior, "rx": rx, "rz_off": rz_off})


def _spawn_static(wps):
    veh = [(2, 4.0, "car", 0), (4, -4.0, "truck", 180), (6, 4.0, "car", 0)]
    ped = [(3, 3.0, PED_USDS[0]), (5, -3.0, PED_USDS[1])]
    for idx, lat, kind, dyaw in veh:
        if idx >= len(wps):
            continue
        x, y, z, yaw = wps[idx]
        yr = np.radians(yaw)
        _make_vehicle(f"/World/Actors/{kind}_{idx}", kind,
                      x + np.sin(yr) * lat, y - np.cos(yr) * lat, z - 0.5,
                      yaw + dyaw)
    for idx, lat, usd in ped:
        if idx >= len(wps):
            continue
        x, y, z, yaw = wps[idx]
        yr = np.radians(yaw)
        _make_actor(f"/World/Actors/ped_{idx}", usd,
                    x + np.sin(yr) * lat, y - np.cos(yr) * lat, z - 0.5,
                    yaw, "pedestrian")


def _spawn_vru(wps):
    """보행자 횡단(정상/무단) + 이륜차 끼어들기 — ego 전방을 가로지름."""
    x0_, y0_, z0_, yaw0_ = wps[0]
    yr = np.radians(yaw0_)
    fwd = np.array([np.cos(yr), np.sin(yr)])         # 진행방향
    left = np.array([-np.sin(yr), np.cos(yr)])       # 좌측
    base = np.array([x0_, y0_]) + fwd * 9            # 전방 9m 횡단지점(ego 제동권)
    # (라벨, USD, 시작측면offset, 속도방향, 속력 m/s, 행동)
    plan = [
        ("pedestrian", PED_USDS[0],  10.0, -left, 1.4, "normal_cross"),
        ("pedestrian", PED_USDS[1], -8.0,  left, 1.8, "jaywalk"),
        # 이륜차: 차로 중앙 정면에서 ego 쪽으로 → ego가 제동
        ("motorcycle", None,         0.0, fwd * -1, 2.5, "cutin"),
    ]
    for i, (label, usd, off, vdir, spd, beh) in enumerate(plan):
        start = base + left * off
        vel = vdir / (np.linalg.norm(vdir) + 1e-9) * spd
        head = float(np.degrees(np.arctan2(vel[1], vel[0])))
        if label in _VEH_CFG or label in _PROXY_TYPES:       # 차량/이륜차
            _make_vehicle(f"/World/Actors/{label}_{i}", label,
                          float(start[0]), float(start[1]), z0_ - 0.5,
                          head, float(vel[0]), float(vel[1]), beh)
        else:
            _make_actor(f"/World/Actors/{label}_{i}", usd,
                        float(start[0]), float(start[1]), z0_ - 0.5,
                        head, label, float(vel[0]), float(vel[1]), beh)


def _spawn_collision(wps):
    """전방 차로 위 고장차(arc-length 10m) + 측면 교차 진입차량 → 실제 충돌 코스.
    ego는 s=0에서 접근 → 무반응(사고)이면 충돌, 제동(회피)이면 정지."""
    sx, sy, sz, syaw = lane_at(10.0)        # 전방 10m 차로 위
    yr = np.radians(syaw)
    left = np.array([-np.sin(yr), np.cos(yr)])
    sp = np.array([sx, sy]) + left * 0.6    # 차로 점유(0.6m 치우침)
    _make_vehicle("/World/Actors/stalled_veh", "car",
                  float(sp[0]), float(sp[1]), sz - 0.5, syaw,
                  0.0, 0.0, "stalled")
    # 측면 교차 진입차량: 전방 7m 옆에서 차로로 합류
    mx, my, mz, _ = lane_at(7.0)
    s = np.array([mx, my]) + left * 9
    vel = -left / (np.linalg.norm(left) + 1e-9) * 5.0
    head = float(np.degrees(np.arctan2(vel[1], vel[0])))
    _make_vehicle("/World/Actors/crossing_veh", "truck",
                  float(s[0]), float(s[1]), mz - 0.5, head,
                  float(vel[0]), float(vel[1]), "crossing")


# ── 신호등 + 주행차량 + 폐루프 V2X (ACTOR_MODE=traffic) ──────────────────────
SIG_S = 45.0                       # 신호 정지선 (차로 arc-length)
# 적색→녹색→황색: 차량이 적색에 줄서고 녹색에 방출되는 폐루프 시연
SIG_CYCLE = [("red", 5.0), ("green", 5.0), ("yellow", 1.5)]
TDT = 0.7                          # traffic 프레임당 진행 시간(s)
_TRAFFIC = []                      # [{a, s, v}]
_SIGNAL = None
_SIG_COL = {"green": (0.1, 0.9, 0.1), "yellow": (0.9, 0.8, 0.1),
            "red": (0.9, 0.1, 0.1)}


def signal_phase(t):
    tot = sum(d for _, d in SIG_CYCLE)
    tm = t % tot
    for ph, d in SIG_CYCLE:
        if tm < d:
            return ph, round(d - tm, 1)
        tm -= d
    return "red", 0.0


def _spawn_traffic(wps):
    """기능형 신호등(색 변화) + 선행차(적색정지) 1 + 통과차 2 (ego가 추종)."""
    global _SIGNAL, SIG_S
    lane_len = float(_LANE_CUM[-1])
    SIG_S = min(45.0, lane_len * 0.85)        # 신호 정지선
    sx, sy, sz, _ = lane_at(SIG_S)
    sig = UsdGeom.Sphere.Define(stage, "/World/TrafficSignal/head")
    sig.CreateRadiusAttr(1.2)
    UsdGeom.XformCommonAPI(sig).SetTranslate(Gf.Vec3d(sx, sy, sz + 5.0))
    sig.CreateDisplayColorAttr([Gf.Vec3f(*_SIG_COL["red"])])
    add_update_semantics(stage.GetPrimAtPath("/World/TrafficSignal"),
                         "traffic_light")
    _SIGNAL = sig
    # ego 바로 앞 선행차(신호 정지) + 신호 통과한 앞쪽차 → ego가 따라 정지
    _ego["s"] = max(1.0, SIG_S - 18.0)        # ego는 선행차 뒤
    car_s = [s for s in (SIG_S - 6.0, SIG_S + 8.0, SIG_S + 16.0) if s > 1.0]
    print(f"  신호 s={SIG_S:.1f}, ego 시작 s={_ego['s']:.1f} (차로 {lane_len:.1f}m)")
    for i, s0 in enumerate(car_s):
        x, y, z, yaw = lane_at(s0)
        _make_vehicle(f"/World/Actors/car_{i}", "car",
                      x, y, z, yaw, 0.0, 0.0, "driving")
        _TRAFFIC.append({"a": _ACTORS[-1], "s": s0, "v": 6.0})


def update_traffic(t):
    """신호 위상 갱신 + 차량 종방향 제어(적색정지·앞차추종) → 폐루프."""
    if not _TRAFFIC:
        return None
    phase, ttc = signal_phase(t)
    _SIGNAL.GetDisplayColorAttr().Set([Gf.Vec3f(*_SIG_COL[phase])])
    CRUISE, GAP, ACC, DEC = 6.0, 8.0, 4.0, 6.0
    veh = sorted(_TRAFFIC, key=lambda c: -c["s"])   # 선두 먼저
    for idx, c in enumerate(veh):
        vt = CRUISE
        if phase != "green" and c["s"] < SIG_S:      # 신호 정지(V2I 반응)
            vt = min(vt, max(0.0, SIG_S - 3.0 - c["s"]))   # 정지선 3m 전 제동
        if idx > 0:                                   # 앞차 간격 좁으면 감속(V2V)
            gap = veh[idx - 1]["s"] - c["s"]
            if gap < GAP:
                vt = min(vt, veh[idx - 1]["v"] * gap / GAP)
        dv = vt - c["v"]
        c["v"] = max(0.0, c["v"] + max(-DEC * TDT, min(ACC * TDT, dv)))
        c["s"] += c["v"] * TDT
        x, y, z, yaw = lane_at(c["s"])
        a = c["a"]
        a["x"], a["y"], a["yaw"] = x, y, yaw
        api = UsdGeom.XformCommonAPI(a["prim"])
        api.SetTranslate(Gf.Vec3d(x, y, z))
        api.SetRotate(Gf.Vec3f(a.get("rx", 0.0), 0.0, yaw + a.get("rz_off", 0.0)),
                      UsdGeom.XformCommonAPI.RotationOrderXYZ)
    return {"phase": phase, "time_to_change": ttc, "signal_s": SIG_S}


_V2X = []
COMM_RANGE = 300.0      # C-V2X/DSRC 통신 반경(m)
COMM_LATENCY_MS = 100   # 전송 지연
_v2x_rng = np.random.RandomState(7)


def _rssi(d):
    """자유공간 경로손실 근사 수신세기(dBm)."""
    return round(-40.0 - 20.0 * np.log10(max(1.0, d)), 1)


def _delivery_prob(d):
    """거리에 따른 패킷 전달 확률 (멀수록 손실↑)."""
    return float(max(0.0, 1.0 - (d / COMM_RANGE) ** 2))


def accumulate_v2x(fi, ex, ey, eyaw, sig):
    """실제 통신 모델: 노드별 송신 → 링크별(거리·RSSI·손실·지연) 수신 로그.
    위치 덤프가 아니라 송수신 이벤트(tx→rx, 전달여부 포함)를 기록."""
    ts = round(fi * TDT, 2)
    sx, sy, _, _ = lane_at(SIG_S)
    # 노드: ego + 차량 + 신호 RSU. 각자 메시지 송신.
    nodes = [("ego", ex, ey,
              {"type": "BSM", "x": round(ex, 2), "y": round(ey, 2),
               "heading": round(eyaw, 1)}),
             ("RSU_signal_01", sx, sy,
              {"type": "SPaT", "phase": sig["phase"],
               "time_to_change_s": sig["time_to_change"]})]
    for i, c in enumerate(_TRAFFIC):
        a = c["a"]
        nodes.append((f"veh_{i}", a["x"], a["y"],
                      {"type": "BSM", "x": round(a["x"], 2),
                       "y": round(a["y"], 2), "heading": round(a["yaw"], 1)}))
    # 링크별 전달 (PHY 근사: 범위·RSSI·확률손실·지연)
    for sid, sxx, syy, payload in nodes:
        for rid, rxx, ryy, _p in nodes:
            if rid == sid:
                continue
            d = float(np.hypot(sxx - rxx, syy - ryy))
            if d > COMM_RANGE:
                continue            # 통신 범위 밖 → 미수신
            delivered = bool(_v2x_rng.random() < _delivery_prob(d))
            rec = {"frame": fi, "timestamp": ts, "tx": sid, "rx": rid,
                   "msg": payload["type"], "range_m": round(d, 1),
                   "rssi_dbm": _rssi(d), "latency_ms": COMM_LATENCY_MS,
                   "delivered": delivered}
            rec.update({k: v for k, v in payload.items() if k != "type"})
            _V2X.append(rec)


def _spawn_amr(wps):
    """AMR 산단: 이동 작업자 2명(걷기) + 주행 지게차 1대 — 전부 동적."""
    x0_, y0_, z0_, yaw0_ = wps[0]
    yr = np.radians(yaw0_)
    fwd = np.array([np.cos(yr), np.sin(yr)])
    left = np.array([-np.sin(yr), np.cos(yr)])
    base = np.array([x0_, y0_]) + fwd * 12
    for i, (off, vd, spd) in enumerate([(6.0, -left, 1.3), (-5.0, left, 1.1)]):
        s = base + left * off
        v = vd / (np.linalg.norm(vd) + 1e-9) * spd
        _make_actor(f"/World/Actors/worker_{i}", PED_USDS[i % len(PED_USDS)],
                    float(s[0]), float(s[1]), z0_ - 0.5,
                    float(np.degrees(np.arctan2(v[1], v[0]))),
                    "pedestrian", float(v[0]), float(v[1]), "worker")
    fs = base + fwd * 8 + left * 4
    fv = -left * 1.5
    _make_actor("/World/Actors/forklift_amr", VEHICLE_USD,
                float(fs[0]), float(fs[1]), z0_ - 0.5,
                float(np.degrees(np.arctan2(fv[1], fv[0]))),
                "vehicle", float(fv[0]), float(fv[1]), "forklift_moving")


def _spawn_ambient(wps):
    """배경 밀도: 차로 옆 주차차량 + 인도 보행자 (씬을 붐비게). 차로 4.5m+ 밖."""
    if _LANE_CUM is None:
        return
    UsdGeom.Xform.Define(stage, "/World/Ambient")
    span = min(float(_LANE_CUM[-1]) - 1.0, 70.0)
    mix = ["car", "car", "car", "truck", "bus", "motorcycle", "bicycle"]
    for i in range(AMBIENT_VEH):
        x, y, z, yaw = lane_at(2.0 + span * (i + 0.5) / AMBIENT_VEH)
        yr = np.radians(yaw)
        left = np.array([-np.sin(yr), np.cos(yr)])
        side = 1.0 if i % 2 else -1.0
        off = side * (4.5 + (i % 3) * 3.0)         # 차로 옆/갓길
        _make_vehicle(f"/World/Ambient/veh_{i}", mix[i % len(mix)],
                      float(x + left[0] * off), float(y + left[1] * off),
                      z - 0.5, yaw + (180.0 if side > 0 else 0.0),
                      0.0, 0.0, "parked")
    for j in range(AMBIENT_PED):
        x, y, z, yaw = lane_at(2.0 + span * (j + 0.5) / AMBIENT_PED)
        yr = np.radians(yaw)
        left = np.array([-np.sin(yr), np.cos(yr)])
        side = 1.0 if j % 2 else -1.0
        off = side * (7.0 + (j % 4) * 1.2)         # 인도
        _make_actor(f"/World/Ambient/ped_{j}", PED_USDS[j % len(PED_USDS)],
                    float(x + left[0] * off), float(y + left[1] * off),
                    z - 0.5, yaw + 90.0 * side, "pedestrian",
                    0.0, 0.0, "ambient")


def spawn_actors(wps):
    UsdGeom.Xform.Define(stage, "/World/Actors")
    {"vru": _spawn_vru, "collision": _spawn_collision, "amr": _spawn_amr,
     "traffic": _spawn_traffic}.get(ACTOR_MODE, _spawn_static)(wps)
    _spawn_ambient(wps)                            # 모든 시나리오에 배경 밀도
    return len(_ACTORS)


def compute_ttc(ex, ey, evx, evy):
    """ego와 액터들 간 최소 TTC(s)·최소거리(m)·위험단계."""
    best_ttc, min_rng = float("inf"), float("inf")
    for a in _ACTORS:
        rx, ry = a["x"] - ex, a["y"] - ey
        rng = float(np.hypot(rx, ry))
        min_rng = min(min_rng, rng)
        rvx, rvy = a["vx"] - evx, a["vy"] - evy
        closing = -(rx * rvx + ry * rvy) / (rng + 1e-9)
        if closing > 0.1:
            best_ttc = min(best_ttc, rng / closing)
    if min_rng < 2.5:
        phase = "collision"
    elif best_ttc <= 1.0:
        phase = "imminent"
    elif best_ttc <= 3.0:
        phase = "warning"
    elif best_ttc < float("inf"):
        phase = "approaching"
    else:
        phase = "clear"
    return (round(best_ttc, 2) if best_ttc != float("inf") else None,
            round(min_rng, 2), phase)


def move_actors():
    """속도 있는 액터를 DT만큼 전진 (VRU 모션)."""
    for a in _ACTORS:
        if a["vx"] == 0 and a["vy"] == 0:
            continue
        a["x"] += a["vx"] * DT
        a["y"] += a["vy"] * DT
        UsdGeom.XformCommonAPI(a["prim"]).SetTranslate(
            Gf.Vec3d(a["x"], a["y"], a["z"]))


# ── ego 폐루프 종방향 주행 (차로 추종 + 신호/전방장애물 반응) ────────────────
_ego = {"s": 0.0, "v": 0.0}   # 차로 arc-length, 속도(m/s)
_collision = {"hit": False}   # 실제 접촉 발생 시 충돌 이벤트 기록


def ego_step(sig_state):
    """ego가 차로를 따라 주행하며 적색신호·전방차량/보행자에 감속/정지.
    충돌 후엔 정지. 반환: (x, y, z, yaw, v, reason)."""
    if _collision["hit"]:                   # 충돌 후 정지(post-impact)
        _ego["v"] = 0.0
        x, y, z, yaw = lane_at(_ego["s"])
        return x, y, z + 0.5, yaw, 0.0, "collided"
    ex, ey, ez, eyaw = lane_at(_ego["s"])
    yr = np.radians(eyaw)
    fx, fy = np.cos(yr), np.sin(yr)        # 진행방향
    vt = SPEED_MPS                          # 목표속도
    reason = "cruise"
    # 1) 신호 정지 (V2I) — 정지선 4m 전
    if sig_state and sig_state["phase"] != "green" and _ego["s"] < SIG_S:
        d = SIG_S - 4.0 - _ego["s"]
        if d < vt * 2:
            vt = min(vt, max(0.0, d))
            reason = "signal"
    # 2) 전방 장애물 (V2V/충돌회피) — 차로폭 내 가장 가까운 앞 객체
    #    EGO_REACT=0이면 무반응(돌진) → 사고. 기본=제동(회피).
    if EGO_REACT:
        fwd_min = 1e9
        for a in _ACTORS:
            rx, ry = a["x"] - ex, a["y"] - ey
            fd = rx * fx + ry * fy             # 전방 투영거리
            lat = abs(-rx * fy + ry * fx)      # 측면 이격
            if fd > 0 and lat < 2.8 and fd < fwd_min:
                fwd_min = fd
        if fwd_min < 18.0:                      # 18m 내 전방 차량/보행자
            vt = min(vt, max(0.0, fwd_min - 6.0))   # 6m 앞 정지
            reason = "lead" if reason == "cruise" else reason
    # 가감속 (±)
    ACC, DEC = 3.0, 6.0
    dv = vt - _ego["v"]
    _ego["v"] = max(0.0, _ego["v"] + max(-DEC * DT, min(ACC * DT, dv)))
    _ego["s"] = min(_ego["s"] + _ego["v"] * DT, float(_LANE_CUM[-1]) - 1.0)
    x, y, z, yaw = lane_at(_ego["s"])
    return x, y, z + 0.5, yaw, _ego["v"], reason


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
# 가시 ego 모델(예: AMR iw.hub) — EGO_MODEL 환경변수로 지정 시 부착
_EGO_MODEL = os.environ.get("EGO_MODEL", "")
if _EGO_MODEL:
    add_reference_to_stage(usd_path=ASSETS_ROOT + _EGO_MODEL,
                           prim_path=ego_path + "/model")
    print(f"ego 가시 모델: {_EGO_MODEL}")


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

# ── 8. LiDAR — PhysX raycast 점구름 (RTX LiDAR는 gumi 지오메트리 미명중 → 대체)
# RTX Example_Rotary/HESAI 모두 레이가 씬을 거의 못 맞춰 non-return만 나옴.
# raycast는 건물/도로를 실거리로 맞히므로 360°×다채널로 진짜 점구름 생성.
LIDAR_CH = (-15, -11, -8, -5, -3, -1, 0, 1, 2, 4, 7, 11)  # 수직 채널(도)
LIDAR_AZ = 200       # 수평 분해능
LIDAR_MAX = 100.0
print("LiDAR: PhysX raycast 점구름 (200az x 12ch)")

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
print(f"근접 raycast {len(US_DEFS)}방향 설정 (max {US_MAX:.0f}m)")

# ── 10. 초기화 + 워밍업 ──────────────────────────────────────────────────────
sim_ctx.reset()
sim_ctx.play()
print("워밍업 (30 steps)...")
for _ in range(30):
    sim_ctx.step(render=True)
print("워밍업 완료")


# ── LiDAR: 360°×다채널 raycast → 센서-로컬 점구름 (x 전방, y 좌) ─────────────
def get_lidar_pts(ex, ey, ez, yaw_deg):
    """센서-로컬 점구름 (x,y,z,intensity). intensity=입사각×거리감쇠."""
    yr = np.radians(yaw_deg)
    cy, sy = np.cos(yr), np.sin(yr)
    sz = ez + 2.2                       # 센서 높이
    chans = [(np.cos(np.radians(e)), np.sin(np.radians(e))) for e in LIDAR_CH]
    pts = []
    for ai in range(LIDAR_AZ):
        az = 2.0 * np.pi * ai / LIDAR_AZ      # 로컬 방위(0=전방)
        ca, sa = np.cos(az), np.sin(az)
        for che, she in chans:
            lx, ly, lz = ca * che, sa * che, she    # 로컬 방향
            wx, wy = lx * cy - ly * sy, lx * sy + ly * cy   # 월드 방향
            h = physx_query.raycast_closest([ex, ey, sz], [wx, wy, lz],
                                            LIDAR_MAX)
            if h and h.get("hit"):
                d = h["distance"]
                # intensity: 표면 입사각(cos) × 거리감쇠
                n = h.get("normal")
                cos_i = 0.7
                if n is not None:
                    nv = np.array([n[0], n[1], n[2]], dtype=float)
                    nn = np.linalg.norm(nv)
                    if nn > 1e-6:
                        cos_i = abs(float(np.dot([wx, wy, lz], nv / nn)))
                inten = cos_i * (1.0 - 0.5 * d / LIDAR_MAX) * 255.0
                pts.append((lx * d, ly * d, lz * d, round(inten, 1)))
    return np.array(pts, dtype=np.float32) if pts else None


# 악천후 센서 성능 저하 (비/안개 → LiDAR 노이즈 + 포인트 드롭)
_WEATHER_NOISE = {"rain": (0.10, 0.25), "fog": (0.05, 0.50)}


def degrade_lidar(pts):
    """WEATHER에 따라 거리 노이즈(xyz만) + 랜덤 포인트 드롭."""
    if pts is None or WEATHER not in _WEATHER_NOISE:
        return pts
    sigma, drop = _WEATHER_NOISE[WEATHER]
    pts = pts.copy()
    pts[:, :3] += np.random.normal(0, sigma, (len(pts), 3)).astype(pts.dtype)
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


def _cast(ox, oy, oz, dx, dy, dz, maxd):
    """단일 raycast → (거리, 충돌체경로) 또는 (None, None)."""
    d = np.array([dx, dy, dz], float)
    d /= (np.linalg.norm(d) + 1e-9)
    try:
        h = physx_query.raycast_closest([ox, oy, oz], list(d), maxd)
        if h and h.get("hit"):
            return float(h["distance"]), str(h.get("collision", ""))
    except Exception:
        pass
    return None, None


_RCS = {"vehicle": 10.0, "pedestrian": -5.0}   # 표적별 RCS(dBsm)


def sense_radar(ex, ey, ez, yaw_deg, ego_spd=0.0, fov=60, beams=15,
                max_r=120.0):
    """FMCW 자동차 레이더 근사: 표적별 거리·방위·상대속도·RCS·SNR.
    상대 라디얼 속도 = (표적속도 - ego속도)의 LOS 성분(접근+)."""
    yr = np.radians(yaw_deg)
    evx, evy = ego_spd * np.cos(yr), ego_spd * np.sin(yr)   # ego 속도벡터
    rows = []
    for beam, ang in enumerate(np.linspace(-fov, fov, beams)):
        ar = yr + np.radians(ang)
        dx, dy = np.cos(ar), np.sin(ar)         # LOS
        dist, coll = _cast(ex, ey, ez + 0.5, dx, dy, 0.0, max_r)
        if dist is None:
            continue
        tvx, tvy, rcs = 0.0, 0.0, 20.0          # 정지구조물 기본(큰 RCS)
        for a in _ACTORS:
            if a["path"] in coll:
                tvx, tvy = a["vx"], a["vy"]
                rcs = _RCS.get(a["label"], 5.0)
                break
        rv = -((tvx - evx) * dx + (tvy - evy) * dy)   # 상대 라디얼속도
        snr = 80.0 + rcs - 40.0 * np.log10(max(1.0, dist))   # 레이더방정식
        rows.append({"beam": beam, "azimuth_deg": round(float(ang), 1),
                     "range_m": round(dist, 2),
                     "radial_velocity_mps": round(float(rv), 2),
                     "rcs_dbsm": round(rcs, 1), "snr_db": round(float(snr), 1)})
    return rows


def sense_ultrasonic(ex, ey, ez, yaw_deg, max_r=5.0):
    """범퍼 8방향 단거리(≤5m) 초음파. (sensor, distance) — 미탐지는 max."""
    yr = np.radians(yaw_deg)
    cos, sin = np.cos(yr), np.sin(yr)
    rows = []
    for label, off, d in US_DEFS:
        ox, oy, oz = off
        wx = ex + ox * cos - oy * sin
        wy = ey + ox * sin + oy * cos
        dx = d[0] * cos - d[1] * sin
        dy = d[0] * sin + d[1] * cos
        dist, _ = _cast(wx, wy, ez + oz, dx, dy, d[2], max_r)
        rows.append({"sensor": label,
                     "distance_m": round(dist, 3) if dist else max_r,
                     "detected": dist is not None})
    return rows


def write_pcd(path, pts):
    """포인트클라우드 → ASCII PCD (x y z intensity)."""
    n = 0 if pts is None else len(pts)
    has_i = n and pts.shape[1] >= 4
    with open(path, "w") as f:
        fields = "x y z intensity" if has_i else "x y z"
        sz = "4 4 4 4" if has_i else "4 4 4"
        typ = "F F F F" if has_i else "F F F"
        cnt = "1 1 1 1" if has_i else "1 1 1"
        f.write(f"# .PCD v0.7 - Point Cloud Data\nVERSION 0.7\n"
                f"FIELDS {fields}\nSIZE {sz}\nTYPE {typ}\nCOUNT {cnt}\n"
                f"WIDTH {n}\nHEIGHT 1\nVIEWPOINT 0 0 0 1 0 0 0\n"
                f"POINTS {n}\nDATA ascii\n")
        if n and has_i:
            for p in pts:
                f.write(f"{p[0]:.3f} {p[1]:.3f} {p[2]:.3f} {p[3]:.1f}\n")
        elif n:
            for p in pts:
                f.write(f"{p[0]:.3f} {p[1]:.3f} {p[2]:.3f}\n")


def write_csv(path, rows, cols):
    """딕트 리스트 → CSV (제안서 Radar/Ultrasonic .csv 포맷)."""
    with open(path, "w") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(r[c]) for c in cols) + "\n")


def clean(o):
    """numpy 스칼라/배열 → native (json·yaml 직렬화 안전)."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    return o


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
    """3D bbox: 로컬 AABB extent + 월드 변환(4x4). transform 있어야 3D검출 사용가능."""
    out = []
    if not b3 or "data" not in b3 or len(b3["data"]) == 0:
        return out
    id2label = b3.get("info", {}).get("idToLabels", {})
    names = b3["data"].dtype.names if hasattr(b3["data"], "dtype") else ()
    for bb in b3["data"]:
        sid = int(bb["semanticId"])
        lab = id2label.get(sid, id2label.get(str(sid), ""))
        if isinstance(lab, dict):
            lab = lab.get("class") or next(iter(lab.values()), "")
        rec = {
            "label": str(lab),
            "x_min": float(bb["x_min"]), "y_min": float(bb["y_min"]),
            "z_min": float(bb["z_min"]), "x_max": float(bb["x_max"]),
            "y_max": float(bb["y_max"]), "z_max": float(bb["z_max"]),
        }
        if "transform" in names:          # 월드 포즈(회전+위치) 4x4
            rec["transform"] = np.asarray(bb["transform"],
                                          dtype=float).reshape(4, 4).tolist()
        out.append(rec)
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
    # 실측 ego 속도·행동 (폐루프 주행)
    draw.text((20,  672), f"Speed: {_HUD['spd']:.0f} km/h ({_HUD['act']})",
              fill=(0, 255, 100))
    draw.text((20,  694), f"Dist: {_HUD['dist']:.1f}m", fill=(255, 200, 0))
    draw.text((220, 650), f"Light: {LIGHTING}", fill=(255, 220, 120))
    draw.text((220, 672), f"Weather: {WEATHER}", fill=(150, 200, 255))
    if _HUD.get("sig"):
        draw.text((220, 694), f"Signal: {_HUD['sig']}", fill=(255, 120, 120))
    return np.array(canvas)


_HUD = {"spd": 0.0, "act": "", "dist": 0.0, "sig": ""}


# ── 메인 루프 ─────────────────────────────────────────────────────────────────
import traceback
_ego["v"] = SPEED_MPS   # ego 초기 주행속도
log(f"=== 수집 시작: {NUM_FRAMES}프레임 ===")
for fi in range(NUM_FRAMES):
  try:
    move_actors()  # VRU 모션 (정적 액터는 무변화)
    sig_state = update_traffic(fi * TDT)  # 신호 위상 + 주행차량 폐루프
    # ego 폐루프 주행: 차로 추종 + 적색신호/전방장애물 반응
    px, py = lane_at(_ego["s"])[:2]
    x, y, z, yaw, ego_spd, ego_reason = ego_step(sig_state)
    move_ego(x, y, z, yaw)
    if sig_state is not None:
        accumulate_v2x(fi, x, y, yaw, sig_state)
    # ego 속도 벡터 (실제 이동량) → TTC 계산
    ego_vx, ego_vy = (x - px) / DT, (y - py) / DT
    ttc, ttc_rng, ttc_phase = compute_ttc(x, y, ego_vx, ego_vy)
    # 실제 접촉 감지 (collision 모드) → 충돌 이벤트 1회 기록 + 전원 정지
    if (ACTOR_MODE == "collision" and not _collision["hit"]
            and ttc_rng is not None and ttc_rng <= 2.5):
        near = min(_ACTORS, key=lambda a: np.hypot(a["x"] - x, a["y"] - y))
        _collision.update(hit=True, frame=fi, impact_kph=round(ego_spd * 3.6, 1),
                          min_range_m=ttc_rng, actor=near["behavior"])
        for a in _ACTORS:
            a["vx"] = a["vy"] = 0.0
        log(f"  *** 충돌! frame {fi} {near['behavior']} "
            f"@ {_collision['impact_kph']}km/h")
    log(f"  frame {fi}: ego v={ego_spd:.1f}m/s ({ego_reason})")

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

    # LiDAR / 근접 raycast / Radar / Ultrasonic
    pts = degrade_lidar(get_lidar_pts(x, y, z, yaw))
    us_vals = raycast_us(x, y, z, yaw)
    radar_rows = sense_radar(x, y, z, yaw, ego_spd=ego_spd)
    us_rows = sense_ultrasonic(x, y, z, yaw)
    # 제안서 포맷 저장: LiDAR .pcd, Radar/Ultrasonic .csv
    write_pcd(os.path.join(LABELS_DIR, f"frame_{fi:04d}_lidar.pcd"), pts)
    write_csv(os.path.join(LABELS_DIR, f"frame_{fi:04d}_radar.csv"),
              radar_rows, ["beam", "azimuth_deg", "range_m",
                           "radial_velocity_mps", "rcs_dbsm", "snr_db"])
    write_csv(os.path.join(LABELS_DIR, f"frame_{fi:04d}_ultrasonic.csv"),
              us_rows, ["sensor", "distance_m", "detected"])

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
        "speed_kph": round(ego_spd * 3.6, 1),
        "ego_action": ego_reason,
        "distance_m": round(float(_ego["s"]), 2),
        "bbox2d": bbox_json,
        "bbox3d": boxes3d,
        "actors": [{"label": a["label"], "behavior": a["behavior"],
                    "x": round(float(a["x"]), 2), "y": round(float(a["y"]), 2),
                    "yaw": round(float(a["yaw"]), 1)} for a in _ACTORS],
        "ttc": {"ttc_s": ttc, "min_range_m": ttc_rng, "phase": ttc_phase},
        "collision_event": dict(_collision) if _collision["hit"] else None,
        "signal": sig_state,
        "lidar_pts": int(len(pts)) if pts is not None else 0,
        "proximity_m": {lbl: float(v) for lbl, v in us_vals},
        "radar_detections": len(radar_rows),
        "ultrasonic_detections": sum(1 for r in us_rows if r["detected"]),
        "labels": {
            "semantic_seg": f"labels/frame_{fi:04d}_seg.png",
            "instance_seg": f"labels/frame_{fi:04d}_inst.png",
            "depth": f"labels/frame_{fi:04d}_depth.png",
            "lidar_pcd": f"labels/frame_{fi:04d}_lidar.pcd",
            "radar_csv": f"labels/frame_{fi:04d}_radar.csv",
            "ultrasonic_csv": f"labels/frame_{fi:04d}_ultrasonic.csv",
        },
    }
    meta = clean(meta)
    with open(os.path.join(OUTPUT_DIR, f"frame_{fi:04d}.json"), "w",
              encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    # 메타 .yaml 도 저장 (제안서 .yaml 포맷)
    with open(os.path.join(OUTPUT_DIR, f"frame_{fi:04d}.yaml"), "w",
              encoding="utf-8") as f:
        yaml.safe_dump(meta, f, allow_unicode=True, sort_keys=False)

    _HUD.update(spd=ego_spd * 3.6, act=ego_reason, dist=float(_ego["s"]),
                sig=sig_state["phase"] if sig_state else "")
    Image.fromarray(
        make_composite(cam_imgs, lidar_topdown(pts), us_viz(us_vals),
                       seg_img, depth_img, fi)
    ).save(os.path.join(OUTPUT_DIR, f"frame_{fi:04d}.png"))
    log(f"  frame {fi}: 저장 완료")
  except Exception as e:
    log(f"  frame {fi} 예외: {e}\n{traceback.format_exc()}")

# 폐루프 V2X 로그 저장 (traffic 모드)
if _V2X:
    with open(os.path.join(OUTPUT_DIR, "v2x_log.json"), "w",
              encoding="utf-8") as f:
        json.dump({"signal_cycle": SIG_CYCLE, "dt": TDT,
                   "messages": clean(_V2X)}, f, indent=2, ensure_ascii=False)
    log(f"V2X 로그 {len(_V2X)}개 저장 (v2x_log.json)")

sim_ctx.stop()
print(f"\n=== 완료: output/frame_0000~{NUM_FRAMES-1:04d}.png/.json ===")
app.close()
