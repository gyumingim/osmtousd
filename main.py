from pxr import Usd

from vworld_loader import load_as_gdf, load_osm_gdf, load_points_data
from geo_to_mesh import (
    building_to_meshes, road_to_mesh,
    surface_line_to_mesh, build_road_markings,
    build_intersection_elements,
)
from building_generator import generate_missing_buildings
from usd_writer import write_usd
from apply_textures import apply_textures
from isaac_setup import setup_physics, setup_semantics, setup_road_graph


USD_OUTPUT = "gumi.usda"


def main():
    print("=== Vworld -> USD conversion ===")

    print("1/4 Vworld 데이터 로드...")
    buildings_gdf = load_as_gdf("lt_c_bldginfo")
    roads_gdf = load_as_gdf("lt_l_n3a0020000")
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

    road_meshes = []
    for _, row in roads_gdf.iterrows():
        mesh = road_to_mesh(row)
        if mesh is not None:
            road_meshes.append(mesh)

    sidewalk_meshes = []

    marking_gdf = load_as_gdf("lt_l_b2surfacelinemark")
    marking_meshes = []
    if marking_gdf is not None:
        for _, row in marking_gdf.iterrows():
            mesh = surface_line_to_mesh(row)
            if mesh is not None:
                marking_meshes.append(mesh)

    nodes_gdf = load_as_gdf("lt_p_moctnode")
    marking_meshes += build_road_markings(roads_gdf, nodes_gdf)
    print(f"  도로: {len(road_meshes)}, 노면선: {len(marking_meshes)}")

    intersection_meshes = []
    # intersection_meshes = build_intersection_elements(roads_gdf)

    print(f"  건물: {len(building_meshes)}, 도로: {len(road_meshes)}")

    print("4/4 USD 저장...")
    write_usd(
        USD_OUTPUT, building_meshes, road_meshes,
        generated_meshes, [], [],
        [],
        sidewalk_meshes,
        marking_meshes,
        intersection_meshes,
    )

    print("\n=== 텍스처 적용 ===")
    apply_textures(USD_OUTPUT)

    print("\n=== Isaac Sim 설정 ===")
    stage = Usd.Stage.Open(USD_OUTPUT)
    setup_physics(stage)
    setup_semantics(stage)
    setup_road_graph(stage)
    stage.Save()
    print(f"저장 완료: {USD_OUTPUT}")

    print("\n=== 완료 ===")
    print(f"결과물: {USD_OUTPUT}")


if __name__ == "__main__":
    main()
