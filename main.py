import os
import pickle
import numpy as np
from shapely.geometry import Polygon
from shapely.strtree import STRtree
from shapely.geometry import Point
from pyproj import Transformer

from osm_fetch import CENTER, RADIUS
from vworld_loader import load_as_gdf, load_osm_gdf, load_points_data, UTM_CRS
from geo_to_mesh import building_to_meshes, road_to_mesh, polygon_to_mesh
from building_generator import generate_missing_buildings
from props_generator import make_traffic_signal_meshes, make_crossing_meshes
from csv_loader import load_traffic_signals_csv
from usd_writer import write_usd

SNAP_THRESHOLD = 80  # 교차로까지 최대 스냅 거리(m)


def snap_to_intersections(signal_coords, node_gdf):
    """
    각 신호등을 가장 가까운 교차로 노드로 스냅.
    SNAP_THRESHOLD(m) 초과 시 원래 위치 유지.
    """
    if node_gdf is None or len(node_gdf) == 0:
        return signal_coords

    # 교차로 타입만 사용
    inter = node_gdf[node_gdf.get("nd_type_h", "").eq("교차로시·종점")
                     if "nd_type_h" in node_gdf.columns
                     else node_gdf.index >= 0]
    if len(inter) == 0:
        inter = node_gdf

    node_pts = [Point(row.geometry.x, row.geometry.y)
                for _, row in inter.iterrows()
                if row.geometry.geom_type == "Point"]
    if not node_pts:
        return signal_coords

    tree = STRtree(node_pts)
    node_xy = np.array([(p.x, p.y) for p in node_pts])

    snapped, moved = [], 0
    for x, y, sig_type in signal_coords:
        pt = Point(x, y)
        idx = tree.nearest(pt)
        nx, ny = node_xy[idx]
        dist = ((nx - x) ** 2 + (ny - y) ** 2) ** 0.5
        if dist <= SNAP_THRESHOLD:
            snapped.append((nx, ny, sig_type))
            moved += 1
        else:
            snapped.append((x, y, sig_type))

    print(f"  신호등 스냅: {moved}/{len(signal_coords)}개 교차로로 이동")
    return snapped

USD_OUTPUT = "gumi.usda"
CSV_SIGNALS_PATH = "경상북도_구미시_신호등_20260331.csv"
CSV_SIGNALS_CACHE = "csv_signals_cache.pkl"


def main():
    print("=== Vworld -> USD conversion ===")

    print("1/4 Vworld 데이터 로드...")
    buildings_gdf = load_as_gdf("lt_c_bldginfo")
    roads_gdf = load_as_gdf("lt_l_moctlink")
    node_gdf = load_as_gdf("lt_p_moctnode")
    if buildings_gdf is None or roads_gdf is None:
        print("  [오류] vworld_data/ 파일 없음. 먼저 실행: python3 vworld_fetcher.py")
        return
    print(f"  건물: {len(buildings_gdf)}, 도로: {len(roads_gdf)}, "
          f"교차로 노드: {len(node_gdf) if node_gdf is not None else 0}")

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

    road_meshes = []
    for _, row in roads_gdf.iterrows():
        mesh = road_to_mesh(row)
        if mesh is not None:
            road_meshes.append(mesh)

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
    signal_coords = snap_to_intersections(signal_coords, node_gdf)
    traffic_signal_meshes = make_traffic_signal_meshes(signal_coords)

    # 횡단보도: 보행자 신호등 위치 + Vworld 노면표시 폴리곤
    ped_coords = [(x, y) for x, y, t in signal_coords if t == 2]
    crossing_meshes = make_crossing_meshes(ped_coords, roads_gdf)

    crosswalk_gdf = load_as_gdf("lt_c_b3surfacemark")
    if crosswalk_gdf is not None:
        for _, row in crosswalk_gdf.iterrows():
            geom = row.geometry
            if isinstance(geom, Polygon):
                mesh = polygon_to_mesh(geom, height=0.04, base_z=0.02)
                if mesh:
                    crossing_meshes.append(mesh)
        print(f"  횡단보도 Vworld: {len(crosswalk_gdf)}개 폴리곤")

    print(f"  건물: {len(building_meshes)}, 도로: {len(road_meshes)}, "
          f"신호등: {len(traffic_signal_meshes)}, 횡단보도: {len(crossing_meshes)}")

    print("4/4 USD 저장...")
    write_usd(
        USD_OUTPUT, building_meshes, road_meshes,
        generated_meshes, traffic_signal_meshes, crossing_meshes,
        [],  # vworld_meshes 별도 레이어 미사용 (건물이 이미 Vworld)
    )
    print("=== Done ===")
    print(f"\nApply textures: python3 apply_textures.py {USD_OUTPUT}")


if __name__ == "__main__":
    main()
