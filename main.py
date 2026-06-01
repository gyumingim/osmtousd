import os
import math
import pickle
from shapely.geometry import Polygon, Point
from shapely.strtree import STRtree
from pyproj import Transformer

from osm_fetch import CENTER, RADIUS
from vworld_loader import load_as_gdf, load_osm_gdf, load_points_data, UTM_CRS
from geo_to_mesh import (
    building_to_meshes, road_to_mesh, sidewalk_to_mesh, polygon_to_mesh,
)
from building_generator import generate_missing_buildings
from props_generator import (
    make_traffic_signal_meshes, make_crossing_meshes,
    make_crossing_meshes_from_data,
)
from csv_loader import load_traffic_signals_csv, load_crosswalks_csv
from usd_writer import write_usd

BLDG_SNAP_THRESHOLD = 100  # 건물 내부 신호등의 도로 엣지 스냅 최대 거리(m)


def process_signals(signal_coords, roads_gdf, buildings_gdf):
    """
    1. 도로 방향(angle) 계산
    2. 건물 내부 신호등 → 가장 가까운 도로 엣지 + 인도 오프셋으로 이동
    Returns: list of (x, y, type, angle)
    """
    from geo_to_mesh import _VWORLD_ROAD_WIDTHS

    road_geoms = roads_gdf.geometry.tolist()
    road_tree = STRtree(road_geoms)
    bldg_tree = STRtree(buildings_gdf.geometry.tolist())

    result, fixed = [], 0
    for x, y, sig_type in signal_coords:
        pt = Point(x, y)

        # 가장 가까운 도로 방향 계산
        road_idx = road_tree.nearest(pt)
        road_geom = road_geoms[road_idx]
        coords = (list(road_geom.geoms[0].coords)
                  if hasattr(road_geom, 'geoms')
                  else list(road_geom.coords))
        if len(coords) >= 2:
            dx = coords[-1][0] - coords[0][0]
            dy = coords[-1][1] - coords[0][1]
            angle = math.atan2(dy, dx) if (dx*dx + dy*dy) > 0 else 0.0
        else:
            angle = 0.0

        # 건물 내부 여부 확인
        inside = any(
            buildings_gdf.geometry.iloc[i].contains(pt)
            for i in bldg_tree.query(pt)
        )

        if inside:
            # 도로 위 최근접점 + 인도 방향 오프셋
            nearest_pt = road_geom.interpolate(road_geom.project(pt))
            road_row = roads_gdf.iloc[road_idx]
            rank = road_row.get("road_rank")
            try:
                width = float(road_row.get("lanes") or 0) * 3.5 or \
                        _VWORLD_ROAD_WIDTHS.get(str(rank), 4.0)
            except (TypeError, ValueError):
                width = 4.0

            # 원래 신호등이 도로의 어느 쪽에 있는지 판별
            perp_x = -math.sin(angle)
            perp_y = math.cos(angle)
            dot = (x - nearest_pt.x)*perp_x + (y - nearest_pt.y)*perp_y
            side = 1 if dot >= 0 else -1
            offset = width / 2 + 1.5  # 도로 반폭 + 인도 1.5m
            nx = nearest_pt.x + side * offset * perp_x
            ny = nearest_pt.y + side * offset * perp_y
            result.append((nx, ny, sig_type, angle))
            fixed += 1
        else:
            result.append((x, y, sig_type, angle))

    print(f"  신호등 처리: 건물 내부 {fixed}개 도로 엣지로 이동")
    return result


USD_OUTPUT = "gumi.usda"
CSV_SIGNALS_PATH = "경상북도_구미시_신호등_20260331.csv"
CSV_SIGNALS_CACHE = "csv_signals_cache.pkl"
CSV_CROSSWALKS_PATH = "경상북도_구미시_횡단보도_20260228.csv"
CSV_CROSSWALKS_CACHE = "csv_crosswalks_cache.pkl"


