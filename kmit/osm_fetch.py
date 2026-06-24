import osmnx as ox
from pyproj import Transformer

# 경북 구미시 1공단로 135 (lat, lon)
CENTER = (36.102064, 128.376468)
RADIUS = 2000  # meters

# Point features to fetch: {display_label: {tag_key: tag_value}}
POINT_FEATURES = {
    # Road infrastructure
    "traffic_signals":  {"highway": "traffic_signals"},
    "crossing":         {"highway": "crossing"},
    "bus_stop":         {"highway": "bus_stop"},
    # Public transport
    "platform":         {"public_transport": "platform"},
    "stop_position":    {"public_transport": "stop_position"},
    "station":          {"public_transport": "station"},
    # Food & drink
    "restaurant":       {"amenity": "restaurant"},
    "cafe":             {"amenity": "cafe"},
    "bar":              {"amenity": "bar"},
    "pub":              {"amenity": "pub"},
    "fast_food":        {"amenity": "fast_food"},
    "ice_cream":        {"amenity": "ice_cream"},
    # Healthcare
    "hospital":         {"amenity": "hospital"},
    "dentist":          {"amenity": "dentist"},
    # Finance
    "bank":             {"amenity": "bank"},
    "atm":              {"amenity": "atm"},
    # Public services
    "townhall":         {"amenity": "townhall"},
    "post_office":      {"amenity": "post_office"},
    "police":           {"amenity": "police"},
    "kindergarten":     {"amenity": "kindergarten"},
    "library":          {"amenity": "library"},
    "parking_space":    {"amenity": "parking_space"},
    "fuel":             {"amenity": "fuel"},
    "childcare":        {"amenity": "childcare"},
    "public_bath":      {"amenity": "public_bath"},
    "cinema":           {"amenity": "cinema"},
    "arts_centre":      {"amenity": "arts_centre"},
    "marketplace":      {"amenity": "marketplace"},
    "place_of_worship": {"amenity": "place_of_worship"},
    # Shops
    "supermarket":      {"shop": "supermarket"},
    "convenience":      {"shop": "convenience"},
    "bakery":           {"shop": "bakery"},
    "books":            {"shop": "books"},
    "laundry":          {"shop": "laundry"},
    "hairdresser":      {"shop": "hairdresser"},
    "florist":          {"shop": "florist"},
    "clothes":          {"shop": "clothes"},
    "beauty":           {"shop": "beauty"},
    # Tourism
    "motel":            {"tourism": "motel"},
    "hostel":           {"tourism": "hostel"},
    "museum":           {"tourism": "museum"},
    "viewpoint":        {"tourism": "viewpoint"},
    # Leisure
    "sauna":            {"leisure": "sauna"},
    # Barriers
    "gate":             {"barrier": "gate"},
    "lift_gate":        {"barrier": "lift_gate"},
}


def _compute_origin(gdf):
    """WGS84 center -> UTM origin (meters) for local coordinate system"""
    t = Transformer.from_crs("EPSG:4326", gdf.crs, always_xy=True)
    cx, cy = t.transform(CENTER[1], CENTER[0])
    return cx, cy


def fetch_buildings():
    gdf = ox.features_from_point(CENTER, tags={"building": True}, dist=RADIUS)
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    gdf = ox.projection.project_gdf(gdf)
    cx, cy = _compute_origin(gdf)
    gdf = gdf.copy()
    gdf.geometry = gdf.geometry.translate(-cx, -cy)
    return gdf


def fetch_roads():
    G = ox.graph_from_point(CENTER, dist=RADIUS, network_type="all")
    _, edges = ox.graph_to_gdfs(G)
    edges = ox.projection.project_gdf(edges)
    cx, cy = _compute_origin(edges)
    edges = edges.copy()
    edges.geometry = edges.geometry.translate(-cx, -cy)
    return edges


def fetch_points(utm_crs=None):
    """
    Fetch all POINT_FEATURES in a single Overpass request,
    then classify client-side.
    Returns: {label: [(x, y), ...]} in local meter coordinates
    """
    if utm_crs is None:
        # Fallback: derive CRS from a small building query
        ref = ox.features_from_point(
            CENTER, tags={"building": True}, dist=RADIUS
        )
        ref = ox.projection.project_gdf(ref)
        utm_crs = ref.crs
    t = Transformer.from_crs("EPSG:4326", utm_crs, always_xy=True)
    cx, cy = t.transform(CENTER[1], CENTER[0])

    # Merge all tags into one combined dict -> single Overpass request
    combined: dict = {}
    for tags in POINT_FEATURES.values():
        for k, v in tags.items():
            combined.setdefault(k, []).append(v)

    print("  Sending single Overpass API request...", flush=True)
    gdf = ox.features_from_point(CENTER, tags=combined, dist=RADIUS)
    gdf = gdf[gdf.geometry.geom_type == "Point"].to_crs(utm_crs)
    print(f"  Received {len(gdf)} points, classifying...")

    result = {}
    for label, tags in POINT_FEATURES.items():
        key, val = next(iter(tags.items()))
        if key not in gdf.columns:
            continue
        matched = gdf[gdf[key] == val]
        if len(matched) == 0:
            continue
        coords = [(geom.x - cx, geom.y - cy) for geom in matched.geometry]
        result[label] = coords
        print(f"    {label}: {len(coords)}")

    return result
