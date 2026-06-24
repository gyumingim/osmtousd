"""
OSM 전체 피처를 구미시 반경 내에서 fetch해 osm_data/ 에 GeoJSON으로 저장.
이미 파일이 있고 유효하면 skip (재실행 시 캐시로 동작).

실행: python3 osm_fetcher.py
읽기: from osm_fetcher import load_layer
"""

import os
import json
import osmnx as ox
from osm_fetch import CENTER, RADIUS

OUTPUT_DIR = "osm_data"

# ── 레이어 목록 (key: 저장 파일명, value: (한글명, tags dict)) ────────────
LAYERS = {
    # 건물
    "buildings":            ("건물",              {"building": True}),
    # 도로
    "roads":                ("도로(엣지)",         None),   # 별도 graph 처리
    # 철도
    "railways":             ("철도",              {"railway": True}),
    # 수계
    "waterways":            ("수계",              {"waterway": True}),
    "water":                ("수면",              {"natural": "water"}),
    # 자연
    "natural":              ("자연지형",           {"natural": True}),
    "wood":                 ("숲",               {"landuse": "forest"}),
    # 토지이용
    "landuse":              ("토지이용",           {"landuse": True}),
    # 편의시설
    "amenity":              ("편의시설",           {"amenity": True}),
    # 상점
    "shop":                 ("상점",              {"shop": True}),
    # 관광
    "tourism":              ("관광",              {"tourism": True}),
    # 여가
    "leisure":              ("여가",              {"leisure": True}),
    # 대중교통
    "public_transport":     ("대중교통",           {"public_transport": True}),
    # 장벽/시설물
    "barrier":              ("장벽",              {"barrier": True}),
    "man_made":             ("인공구조물",         {"man_made": True}),
    # 전력
    "power":                ("전력시설",           {"power": True}),
    # 긴급
    "emergency":            ("긴급시설",           {"emergency": True}),
    # 의료
    "healthcare":           ("의료",              {"healthcare": True}),
    # 역사
    "historic":             ("역사유산",           {"historic": True}),
    # 군사
    "military":             ("군사시설",           {"military": True}),
    # 항공
    "aeroway":              ("항공시설",           {"aeroway": True}),
    # 지명
    "place":                ("지명",              {"place": True}),
    # 스포츠
    "sport":                ("스포츠",            {"sport": True}),
    # 교통 인프라 (포인트)
    "traffic_signals":      ("신호등",            {"highway": "traffic_signals"}),
    "crossings":            ("횡단보도",           {"highway": "crossing"}),
    "bus_stop":             ("버스정류장",         {"highway": "bus_stop"}),
    "street_lamp":          ("가로등",            {"highway": "street_lamp"}),
    "speed_camera":         ("과속카메라",         {"highway": "speed_camera"}),
    # 주차
    "parking":              ("주차장",            {"amenity": "parking"}),
    "parking_space":        ("주차면",            {"amenity": "parking_space"}),
    # 경계
    "boundary_admin":       ("행정경계",           {"boundary": "administrative"}),
    # 지표면
    "surface":              ("지표면",            {"surface": True}),
    # 보행자
    "footway":              ("보행로",            {"highway": "footway"}),
    "cycleway":             ("자전거도로",         {"highway": "cycleway"}),
    "path":                 ("산책로",            {"highway": "path"}),
    "steps":                ("계단",              {"highway": "steps"}),
    # 광장/보행구역
    "pedestrian_area":      ("보행광장",           {"highway": "pedestrian"}),
    # 녹지
    "park":                 ("공원",              {"leisure": "park"}),
    "playground":           ("놀이터",            {"leisure": "playground"}),
    "pitch":                ("운동장",            {"leisure": "pitch"}),
    "garden":               ("정원",              {"leisure": "garden"}),
    # 교육
    "school":               ("학교",              {"amenity": "school"}),
    "university":           ("대학교",            {"amenity": "university"}),
    "kindergarten":         ("유치원",            {"amenity": "kindergarten"}),
    # 의료시설
    "hospital":             ("병원",              {"amenity": "hospital"}),
    "clinic":               ("의원",              {"amenity": "clinic"}),
    "pharmacy":             ("약국",              {"amenity": "pharmacy"}),
    # 종교
    "place_of_worship":     ("종교시설",           {"amenity": "place_of_worship"}),
    # 공공시설
    "police":               ("경찰서",            {"amenity": "police"}),
    "fire_station":         ("소방서",            {"amenity": "fire_station"}),
    "post_office":          ("우체국",            {"amenity": "post_office"}),
    "townhall":             ("시청/구청",          {"amenity": "townhall"}),
    # 식음료
    "restaurant":           ("음식점",            {"amenity": "restaurant"}),
    "cafe":                 ("카페",              {"amenity": "cafe"}),
    "fast_food":            ("패스트푸드",         {"amenity": "fast_food"}),
    "bar":                  ("술집",              {"amenity": "bar"}),
    # 금융
    "bank":                 ("은행",              {"amenity": "bank"}),
    "atm":                  ("ATM",              {"amenity": "atm"}),
    # 주유소/충전소
    "fuel":                 ("주유소",            {"amenity": "fuel"}),
    "charging_station":     ("충전소",            {"amenity": "charging_station"}),
    # 숙박
    "hotel":                ("호텔",              {"tourism": "hotel"}),
    "motel":                ("모텔",              {"tourism": "motel"}),
    # 문화시설
    "museum":               ("박물관",            {"tourism": "museum"}),
    "library":              ("도서관",            {"amenity": "library"}),
    "cinema":               ("영화관",            {"amenity": "cinema"}),
    # 슈퍼/편의점
    "supermarket":          ("슈퍼마켓",           {"shop": "supermarket"}),
    "convenience":          ("편의점",            {"shop": "convenience"}),
}