def main():
    print("=== Vworld -> USD conversion ===")

    print("1/4 Vworld 데이터 로드...")
    buildings_gdf = load_as_gdf("lt_c_bldginfo")
    roads_gdf = load_as_gdf("lt_l_moctlink")
    if buildings_gdf is None or roads_gdf is None:
        print("  [오류] vworld_data/ 파일 없음. 먼저 실행: python3 vworld_fetcher.py")
        return
    print(f"  건물: {len(buildings_gdf)}, 도로: {len(roads_gdf)}")

    print("2/4 Point 피처 로드...")
    points_data = load_points_data()
    print(f"  {len(points_data)} 카테고리")

    print("3/4 메시 생성...")
    building_meshes = []
    for _, row in buildings_gdf.iterrows():
        building_meshes.extend(building_to_meshes(row))

    osm_buildings_gdf = load_osm_gdf("buildings")
    if osm_buildings_gdf is not None:
        for _, row in osm_buildings_gdf.iterrows():
            building_meshes.extend(building_to_meshes(row))
        print(f"  OSM 건물 추가: {len(osm_buildings_gdf)}개")

    generated_meshes = generate_missing_buildings(
        buildings_gdf, roads_gdf, points_data
    )

    # 건물 STRtree 미리 계산 (도로·보도 클리핑용)
    bldg_geoms = buildings_gdf.geometry.tolist()
    bldg_tree = STRtree(bldg_geoms)

    road_meshes = []
    sidewalk_meshes = []
    for _, row in roads_gdf.iterrows():
        mesh = road_to_mesh(row)
        if mesh is not None:
            road_meshes.append(mesh)
        sw = sidewalk_to_mesh(row, bldg_tree, bldg_geoms)
        if sw is not None:
            sidewalk_meshes.append(sw)
    print(f"  도로: {len(road_meshes)}, 보도: {len(sidewalk_meshes)}")

    # 신호등: CSV 우선, 없으면 Vworld JSON
    if os.path.exists(CSV_SIGNALS_CACHE):
        with open(CSV_SIGNALS_CACHE, "rb") as f:
            signal_coords = pickle.load(f)
        print(f"  신호등 CSV 캐시: {len(signal_coords)}개")
    elif os.path.exists(CSV_SIGNALS_PATH):
        t = Transformer.from_crs("EPSG:4326", UTM_CRS, always_xy=True)
        cx, cy = t.transform(CENTER[1], CENTER[0])
        signal_coords = load_traffic_signals_csv(
            CSV_SIGNALS_PATH, UTM_CRS, cx, cy, radius=RADIUS
        )
        with open(CSV_SIGNALS_CACHE, "wb") as f:
            pickle.dump(signal_coords, f)
        print(f"  신호등 CSV 파싱: {len(signal_coords)}개")
    else:
        vw_sigs = points_data.get("traffic_signals", [])
        signal_coords = [(x, y, 1) for x, y in vw_sigs]
        print(f"  신호등 Vworld JSON: {len(signal_coords)}개")
    # 신호등 위치 보정 + 도로 방향 계산
    signal_coords = process_signals(signal_coords, roads_gdf, buildings_gdf)
    traffic_signal_meshes = make_traffic_signal_meshes(signal_coords)

    # 횡단보도 ①: CSV 실제 치수 기반 (우선 소스)
    t = Transformer.from_crs("EPSG:4326", UTM_CRS, always_xy=True)
    cx, cy = t.transform(CENTER[1], CENTER[0])
    if os.path.exists(CSV_CROSSWALKS_CACHE):
        with open(CSV_CROSSWALKS_CACHE, "rb") as f:
            crosswalk_data = pickle.load(f)
        print(f"  횡단보도 CSV 캐시: {len(crosswalk_data)}개")
    elif os.path.exists(CSV_CROSSWALKS_PATH):
        crosswalk_data = load_crosswalks_csv(
            CSV_CROSSWALKS_PATH, UTM_CRS, cx, cy, radius=RADIUS
        )
        with open(CSV_CROSSWALKS_CACHE, "wb") as f:
            pickle.dump(crosswalk_data, f)
        print(f"  횡단보도 CSV: {len(crosswalk_data)}개")
    else:
        crosswalk_data = None

    if crosswalk_data:
        crossing_meshes = make_crossing_meshes_from_data(
            crosswalk_data, roads_gdf
        )
        sig_cw = sum(1 for c in crosswalk_data if c["has_signal"])
        no_sig_cw = len(crosswalk_data) - sig_cw
        print(f"  신호 있음: {sig_cw}개, 무신호: {no_sig_cw}개")
    else:
        # fallback: 보행자 신호등 위치
        ped_coords = [(x, y) for x, y, st, *_ in signal_coords if st == 2]
        crossing_meshes = make_crossing_meshes(ped_coords, roads_gdf)

    # 횡단보도 ②: Vworld 노면표시 폴리곤 (실제 형상, 우선 보완)
    crosswalk_gdf = load_as_gdf("lt_c_b3surfacemark")
    if crosswalk_gdf is not None:
        for _, row in crosswalk_gdf.iterrows():
            geom = row.geometry
            if isinstance(geom, Polygon):
                mesh = polygon_to_mesh(geom, height=0.04, base_z=0.02)
                if mesh:
                    crossing_meshes.append(mesh)
        print(f"  횡단보도 Vworld 폴리곤 보완: {len(crosswalk_gdf)}개")

    # 횡단보도 ③: OSM 무신호 횡단보도 (CSV 없는 경우 fallback)
    if not crosswalk_data:
        osm_crossings_gdf = load_osm_gdf("crossings")
        if osm_crossings_gdf is not None:
            osm_pts = [
                (row.geometry.x, row.geometry.y)
                for _, row in osm_crossings_gdf.iterrows()
                if row.geometry is not None
                and row.geometry.geom_type == "Point"
            ]
            crossing_meshes += make_crossing_meshes(osm_pts, roads_gdf)
            print(f"  횡단보도 OSM fallback: {len(osm_pts)}개")

    print(f"  건물: {len(building_meshes)}, 도로: {len(road_meshes)}, "
          f"신호등: {len(traffic_signal_meshes)}, 횡단보도: {len(crossing_meshes)}")

    print("4/4 USD 저장...")
    write_usd(
        USD_OUTPUT, building_meshes, road_meshes,
        generated_meshes, traffic_signal_meshes, crossing_meshes,
        [],
        sidewalk_meshes,
    )
    print("=== Done ===")
    print(f"\nApply textures: python3 apply_textures.py {USD_OUTPUT}")


if __name__ == "__main__":
    main()
