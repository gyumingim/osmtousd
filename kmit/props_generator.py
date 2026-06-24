import math
from shapely.geometry import Polygon, Point
from shapely.strtree import STRtree
from geo_to_mesh import polygon_to_mesh


def _road_angle(x, y, roads_gdf, roads_tree):
    idx = roads_tree.nearest(Point(x, y))
    geom = roads_gdf.geometry.iloc[idx]
    coords = (
        list(geom.geoms[0].coords)
        if hasattr(geom, 'geoms')
        else list(geom.coords)
    )
    if len(coords) < 2:
        return 0.0
    dx = coords[-1][0] - coords[0][0]
    dy = coords[-1][1] - coords[0][1]
    return math.atan2(dy, dx) if (dx * dx + dy * dy) > 0 else 0.0


def _rect(cx, cy, w, d, angle):
    hw, hd = w / 2, d / 2
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return Polygon([
        (cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a)
        for x, y in [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
    ])


def _vehicle_signal_meshes(x, y, angle=0.0):
    """차량용(1): 폴 2x2x50m + 가로 박스(도로 방향) 5x3x8m at 45m."""
    pole = polygon_to_mesh(_rect(x, y, 2, 2, 0), height=50.0, base_z=0.0)
    box = polygon_to_mesh(_rect(x, y, 5, 3, angle), height=8.0, base_z=45.0)
    return [m for m in (pole, box) if m]


def _pedestrian_signal_meshes(x, y, angle=0.0):
    """보행자용(2): 폴 1.5x1.5x30m + 세로 박스(도로 수직) 2x1.5x6m at 25m."""
    perp = angle + math.pi / 2
    pole = polygon_to_mesh(_rect(x, y, 1.5, 1.5, 0), height=30.0, base_z=0.0)
    box = polygon_to_mesh(_rect(x, y, 2, 1.5, perp), height=6.0, base_z=25.0)
    return [m for m in (pole, box) if m]


def _flashing_signal_meshes(x, y, angle=0.0):
    """황색점멸(6): 폴 1.5x1.5x35m + 소형 박스 2.5x2.5x2.5m at 33m."""
    pole = polygon_to_mesh(_rect(x, y, 1.5, 1.5, 0), height=35.0, base_z=0.0)
    box = polygon_to_mesh(
        _rect(x, y, 2.5, 2.5, angle), height=2.5, base_z=33.0
    )
    return [m for m in (pole, box) if m]


def make_traffic_signal_meshes(coords):
    """
    (x, y, type) or (x, y, type, angle) list → list of meshes.
    type: 1=차량용, 2=보행자용, 6=황색점멸
    angle: 도로 방향(라디안), 없으면 0
    """
    meshes = []
    for item in coords:
        if len(item) == 4:
            x, y, sig_type, angle = item
        elif len(item) == 3:
            x, y, sig_type = item
            angle = 0.0
        else:
            x, y = item
            sig_type, angle = 1, 0.0

        if sig_type == 2:
            meshes.extend(_pedestrian_signal_meshes(x, y, angle))
        elif sig_type == 6:
            meshes.extend(_flashing_signal_meshes(x, y, angle))
        else:
            meshes.extend(_vehicle_signal_meshes(x, y, angle))
    return meshes


def _crossing_stripes(x, y, angle, cw_length, cw_width,
                      base_z=0.02, stripe_h=0.04):
    """공통 줄무늬 생성. cw_length=연장(도로수직), cw_width=폭(도로방향)."""
    perp = angle + math.pi / 2
    stripe_d = 0.45                          # 줄무늬 두께
    spacing = 0.9                            # 줄무늬 간격(중심-중심)
    n = max(round(cw_width / spacing), 1)   # 줄무늬 개수

    meshes = []
    for i in range(n):
        offset = (i - (n - 1) / 2) * spacing
        sx = x + offset * math.cos(angle)
        sy = y + offset * math.sin(angle)
        stripe = polygon_to_mesh(
            _rect(sx, sy, cw_length, stripe_d, perp),
            height=stripe_h, base_z=base_z,
        )
        if stripe:
            meshes.append(stripe)
    return meshes


def make_crossing_meshes(coords, roads_gdf):
    """
    (x, y) list → 기본 치수(연장 5m, 폭 4m) 횡단보도 메시.
    fallback용 — CSV 데이터 없을 때 사용.
    """
    roads_tree = STRtree(roads_gdf.geometry.tolist())
    meshes = []
    for x, y in coords:
        angle = _road_angle(x, y, roads_gdf, roads_tree)
        meshes.extend(_crossing_stripes(x, y, angle, 5.0, 4.0))
    return meshes


def make_crossing_meshes_from_data(crosswalk_data, roads_gdf):
    """
    횡단보도 CSV dict 리스트 → 실제 치수 기반 메시.
    kind='04'(고원식)은 높이 15cm로 처리.
    """
    roads_tree = STRtree(roads_gdf.geometry.tolist())
    meshes = []
    for cw in crosswalk_data:
        x, y = cw["x"], cw["y"]
        angle = _road_angle(x, y, roads_gdf, roads_tree)
        elevated = cw["kind"] == "04"
        base_z = 0.13 if elevated else 0.02
        stripe_h = 0.04
        meshes.extend(_crossing_stripes(
            x, y, angle,
            cw_length=cw["length"],
            cw_width=cw["width"],
            base_z=base_z,
            stripe_h=stripe_h,
        ))
    return meshes
