"""
센서 자가진단 스크립트 — 시각화 없이 raw 데이터 구조만 기록.
결과: output/debug_report.json (구조화된 진단)

Usage:
    ./_build/linux-x86_64/release/python.sh /home/karma/OSMtoUSD/sensor_debug.py
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "enable_motion_bvh": True})

import os
import json
import traceback
import numpy as np
from pxr import UsdGeom, UsdLux, UsdPhysics, Gf, Sdf

import omni
import omni.kit.commands
import omni.replicator.core as rep
from isaacsim.core.utils.stage import open_stage, is_stage_loading
from isaacsim.core.api import SimulationContext
from isaacsim.sensors.rtx import LidarRtx, get_gmo_data
from omni.physx import get_physx_scene_query_interface

STAGE_PATH = "/home/karma/OSMtoUSD/gumi.usda"
OUTPUT_DIR = "/home/karma/OSMtoUSD/output"
LIDAR_CONFIG = "Example_Rotary"
NUM_FRAMES = 3

os.makedirs(OUTPUT_DIR, exist_ok=True)

report = {"stages": [], "frames": [], "errors": []}


def safe(v):
    """JSON 직렬화 안전 변환."""
    try:
        if isinstance(v, np.ndarray):
            return {"_ndarray": True, "shape": list(v.shape),
                    "dtype": str(v.dtype)}
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, dict):
            return {str(k): safe(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [safe(x) for x in v[:5]]
        return v
    except Exception:
        return str(type(v))


def stage_log(msg):
    print(f"[DEBUG] {msg}", flush=True)
    report["stages"].append(msg)


# ── 씬 로드 ───────────────────────────────────────────────────────────────────
try:
    stage_log("씬 로드 시작")
    open_stage(STAGE_PATH)
    while is_stage_loading():
        app.update()
    for _ in range(5):
        app.update()
    stage = omni.usd.get_context().get_stage()
    stage_log("씬 로드 완료")

    if not stage.GetPrimAtPath("/World/PhysicsScene").IsValid():
        UsdPhysics.Scene.Define(stage, Sdf.Path("/World/PhysicsScene"))
    sim_ctx = SimulationContext(stage_units_in_meters=1.0,
                                physics_dt=1.0 / 60, rendering_dt=1.0 / 60)

    dome = UsdLux.DomeLight.Define(stage, "/World/DomeLight")
    dome.CreateIntensityAttr(800.0)

    # 건물 밀집 위치를 시작점으로 (40m 내 건물 최다 도로점)
    bcent = []
    for grp in ["/World/Buildings", "/World/GeneratedBuildings",
                "/World/VworldBuildings"]:
        g = stage.GetPrimAtPath(grp)
        if g.IsValid():
            for c in g.GetChildren():
                pts = c.GetAttribute("points").Get()
                if pts and len(pts) > 0:
                    a = np.array(pts)
                    bcent.append([a[:, 0].mean(), a[:, 1].mean()])
    bcent = np.array(bcent) if bcent else np.zeros((0, 2))

    rg = stage.GetPrimAtPath("/World/RoadGraph")
    start = (0.0, 0.0, 0.5, 0.0)
    best_cnt = -1
    if rg.IsValid() and len(bcent) > 0:
        for c in rg.GetChildren():
            pts = c.GetAttribute("points").Get()
            if not pts or len(pts) < 2:
                continue
            a = np.array(pts)
            for i in range(0, len(a), 2):  # 2점마다 샘플
                d = np.linalg.norm(bcent - a[i, :2], axis=1)
                cnt = int((d < 40).sum())
                if cnt > best_cnt:
                    best_cnt = cnt
                    j, k = min(i + 1, len(a) - 1), max(i - 1, 0)
                    dx, dy = a[j, 0] - a[k, 0], a[j, 1] - a[k, 1]
                    yaw = float(np.degrees(np.arctan2(dy, dx)))
                    start = (float(a[i, 0]), float(a[i, 1]), 0.5, yaw)
    report["start_pos"] = list(start)
    report["buildings_within_40m"] = best_cnt
    report["total_buildings"] = int(len(bcent))
    stage_log(f"밀집 시작점 {start[:2]} (40m내 건물 {best_cnt}개)")
    x0, y0, z0, yaw0 = start

    # ── 에고 ──────────────────────────────────────────────────────────────────
    ego_path = "/World/EgoVehicle"
    ego = UsdGeom.Xform.Define(stage, ego_path)
    api = UsdGeom.XformCommonAPI(ego)
    api.SetTranslate(Gf.Vec3d(x0, y0, z0))

    # ── 카메라 1대 (전방) ───────────────────────────────────────────────────
    cam = rep.create.camera(
        position=(x0 + 2, y0, z0 + 1.5),
        look_at=(x0 + 22, y0, z0 + 1.5),
        focal_length=18.0)
    cam_rp = rep.create.render_product(cam, (640, 360))
    rgb_an = rep.AnnotatorRegistry.get_annotator("rgb")
    bbox_an = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
    rgb_an.attach([cam_rp])
    bbox_an.attach([cam_rp])
    stage_log("카메라 생성")

    # ── LiDAR ─────────────────────────────────────────────────────────────────
    try:
        lidar = LidarRtx(
            prim_path=ego_path + "/Lidar", name="lidar",
            translation=np.array([0.0, 0.0, 2.2]),
            orientation=np.array([1.0, 0.0, 0.0, 0.0]),
            config_file_name=LIDAR_CONFIG)
        lidar.initialize()
        lidar.attach_annotator("GenericModelOutput")
        report["lidar_prim_type"] = stage.GetPrimAtPath(
            ego_path + "/Lidar").GetTypeName()
        stage_log(f"LiDAR 생성 (prim type="
                  f"{report['lidar_prim_type']})")
    except Exception as e:
        report["errors"].append(f"LiDAR 생성 실패: {e}\n{traceback.format_exc()}")
        lidar = None

    # ── 초음파 → PhysX 직접 raycast (센서 프림/OG 불필요) ────────────────────
    # 각 센서: ego 로컬 오프셋 + 월드 방향. yaw=0이라 로컬=월드.
    physx_query = get_physx_scene_query_interface()
    US_DEFS = [
        ("FL",   (x0 + 3, y0 + 1, z0), (1.0,  0.4, 0.0)),
        ("FR",   (x0 + 3, y0 - 1, z0), (1.0, -0.4, 0.0)),
        ("RL",   (x0 - 3, y0 + 1, z0), (-1.0, 0.4, 0.0)),
        ("RR",   (x0 - 3, y0 - 1, z0), (-1.0,-0.4, 0.0)),
        # sanity: 아래 방향 — 도로/지면을 반드시 맞아야 함
        ("DOWN", (x0, y0, z0 + 1.0),  (0.0,  0.0, -1.0)),
    ]
    US_MAX = 50.0
    stage_log("PhysX raycast 방식 (max 50m)")

    # ── 워밍업 ─────────────────────────────────────────────────────────────────
    sim_ctx.reset()
    sim_ctx.play()
    stage_log("워밍업 40 steps")
    for _ in range(40):
        sim_ctx.step(render=True)

    # ── 프레임별 진단 ──────────────────────────────────────────────────────────
    for fi in range(NUM_FRAMES):
        for _ in range(10):
            sim_ctx.step(render=True)

        fr = {"frame": fi}

        # 카메라
        try:
            rgb = rgb_an.get_data()
            if isinstance(rgb, np.ndarray) and rgb.size > 0:
                fr["camera"] = {
                    "shape": list(rgb.shape),
                    "dtype": str(rgb.dtype),
                    "max": int(rgb.max()),
                    "mean": float(rgb.mean()),
                    "nonzero_pct": float((rgb > 0).mean() * 100),
                }
            else:
                fr["camera"] = {"empty": True, "type": str(type(rgb))}
            bbox = bbox_an.get_data()
            fr["camera"]["bbox_count"] = (
                len(bbox["data"]) if bbox and "data" in bbox else 0)
        except Exception as e:
            fr["camera"] = {"exception": str(e)}

        # LiDAR (GenericModelOutput)
        if lidar is not None:
            try:
                frame = lidar.get_current_frame()
                fr["lidar"] = {"frame_keys": [str(k) for k in frame.keys()]}
                data = frame.get("GenericModelOutput")
                if data is None or len(data) == 0:
                    fr["lidar"]["gmo"] = "empty"
                else:
                    gmo = get_gmo_data(data)
                    x = np.array(gmo.x)
                    y = np.array(gmo.y)
                    z = np.array(gmo.z)
                    fr["lidar"]["count"] = int(len(x))
                    if len(x) > 0:
                        dist = np.sqrt(x**2 + y**2)
                        dd = dist[np.isfinite(dist) & (dist > 0.1)]
                        fr["lidar"]["sample_xyz"] = [
                            round(float(x[0]), 1), round(float(y[0]), 1),
                            round(float(z[0]), 1)]
                        fr["lidar"]["hist"] = {
                            "0-10m":   int(((dd >= 0) & (dd < 10)).sum()),
                            "10-30m":  int(((dd >= 10) & (dd < 30)).sum()),
                            "30-60m":  int(((dd >= 30) & (dd < 60)).sum()),
                            "60-120m": int(((dd >= 60) & (dd < 120)).sum()),
                            ">120m":   int((dd >= 120).sum()),
                        }
            except Exception as e:
                fr["lidar"] = {"exception": str(e),
                               "tb": traceback.format_exc()[-500:]}
        else:
            fr["lidar"] = {"not_created": True}

        # PhysX raycast (초음파)
        fr["raycast"] = {}
        for label, origin, direction in US_DEFS:
            try:
                # 방향 정규화
                d = np.array(direction, dtype=float)
                d = d / np.linalg.norm(d)
                hit = physx_query.raycast_closest(
                    list(origin), list(d), US_MAX)
                if hit and hit.get("hit"):
                    fr["raycast"][label] = {
                        "hit": True,
                        "dist": round(float(hit["distance"]), 2),
                        "collider": str(hit.get("collision", ""))[-40:],
                    }
                else:
                    fr["raycast"][label] = {"hit": False}
            except Exception as e:
                fr["raycast"][label] = {"exception": str(e)}

        report["frames"].append(fr)
        stage_log(f"프레임 {fi} 진단 완료")

    sim_ctx.stop()

except Exception as e:
    report["errors"].append(f"치명적: {e}\n{traceback.format_exc()}")

# ── 리포트 저장 ───────────────────────────────────────────────────────────────
with open(os.path.join(OUTPUT_DIR, "debug_report.json"), "w",
          encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False, default=str)

print("[DEBUG] ===== REPORT SAVED =====", flush=True)
print("[DEBUG] DEBUG_DONE", flush=True)
app.close()