def _is_valid_geojson(path):
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("features"))
    except Exception:
        return False


def _gdf_to_geojson_features(gdf):
    """GeoDataFrame → GeoJSON features 리스트 (EPSG:4326)."""
    if gdf is None or len(gdf) == 0:
        return []
    # WGS84로 변환
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    # 멀티인덱스 평탄화
    if isinstance(gdf.index, type(gdf.index)) and hasattr(gdf.index, 'levels'):
        gdf = gdf.reset_index()
    raw = json.loads(gdf.to_json())
    return raw.get("features", [])


def fetch_layer(name, desc, tags):
    """tags로 OSM features fetch → GeoJSON features 리스트."""
    try:
        gdf = ox.features_from_point(CENTER, tags=tags, dist=RADIUS)
        return _gdf_to_geojson_features(gdf)
    except Exception as e:
        if "No results" in str(e) or "HTTPError" in str(e):
            return []
        raise


def fetch_roads():
    """도로 네트워크 → GeoJSON features 리스트."""
    G = ox.graph_from_point(CENTER, dist=RADIUS, network_type="all")
    _, edges = ox.graph_to_gdfs(G)
    return _gdf_to_geojson_features(edges)


def save_layer(name, features):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"{name}.geojson")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features},
                  f, ensure_ascii=False)
    return path


def load_layer(name):
    """저장된 GeoJSON 읽기. 없으면 None."""
    path = os.path.join(OUTPUT_DIR, f"{name}.geojson")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fetch_all(force=False):
    total = len(LAYERS)
    saved, skipped, empty, errors = [], [], [], []
    log = {}

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log_path = os.path.join(OUTPUT_DIR, "fetch_log.json")

    for i, (name, (desc, tags)) in enumerate(LAYERS.items(), 1):
        path = os.path.join(OUTPUT_DIR, f"{name}.geojson")
        if not force and _is_valid_geojson(path):
            print(f"[{i:3}/{total}] SKIP  {name} ({desc})")
            skipped.append(name)
            log[name] = {"status": "skip", "desc": desc}
            continue

        print(f"[{i:3}/{total}] FETCH {name} ({desc})...", end=" ", flush=True)
        try:
            if tags is None:  # roads 특수처리
                features = fetch_roads()
            else:
                features = fetch_layer(name, desc, tags)
        except Exception as e:
            msg = str(e)
            print(f"ERROR: {msg}")
            errors.append(name)
            log[name] = {"status": "error", "desc": desc, "error": msg}
        else:
            if features:
                save_layer(name, features)
                print(f"{len(features)}개 저장")
                saved.append(name)
                log[name] = {"status": "saved", "desc": desc, "count": len(features)}
            else:
                print("데이터 없음")
                empty.append(name)
                log[name] = {"status": "empty", "desc": desc, "count": 0}

        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

    print("\n=== 완료 ===")
    print(f"  저장:        {len(saved)}개")
    print(f"  skip(기존):  {len(skipped)}개")
    print(f"  데이터없음:  {len(empty)}개")
    print(f"  에러:        {len(errors)}개")
    if errors:
        print(f"  에러 레이어: {errors}")
    print(f"  로그: {log_path}")


if __name__ == "__main__":
    import sys
    fetch_all(force="--force" in sys.argv)
