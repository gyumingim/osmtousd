"""
vworld_data/*.geojson → 로컬 UTM GeoDataFrame 변환 유틸.
vworld_fetcher.py 먼저 실행해 JSON 파일을 생성해야 함.
"""

import os
import json
import geopandas as gpd
from shapely.geometry import shape
from pyproj import Transformer
from vworld_fetcher import load_layer
from osm_fetch import CENTER

UTM_CRS = "EPSG:32652"   # WGS84 UTM Zone 52N (구미 128°E)

_origin = None


def _get_origin():
    global _origin
    if _origin is None:
        t = Transformer.from_crs("EPSG:4326", UTM_CRS, always_xy=True)
        cx, cy = t.transform(CENTER[1], CENTER[0])
        _origin = (cx, cy)
    return _origin


def _geojson_to_gdf(data):
    """GeoJSON dict → 로컬 UTM GeoDataFrame."""
    if not data or not data.get("features"):
        return None
    cx, cy = _get_origin()
    geoms, props = [], []
    for f in data["features"]:
        try:
            geoms.append(shape(f["geometry"]))
            props.append(f.get("properties", {}))
        except Exception:
            continue
    if not geoms:
        return None
    gdf = gpd.GeoDataFrame(props, geometry=geoms, crs="EPSG:4326")
    gdf = gdf.to_crs(UTM_CRS)
    gdf.geometry = gdf.geometry.translate(-cx, -cy)
    return gdf


def load_as_gdf(typename):
    """Vworld GeoJSON (vworld_data/) → 로컬 UTM GeoDataFrame."""
    return _geojson_to_gdf(load_layer(typename))


def load_osm_gdf(name):
    """OSM GeoJSON (osm_data/) → 로컬 UTM GeoDataFrame."""
    path = os.path.join("osm_data", f"{name}.geojson")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return _geojson_to_gdf(json.load(f))


def load_points(typename):
    """Point 레이어 → [(x, y), ...] 로컬 좌표."""
    gdf = load_as_gdf(typename)
    if gdf is None:
        return []
    return [
        (row.geometry.x, row.geometry.y)
        for _, row in gdf.iterrows()
        if row.geometry is not None and row.geometry.geom_type == "Point"
    ]


# Vworld point 레이어 → points_data 키 매핑
_POINT_LAYERS = {
    "traffic_signals":    "lt_p_c1trafficlight",
    "cctv":               "lt_p_utiscctv",
    "tourist_info":       "lt_p_dgtouristinfo",
    "traditional_market": "lt_p_tradsijang",
    "museum":             "lt_p_dgmuseumart",
    "library":            "lt_p_smalllibrary",
    "incubator":          "lt_p_busiincubator",
    "child_safety":       "lt_p_mgprtfa",
    "elderly_welfare":    "lt_p_mgprtfb",
    "child_welfare":      "lt_p_mgprtfc",
    "other_welfare":      "lt_p_mgprtfd",
    "place_name":         "lt_p_nsnmssitenm",
    "bicycle_rack":       "lt_p_bycracks",
    "safety_sign":        "lt_p_b1safetysign",
    "kilopost":           "lt_p_c2kilopost",
    "sign_post":          "lt_p_c6postpoint",
    "helipad":            "lt_p_aishcstrip",
    "golf":               "lt_p_sgisgolf",
    "groundwater":        "lt_p_sgisgwchg",
}


def load_points_data():
    """모든 Point 레이어 로드 → {category: [(x, y), ...]}."""
    result = {}
    for category, typename in _POINT_LAYERS.items():
        pts = load_points(typename)
        if pts:
            result[category] = pts
            print(f"    {category}: {len(pts)}")
    return result
