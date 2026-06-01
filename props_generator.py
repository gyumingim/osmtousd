import math
from shapely.geometry import Polygon
from shapely.strtree import STRtree
from geo_to_mesh import polygon_to_mesh


def _road_angle(x, y, roads_gdf, roads_tree):
    from shapely.geometry import Point
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


def _vehicle_signal_meshes(x, y):
    """차량용(1): 폴 2x2x50m + 가로 박스 5x3x8m at 45m."""
    pole = polygon_to_mesh(_rect(x, y, 2, 2, 0), height=50.0, base_z=0.0)
    box = polygon_to_mesh(_rect(x, y, 5, 3, 0), height=8.0, base_z=45.0)
    return [m for m in (pole, box) if m]


def _pedestrian_signal_meshes(x, y):
    """보행자용(2): 폴 1.5x1.5x30m + 세로 박스 2x1.5x6m at 25m."""
    pole = polygon_to_mesh(_rect(x, y, 1.5, 1.5, 0), height=30.0, base_z=0.0)
    box = polygon_to_mesh(_rect(x, y, 2, 1.5, 0), height=6.0, base_z=25.0)
    return [m for m in (pole, box) if m]


def _flashing_signal_meshes(x, y):
    """황색점멸(6): 폴 1.5x1.5x35m + 소형 박스 2.5x2.5x2.5m at 33m."""
    pole = polygon_to_mesh(_rect(x, y, 1.5, 1.5, 0), height=35.0, base_z=0.0)
    box = polygon_to_mesh(_rect(x, y, 2.5, 2.5, 0), height=2.5, base_z=33.0)
    return [m for m in (pole, box) if m]


def make_traffic_signal_meshes(coords):
    """
    (x, y) or (x, y, type) list -> list of meshes.
    type: 1=차량용, 2=보행자용, 6=황색점멸 (없으면 차량용으로 처리)
    """
    meshes = []
    for item in coords:
        if len(item) == 3:
            x, y, sig_type = item
        else:
            x, y = item
            sig_type = 1

        if sig_type == 2:
            meshes.extend(_pedestrian_signal_meshes(x, y))
        elif sig_type == 6:
            meshes.extend(_flashing_signal_meshes(x, y))
        else:
            meshes.extend(_vehicle_signal_meshes(x, y))
    return meshes


def make_crossing_meshes(coords, roads_gdf):
    """
    (x, y) list -> list of meshes.
    Each crossing: 5 white stripes perpendicular to nearest road.
    Stripe: 5m wide x 0.6m deep x 0.04m tall.
    """
    roads_tree = STRtree(roads_gdf.geometry.tolist())
    meshes = []

    n_stripes = 5
    stripe_w = 5.0    # across road
    stripe_d = 0.6    # along road direction
    stripe_h = 0.04   # height above ground
    spacing = 1.2     # center-to-center along road

    for x, y in coords:
        angle = _road_angle(x, y, roads_gdf, roads_tree)
        perp = angle + math.pi / 2  # stripes run perpendicular to road

        for i in range(n_stripes):
            offset = (i - (n_stripes - 1) / 2) * spacing
            sx = x + offset * math.cos(angle)
            sy = y + offset * math.sin(angle)
            stripe = polygon_to_mesh(
                _rect(sx, sy, stripe_w, stripe_d, perp),
                height=stripe_h,
                base_z=0.02,
            )
            if stripe:
                meshes.append(stripe)

    return meshes
