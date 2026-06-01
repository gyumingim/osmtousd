import math
import requests
import geopandas as gpd
from shapely.geometry import shape, Polygon, MultiPolygon

WFS_URL = "https://api.vworld.kr/req/wfs"
LAYER = "lt_c_bldginfo"  # 건축물정보 레이어


def _bbox(lat, lon, radius_m):
    """Center + radius -> (minLon, minLat, maxLon, maxLat) in WGS84"""
    dlat = radius_m / 111000
    dlon = radius_m / (111000 * math.cos(math.radians(lat)))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


TILE_GRID = 6   # NxN grid tiles -- 4 was hitting 1000-limit on dense tiles
MAX_FEATURES = 1000


def _fetch_tile(bbox_str, api_key):
    """Fetch one tile. Returns list of features."""
    params = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typename": LAYER,
        "key": api_key,
        "bbox": bbox_str,
        "srsname": "EPSG:4326",
        "output": "application/json",
        "maxfeatures": MAX_FEATURES,
    }
    resp = requests.get(WFS_URL, params=params, timeout=30)
    resp.raise_for_status()
    feats = resp.json().get("features", [])
    if len(feats) >= MAX_FEATURES:
        print(f"    [warn] tile {bbox_str[:30]}... hit limit ({MAX_FEATURES})")
    return feats


def fetch_vworld_buildings(center, radius_m, api_key):
    """
    Fetch building polygons from Vworld WFS by splitting area into
    TILE_GRID x TILE_GRID tiles. Vworld WFS ignores startindex,
    so tiling is the only way to get more than 1000 features.
    """
    lat, lon = center
    minx, miny, maxx, maxy = _bbox(lat, lon, radius_m)

    dx = (maxx - minx) / TILE_GRID
    dy = (maxy - miny) / TILE_GRID

    seen_ids = set()
    all_features = []

    for row in range(TILE_GRID):
        for col in range(TILE_GRID):
            tx0 = minx + col * dx
            ty0 = miny + row * dy
            tx1 = tx0 + dx
            ty1 = ty0 + dy
            bbox_str = f"{tx0},{ty0},{tx1},{ty1}"
            try:
                feats = _fetch_tile(bbox_str, api_key)
            except Exception as e:
                print(f"  [vworld] tile ({row},{col}) failed: {e}")
                continue
            for feat in feats:
                fid = feat.get("properties", {}).get("ufid") or str(feat)
                if fid not in seen_ids:
                    seen_ids.add(fid)
                    all_features.append(feat)
        print(f"  [vworld] row {row+1}/{TILE_GRID} done, "
              f"unique buildings so far: {len(all_features)}", flush=True)

    if not all_features:
        print("  [vworld] no features returned")
        return None

    geoms, props = [], []
    for feat in all_features:
        try:
            geom = shape(feat["geometry"])
            if not isinstance(geom, (Polygon, MultiPolygon)):
                continue
            geoms.append(geom)
            props.append(feat.get("properties", {}))
        except Exception:
            continue

    if not geoms:
        return None

    gdf = gpd.GeoDataFrame(props, geometry=geoms, crs="EPSG:4326")
    print(f"  [vworld] total {len(gdf)} unique buildings")
    return gdf


def to_local_coords(gdf, utm_crs, cx, cy):
    """Project GDF to UTM and translate to local origin."""
    gdf = gdf.to_crs(utm_crs).copy()
    gdf.geometry = gdf.geometry.translate(-cx, -cy)
    return gdf


def fetch_vworld_traffic_signals(center, radius_m, api_key):
    """
    Fetch traffic signal positions from Vworld (lt_p_c1trafficlight).
    Returns list of (x, y) in local meter coords, or [].
    """
    from pyproj import Transformer
    lat, lon = center
    minx, miny, maxx, maxy = _bbox(lat, lon, radius_m)
    bbox_str = f"{minx},{miny},{maxx},{maxy}"
    params = {
        "service": "WFS", "version": "1.1.0", "request": "GetFeature",
        "typename": "lt_p_c1trafficlight", "key": api_key,
        "bbox": bbox_str, "srsname": "EPSG:4326",
        "output": "application/json", "maxfeatures": 1000,
    }
    try:
        resp = requests.get(WFS_URL, params=params, timeout=15)
        feats = resp.json().get("features", [])
    except Exception as e:
        print(f"  [vworld signals] failed: {e}")
        return []

    # Project to local UTM coords
    from shapely.geometry import Point
    import geopandas as gpd
    if not feats:
        return []
    pts = [shape(f["geometry"]) for f in feats
           if f.get("geometry", {}).get("type") == "Point"]
    gdf = gpd.GeoDataFrame(geometry=pts, crs="EPSG:4326")

    # Get UTM CRS from a reference
    gdf_utm = gdf.to_crs(gdf.estimate_utm_crs())
    t = Transformer.from_crs("EPSG:4326", gdf_utm.crs, always_xy=True)
    cx, cy = t.transform(lon, lat)
    coords = [(geom.x - cx, geom.y - cy) for geom in gdf_utm.geometry]
    print(f"  [vworld signals] {len(coords)} traffic signals")
    return coords


def fetch_vworld_crossings(center, radius_m, api_key):
    """
    Fetch crosswalk polygons from Vworld (lt_c_b3surfacemark).
    Returns list of Shapely Polygons in local meter coords, or [].
    """
    from pyproj import Transformer
    import geopandas as gpd
    lat, lon = center
    minx, miny, maxx, maxy = _bbox(lat, lon, radius_m)
    bbox_str = f"{minx},{miny},{maxx},{maxy}"
    params = {
        "service": "WFS", "version": "1.1.0", "request": "GetFeature",
        "typename": "lt_c_b3surfacemark", "key": api_key,
        "bbox": bbox_str, "srsname": "EPSG:4326",
        "output": "application/json", "maxfeatures": 1000,
    }
    try:
        resp = requests.get(WFS_URL, params=params, timeout=15)
        feats = resp.json().get("features", [])
    except Exception as e:
        print(f"  [vworld crossings] failed: {e}")
        return []

    geoms = []
    for f in feats:
        try:
            geoms.append(shape(f["geometry"]))
        except Exception:
            continue

    if not geoms:
        return []

    gdf = gpd.GeoDataFrame(geometry=geoms, crs="EPSG:4326")
    gdf_utm = gdf.to_crs(gdf.estimate_utm_crs())
    t = Transformer.from_crs("EPSG:4326", gdf_utm.crs, always_xy=True)
    cx, cy = t.transform(lon, lat)
    gdf_utm.geometry = gdf_utm.geometry.translate(-cx, -cy)

    polys = []
    for geom in gdf_utm.geometry:
        if isinstance(geom, Polygon):
            polys.append(geom)
        elif isinstance(geom, MultiPolygon):
            polys.extend(geom.geoms)
    print(f"  [vworld crossings] {len(polys)} crosswalk polygons")
    return polys


def get_vworld_height(row) -> float:
    """Extract building height from Vworld attributes."""
    h = row.get("height")
    if h is not None:
        try:
            v = float(h)
            if v > 0:
                return v
        except (ValueError, TypeError):
            pass
    floors = row.get("grnd_flr")
    if floors is not None:
        try:
            v = float(floors) * 3.0
            if v > 0:
                return v
        except (ValueError, TypeError):
            pass
    return 10.0
