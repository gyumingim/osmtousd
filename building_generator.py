import math
import random
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree
from geo_to_mesh import polygon_to_mesh, get_road_width

# Amenity types that represent physical buildings worth generating
BUILDING_AMENITIES = {
    "restaurant", "cafe", "bar", "pub", "fast_food", "ice_cream",
    "hospital", "dentist", "bank", "police", "post_office", "townhall",
    "kindergarten", "library", "fuel", "childcare", "public_bath",
    "cinema", "arts_centre", "marketplace", "place_of_worship",
    "supermarket", "convenience", "bakery", "books", "laundry",
    "hairdresser", "florist", "clothes", "beauty", "motel", "hostel", "museum",
    "bus_stop", "platform",
}

# Base footprint size (width x depth) in meters per amenity type
AMENITY_SIZES = {
    "supermarket":      (35, 25),
    "hospital":         (25, 15),
    "cinema":           (25, 15),
    "museum":           (20, 15),
    "arts_centre":      (20, 15),
    "police":           (20, 15),
    "townhall":         (20, 15),
    "marketplace":      (20, 15),
    "place_of_worship": (15, 12),
    "fuel":             (15, 10),
    "post_office":      (15, 10),
    "library":          (15, 10),
    "kindergarten":     (15, 10),
    "childcare":        (12, 8),
    "restaurant":       (12, 8),
    "dentist":          (12, 8),
    "public_bath":      (12, 8),
    "motel":            (12, 8),
    "hostel":           (12, 8),
    "bank":             (12, 8),
    "books":            (10, 8),
    "clothes":          (10, 8),
    "cafe":             (8, 6),
    "convenience":      (8, 6),
    "bakery":           (8, 6),
    "laundry":          (8, 6),
    "hairdresser":      (8, 6),
    "florist":          (8, 6),
    "bar":              (8, 6),
    "pub":              (8, 6),
    "fast_food":        (8, 6),
    "beauty":           (8, 6),
    "ice_cream":        (6, 5),
    "bus_stop":         (4, 2),
    "platform":         (6, 3),
}
_DEFAULT_SIZE = (10, 8)


def _make_rect(cx, cy, width, depth, angle):
    hw, hd = width / 2, depth / 2
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return Polygon([
        (cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a)
        for x, y in [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
    ])


def _road_angle(point, roads_gdf, roads_tree):
    idx = roads_tree.nearest(point)
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


def _push_off_road(x, y, roads_gdf, roads_tree, dist):
    """
    Offset (x, y) perpendicular away from nearest road by dist meters.
    Returns two candidates: pushed left and pushed right of road.
    """
    from shapely.geometry import Point
    idx = roads_tree.nearest(Point(x, y))
    geom = roads_gdf.geometry.iloc[idx]
    nearest_pt = geom.interpolate(geom.project(Point(x, y)))

    # Perpendicular direction away from nearest point on road
    vx = x - nearest_pt.x
    vy = y - nearest_pt.y
    length = math.sqrt(vx * vx + vy * vy)
    if length < 1e-6:
        # Point is ON the road centerline -- use road-normal direction
        angle = _road_angle(Point(x, y), roads_gdf, roads_tree)
        vx, vy = -math.sin(angle), math.cos(angle)
        length = 1.0
    vx /= length
    vy /= length
    return (x + vx * dist, y + vy * dist)


# Only vehicle roads block building placement; footways/paths are fine
_VEHICLE_ROADS = {
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "unclassified", "residential", "living_street", "service",
    "motorway_link", "trunk_link", "primary_link",
    "secondary_link", "tertiary_link", "busway",
}


def _is_vehicle_road(highway):
    if isinstance(highway, list):
        highway = highway[0]
    return str(highway) in _VEHICLE_ROADS


def _build_road_polys(roads_gdf):
    """Buffer vehicle road linestrings into footprint polygons."""
    polys = []
    for _, row in roads_gdf.iterrows():
        if not _is_vehicle_road(row.get("highway", "")):
            continue
        width = get_road_width(row.get("highway", "residential"))
        buffered = row.geometry.buffer(width / 2, cap_style=2, join_style=2)
        if not buffered.is_empty:
            polys.append(buffered)
    return polys


def generate_missing_buildings(buildings_gdf, roads_gdf, points_data):
    """
    Generate rectangular building polygons for amenity points not inside
    any existing building. Returns list of (points, face_counts, face_indices).
    """
    existing_polys = buildings_gdf.geometry.tolist()
    buildings_tree = STRtree(existing_polys)

    print("  Pre-computing road footprints...", flush=True)
    road_polys = _build_road_polys(roads_gdf)
    roads_tree = STRtree(road_polys)

    # roads_tree for angle lookup uses original linestrings
    roads_line_tree = STRtree(roads_gdf.geometry.tolist())

    generated_polys = []
    meshes = []
    n_generated = n_has_building = n_overlap = 0

    for label, coords in points_data.items():
        if label not in BUILDING_AMENITIES:
            continue

        base_w, base_d = AMENITY_SIZES.get(label, _DEFAULT_SIZE)

        for x, y in coords:
            pt = Point(x, y)

            # Skip if already inside an existing building
            if len(buildings_tree.query(pt, predicate='within')) > 0:
                n_has_building += 1
                continue

            angle = _road_angle(pt, roads_gdf, roads_line_tree)
            if label in ("bus_stop", "platform"):
                height = 2.5  # shelter height
            else:
                height = random.randint(2, 3) * 3.0  # 2~3 floors x 3m

            # Candidate positions to try: original + pushed off road
            push_dist = base_d * 0.5 + 3.0  # half-depth + small margin
            ox, oy = _push_off_road(
                x, y, roads_gdf, roads_line_tree, push_dist
            )
            positions = [(x, y), (ox, oy)]

            placed = None
            for cx, cy in positions:
                if placed:
                    break
                for attempt in range(4):
                    scale = random.uniform(0.9, 1.1) * (0.8 ** attempt)
                    w = base_w * scale
                    d = base_d * scale
                    candidate = _make_rect(cx, cy, w, d, angle)

                    hits_building = len(
                        buildings_tree.query(candidate, predicate='intersects')
                    ) > 0
                    hits_road = len(
                        roads_tree.query(candidate, predicate='intersects')
                    ) > 0
                    hits_generated = any(
                        candidate.intersects(p) for p in generated_polys
                    )

                    if not (hits_building or hits_road or hits_generated):
                        placed = candidate
                        break

            if placed is None:
                n_overlap += 1
                continue

            mesh = polygon_to_mesh(placed, height)
            if mesh is not None:
                meshes.append(mesh)
                generated_polys.append(placed)
                n_generated += 1

    print(
        f"  generated: {n_generated}  "
        f"skipped (inside building): {n_has_building}  "
        f"skipped (no space): {n_overlap}"
    )
    return meshes
