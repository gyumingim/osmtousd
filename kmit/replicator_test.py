from isaacsim import SimulationApp
app = SimulationApp({"headless": False, "width": 1920, "height": 1080})

import os
import json
import random
import numpy as np
from PIL import Image
from pxr import UsdGeom, Sdf, Gf, Vt

import omni.usd
import omni.replicator.core as rep

STAGE_PATH = "/home/karma/OSMtoUSD/kmit/gumi.usda"
OUTPUT_DIR = "/home/karma/OSMtoUSD/kmit/output"
NUM_VEHICLES = 8
RENDER_FRAMES = 1

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── 씬 로드 ───────────────────────────────────────────────────────────────────
print("씬 로드 중...")
omni.usd.get_context().open_stage(STAGE_PATH)
app.update()
app.update()

stage = omni.usd.get_context().get_stage()


# ── 도로 위치 샘플링 ─────────────────────────────────────────────────────────
def sample_road_positions(stage, n):
    road_graph = stage.GetPrimAtPath("/World/RoadGraph")
    if not road_graph.IsValid():
        print("[경고] RoadGraph 없음 — 원점 근처에 배치")
        return [(i * 5.0, 0.0, 0.5) for i in range(n)], [(0, 0, 0)] * n

    curves = [c for c in road_graph.GetChildren()
              if c.GetAttribute("points").Get() is not None]
    selected = random.sample(curves, min(n, len(curves)))

    positions, rotations = [], []
    for curve in selected:
        pts = list(curve.GetAttribute("points").Get())
        if len(pts) < 2:
            continue
        idx = random.randint(0, len(pts) - 2)
        p0, p1 = pts[idx], pts[idx + 1]
        pos = (
            (p0[0] + p1[0]) / 2,
            (p0[1] + p1[1]) / 2,
            0.5,
        )
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        yaw = float(np.degrees(np.arctan2(dy, dx)))
        positions.append(pos)
        rotations.append((0.0, 0.0, yaw))

    return positions, rotations


positions, rotations = sample_road_positions(stage, NUM_VEHICLES)
print(f"차량 배치 위치 {len(positions)}개 샘플링 완료")


# ── 차량 프림 생성 (박스) ─────────────────────────────────────────────────────
def create_vehicle_prim(stage, path, pos, rot_deg_z):
    xform = UsdGeom.Xform.Define(stage, path)
    xform.AddTranslateOp().Set(Gf.Vec3d(*pos))
    xform.AddRotateZOp().Set(rot_deg_z)

    mesh = UsdGeom.Mesh.Define(stage, path + "/body")
    # 차량 크기: 4.5m x 2m x 1.5m
    lx, ly, lz = 2.25, 1.0, 0.75
    pts = [
        Gf.Vec3f(-lx, -ly, 0), Gf.Vec3f(lx, -ly, 0),
        Gf.Vec3f(lx,  ly, 0), Gf.Vec3f(-lx,  ly, 0),
        Gf.Vec3f(-lx, -ly, lz * 2), Gf.Vec3f(lx, -ly, lz * 2),
        Gf.Vec3f(lx,  ly, lz * 2), Gf.Vec3f(-lx,  ly, lz * 2),
    ]
    mesh.CreatePointsAttr(Vt.Vec3fArray(pts))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([4] * 6))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray([
        0, 1, 2, 3,  # bottom
        4, 5, 6, 7,  # top
        0, 1, 5, 4,  # front
        2, 3, 7, 6,  # back
        0, 3, 7, 4,  # left
        1, 2, 6, 5,  # right
    ]))
    mesh.CreateDoubleSidedAttr(True)

    prim = stage.GetPrimAtPath(path)
    prim.CreateAttribute("isaac:semantic_label",
                         Sdf.ValueTypeNames.String).Set("vehicle")
    mesh.GetPrim().CreateAttribute("isaac:semantic_label",
                                   Sdf.ValueTypeNames.String).Set("vehicle")
    return path


vehicle_group = UsdGeom.Xform.Define(stage, "/World/Vehicles")
for i, (pos, rot) in enumerate(zip(positions, rotations)):
    create_vehicle_prim(stage, f"/World/Vehicles/Vehicle_{i:03d}", pos, rot[2])

print(f"차량 {len(positions)}개 생성 완료")
app.update()


# ── 에고 차량 카메라 (전방 대시캠 시점) ────────────────────────────────────────
# 에고 차량 = positions[0], 전방 방향으로 카메라 마운트
ex, ey, ez = positions[0]
yaw_rad = float(np.radians(rotations[0][2]))

# 카메라: 차량 루프 위 (z+1.5m), 전방 바라보기
cam_pos = (ex, ey, ez + 1.5)
# 전방 20m 지점을 look_at으로
look_at = (
    ex + np.cos(yaw_rad) * 20.0,
    ey + np.sin(yaw_rad) * 20.0,
    ez + 1.2,
)

camera = rep.create.camera(
    position=cam_pos,
    look_at=look_at,
    focal_length=18.0,   # 광각 (자율주행 전방 카메라)
)
render_product = rep.create.render_product(camera, (1920, 1080))
print(f"에고 차량 위치: {cam_pos}, look_at: {look_at}")


# ── Annotator 연결 ────────────────────────────────────────────────────────────
rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb")
bbox2d_annot = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
bbox3d_annot = rep.AnnotatorRegistry.get_annotator("bounding_box_3d")

rgb_annot.attach([render_product])
bbox2d_annot.attach([render_product])
bbox3d_annot.attach([render_product])


# ── 렌더링 ────────────────────────────────────────────────────────────────────
print("렌더링 중...")
for _ in range(8):
    app.update()

rep.orchestrator.step(rt_subframes=4)
app.update()

rgb_data = rgb_annot.get_data()
bbox2d_data = bbox2d_annot.get_data()
bbox3d_data = bbox3d_annot.get_data()


# ── 결과 저장 ─────────────────────────────────────────────────────────────────
if rgb_data is not None and len(rgb_data) > 0:
    img = Image.fromarray(rgb_data[:, :, :3])
    img.save(f"{OUTPUT_DIR}/frame_0000.png")
    print(f"RGB 저장: {OUTPUT_DIR}/frame_0000.png")
else:
    print("[경고] RGB 데이터 없음")

if bbox2d_data is not None:
    with open(f"{OUTPUT_DIR}/bbox2d_0000.json", "w") as f:
        json.dump(bbox2d_data, f, indent=2, default=str)
    print(f"2D BBox 저장: {OUTPUT_DIR}/bbox2d_0000.json")
    if "data" in bbox2d_data:
        print(f"  감지된 객체: {len(bbox2d_data['data'])}개")

if bbox3d_data is not None:
    with open(f"{OUTPUT_DIR}/bbox3d_0000.json", "w") as f:
        json.dump(bbox3d_data, f, indent=2, default=str)
    print(f"3D BBox 저장: {OUTPUT_DIR}/bbox3d_0000.json")

print("\n=== 완료 ===")
print(f"결과물 위치: {OUTPUT_DIR}/")

while app.is_running():
    app.update()

app.close()
