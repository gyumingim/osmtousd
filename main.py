import os
import pickle
from shapely.geometry import Polygon, MultiPolygon
from pyproj import Transformer

from osm_fetch import CENTER, RADIUS, fetch_buildings, fetch_roads, fetch_points
from geo_to_mesh import building_to_meshes, road_to_mesh, polygon_to_mesh
from building_generator import generate_missing_buildings
from props_generator import make_traffic_signal_meshes, make_crossing_meshes
from vworld_fetch import (
    fetch_vworld_buildings, to_local_coords, get_vworld_height,
    fetch_vworld_traffic_signals, fetch_vworld_crossings,
)
from usd_writer import write_usd

USD_OUTPUT = "busan_univ.usda"
POINTS_CACHE = "points_cache.pkl"
VWORLD_CACHE = "vworld_cache.pkl"

VWORLD_API_KEY = os.environ.get("VWORLD_KEY", "")


def main():
    print("=== OSM -> USD conversion ===")

    print("1/4 Downloading OSM data...")
    buildings_gdf = fetch_buildings()
    roads_gdf = fetch_roads()
    print(f"  buildings: {len(buildings_gdf)}, road edges: {len(roads_gdf)}")

    print("2/4 Loading point features...")
    if os.path.exists(POINTS_CACHE):
        with open(POINTS_CACHE, "rb") as f:
            points_data = pickle.load(f)
        print(f"  {len(points_data)} categories from cache")
    else:
        points_data = fetch_points(utm_crs=buildings_gdf.crs)
        with open(POINTS_CACHE, "wb") as f:
            pickle.dump(points_data, f)
        print(f"  {len(points_data)} categories saved -> {POINTS_CACHE}")

    print("3/4 Generating meshes...")
    building_meshes = []
    for _, row in buildings_gdf.iterrows():
        building_meshes.extend(building_to_meshes(row))

    vworld_meshes = []
    vw_gdf = None
    if os.path.exists(VWORLD_CACHE):
        print("  Loading Vworld buildings from cache...")
        with open(VWORLD_CACHE, "rb") as f:
            vw_gdf = pickle.load(f)
    elif VWORLD_API_KEY:
        print("  Fetching Vworld buildings...")
        vw_gdf = fetch_vworld_buildings(CENTER, RADIUS, VWORLD_API_KEY)
        if vw_gdf is not None:
            with open(VWORLD_CACHE, "wb") as f:
                pickle.dump(vw_gdf, f)
            print(f"  Saved -> {VWORLD_CACHE}")
    else:
        print("  [skip] no cache and VWORLD_KEY not set")
    if vw_gdf is not None:
            t = Transformer.from_crs(
                "EPSG:4326", buildings_gdf.crs, always_xy=True
            )
            cx, cy = t.transform(CENTER[1], CENTER[0])
            vw_local = to_local_coords(vw_gdf, buildings_gdf.crs, cx, cy)
            for _, row in vw_local.iterrows():
                geom = row.geometry
                height = get_vworld_height(row)
                polys = (
                    list(geom.geoms) if isinstance(geom, MultiPolygon)
                    else [geom]
                )
                for poly in polys:
                    if isinstance(poly, Polygon):
                        mesh = polygon_to_mesh(poly, height)
                        if mesh:
                            vworld_meshes.append(mesh)
            print(f"  Vworld: {len(vworld_meshes)} building meshes")
    else:
        print("  [skip] VWORLD_KEY not set -- run: export VWORLD_KEY=your_key")

    print("  Generating buildings for amenity points without polygons...")
    generated_meshes = generate_missing_buildings(
        buildings_gdf, roads_gdf, points_data
    )

    road_meshes = []
    for _, row in roads_gdf.iterrows():
        mesh = road_to_mesh(row)
        if mesh is not None:
            road_meshes.append(mesh)

    # Traffic signals: OSM + Vworld
    signal_coords = list(points_data.get("traffic_signals", []))
    if VWORLD_API_KEY:
        vw_signals = fetch_vworld_traffic_signals(CENTER, RADIUS, VWORLD_API_KEY)
        signal_coords += vw_signals
    traffic_signal_meshes = make_traffic_signal_meshes(signal_coords)

    # Crossings: OSM (synthetic stripes) + Vworld (actual polygons)
    crossing_coords = points_data.get("crossing", [])
    crossing_meshes = make_crossing_meshes(crossing_coords, roads_gdf)
    if VWORLD_API_KEY:
        vw_cross_polys = fetch_vworld_crossings(CENTER, RADIUS, VWORLD_API_KEY)
        for poly in vw_cross_polys:
            mesh = polygon_to_mesh(poly, height=0.04, base_z=0.02)
            if mesh:
                crossing_meshes.append(mesh)

    print(f"  OSM buildings: {len(building_meshes)}, "
          f"Vworld: {len(vworld_meshes)}, roads: {len(road_meshes)}")

    print("4/4 Writing USD...")
    write_usd(
        USD_OUTPUT, building_meshes, road_meshes,
        generated_meshes, traffic_signal_meshes, crossing_meshes,
        vworld_meshes,
    )
    print("=== Done ===")
    print(f"\nApply textures: python3 apply_textures.py {USD_OUTPUT}")


if __name__ == "__main__":
    main()
