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


def make_traffic_signal_meshes(coords):
    """
    (x, y) list -> list of meshes.
    Each signal: vertical pole (0.2x0.2x4m) + light box (0.5x0.3x1m on top).
    """
    meshes = []
    for x, y in coords:
        pole = polygon_to_mesh(_rect(x, y, 0.2, 0.2, 0), height=4.0, base_z=0.0)
        box = polygon_to_mesh(_rect(x, y, 0.5, 0.3, 0), height=1.0, base_z=3.5)
        if pole:
            meshes.append(pole)
        if box:
            meshes.append(box)
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
