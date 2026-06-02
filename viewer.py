import os
import pickle
import numpy as np
import polyscope as ps
import polyscope.imgui as psim
from PIL import Image
from pxr import Usd, UsdGeom, UsdShade
from pyproj import Transformer

import sys

CACHE_FILE = "points_cache.pkl"
USD_PATH = sys.argv[1] if len(sys.argv) > 1 else "gumi.usda"

# Color per point feature label (RGB 0-1)
POINT_COLORS = {
    "traffic_signals":  (1.0, 0.2, 0.2),
    "crossing":         (1.0, 0.9, 0.2),
    "bus_stop":         (0.2, 0.5, 1.0),
    "platform":         (0.3, 0.6, 1.0),
    "stop_position":    (0.4, 0.7, 1.0),
    "station":          (0.0, 0.3, 0.9),
    "restaurant":       (1.0, 0.5, 0.1),
    "cafe":             (0.7, 0.4, 0.1),
    "bar":              (0.8, 0.2, 0.5),
    "pub":              (0.7, 0.1, 0.4),
    "fast_food":        (1.0, 0.6, 0.0),
    "ice_cream":        (0.9, 0.7, 0.9),
    "hospital":         (0.2, 0.8, 0.4),
    "dentist":          (0.4, 0.9, 0.5),
    "bank":             (0.2, 0.7, 0.3),
    "atm":              (0.3, 0.8, 0.4),
    "townhall":         (0.5, 0.5, 0.9),
    "post_office":      (0.6, 0.4, 0.8),
    "police":           (0.2, 0.2, 0.8),
    "kindergarten":     (0.9, 0.6, 0.8),
    "library":          (0.6, 0.6, 0.9),
    "parking_space":    (0.5, 0.5, 0.5),
    "fuel":             (0.8, 0.7, 0.1),
    "childcare":        (1.0, 0.7, 0.8),
    "public_bath":      (0.5, 0.8, 0.9),
    "cinema":           (0.7, 0.3, 0.7),
    "arts_centre":      (0.8, 0.4, 0.8),
    "marketplace":      (0.9, 0.6, 0.2),
    "place_of_worship": (0.9, 0.9, 0.6),
    "supermarket":      (0.5, 0.9, 0.5),
    "convenience":      (0.6, 1.0, 0.6),
    "bakery":           (1.0, 0.8, 0.5),
    "books":            (0.6, 0.5, 0.3),
    "laundry":          (0.6, 0.8, 1.0),
    "hairdresser":      (1.0, 0.5, 0.7),
    "florist":          (0.9, 0.3, 0.5),
    "clothes":          (0.8, 0.5, 0.9),
    "beauty":           (1.0, 0.6, 0.8),
    "motel":            (0.4, 0.6, 0.5),
    "hostel":           (0.3, 0.5, 0.4),
    "museum":           (0.5, 0.4, 0.7),
    "viewpoint":        (0.2, 0.8, 0.9),
    "sauna":            (0.8, 0.5, 0.3),
    "gate":             (0.6, 0.6, 0.6),
    "lift_gate":        (0.5, 0.5, 0.5),
}


_tex_cache: dict = {}


def _sample_texture(tex_path: str, uvs: np.ndarray) -> np.ndarray:
    """Sample texture at Nx2 UV array. Returns Nx3 float32 RGB [0,1]."""
    if tex_path not in _tex_cache:
        _tex_cache[tex_path] = (
            np.array(Image.open(tex_path).convert("RGB")) / 255.0
        ).astype(np.float32)
    img = _tex_cache[tex_path]
    h, w = img.shape[:2]
    u = uvs[:, 0] % 1.0
    v = uvs[:, 1] % 1.0
    px = (u * w).astype(int) % w
    py = ((1.0 - v) * h).astype(int) % h
    return img[py, px]


def _get_tex_path(child_prim) -> str | None:
    """Read texture file path from USD material binding."""
    try:
        mat = UsdShade.MaterialBindingAPI(child_prim).GetDirectBinding()
        mat_prim = mat.GetMaterial().GetPrim()
        diffuse = mat_prim.GetChild("Diffuse")
        val = diffuse.GetAttribute("inputs:file").Get()
        return str(val.resolvedPath) if val else None
    except Exception:
        return None


def load_group(stage, group_path: str):
    """Merge all meshes under a USD group prim into one array."""
    group_prim = stage.GetPrimAtPath(group_path)
    if not group_prim.IsValid():
        return None, None, None

    all_verts, all_faces, all_colors = [], [], []
    offset = 0
    has_colors = False

    for child in group_prim.GetChildren():
        mesh = UsdGeom.Mesh(child)
        pts = mesh.GetPointsAttr().Get()
        counts = mesh.GetFaceVertexCountsAttr().Get()
        indices = mesh.GetFaceVertexIndicesAttr().Get()
        if pts is None or counts is None or indices is None:
            continue
        verts = np.array(pts, dtype=np.float64)
        cnts = np.array(counts, dtype=np.int32)
        idx = np.array(indices, dtype=np.int32)
        if not np.all(cnts == 3):
            continue
        all_verts.append(verts)
        all_faces.append(idx.reshape(-1, 3) + offset)
        offset += len(verts)

        # Per-face color: texture 우선, 없으면 displayColor
        tex_path = _get_tex_path(child)
        pv_api = UsdGeom.PrimvarsAPI(mesh)
        uv_pv = pv_api.GetPrimvar("st")
        if tex_path and os.path.exists(tex_path) and uv_pv:
            uv_raw = np.array(list(uv_pv.Get()), dtype=np.float32)
            n_faces = len(cnts)
            uv_per_face = uv_raw.reshape(n_faces, 3, 2).mean(axis=1)
            face_colors = _sample_texture(tex_path, uv_per_face)
            all_colors.append(face_colors)
            has_colors = True
        else:
            dc = mesh.GetDisplayColorAttr().Get()
            if dc is not None and len(dc) > 0:
                c = np.array(dc[0], dtype=np.float32)
                n_faces = len(cnts)
                all_colors.append(np.tile(c, (n_faces, 1)))
                has_colors = True
            else:
                all_colors.append(None)

    if not all_verts:
        return None, None, None

    verts_out = np.vstack(all_verts)
    faces_out = np.vstack(all_faces)
    if has_colors:
        merged = []
        for fc in all_colors:
            if fc is None:
                # Fallback gray for meshes without texture
                n = len(all_faces[all_colors.index(fc)])
                merged.append(np.full((n, 3), 0.6, dtype=np.float32))
            else:
                merged.append(fc)
        colors_out = np.vstack(merged)
    else:
        colors_out = None

    return verts_out, faces_out, colors_out


def main():
    from vworld_loader import UTM_CRS, _get_origin
    _cx, _cy = _get_origin()
    _t_inv = Transformer.from_crs(UTM_CRS, "EPSG:4326", always_xy=True)

    print(f"Loading USD: {USD_PATH}")
    stage = Usd.Stage.Open(USD_PATH)
    buildings_v, buildings_f, buildings_c = load_group(
        stage, "/World/Buildings"
    )
    roads_v, roads_f, _ = load_group(stage, "/World/Roads")
    generated_v, generated_f, generated_c = load_group(
        stage, "/World/GeneratedBuildings"
    )
    signals_v, signals_f, _ = load_group(stage, "/World/TrafficSignals")
    crossings_v, crossings_f, _ = load_group(stage, "/World/Crossings")
    sidewalks_v, sidewalks_f, _ = load_group(stage, "/World/Sidewalks")
    vworld_v, vworld_f, vworld_c = load_group(
        stage, "/World/VworldBuildings"
    )
    markings_v, markings_f, markings_c = load_group(
        stage, "/World/RoadMarkings"
    )
    if buildings_f is not None:
        print(f"  buildings:           {len(buildings_f):,} triangles")
    if roads_f is not None:
        print(f"  roads:               {len(roads_f):,} triangles")
    if generated_f is not None:
        print(f"  generated buildings: {len(generated_f):,} triangles")

    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "rb") as f:
            points_data = pickle.load(f)
        # Migrate old Korean keys to English
        _KO_TO_EN = {
            "신호등": "traffic_signals", "횡단보도": "crossing", "버스정류장": "bus_stop",
            "승강장": "platform", "정차위치": "stop_position", "역": "station",
            "음식점": "restaurant", "카페": "cafe", "술집": "bar", "퍼브": "pub",
            "패스트푸드": "fast_food", "아이스크림": "ice_cream", "병원": "hospital",
            "치과": "dentist", "은행": "bank", "ATM": "atm", "시청/구청": "townhall",
            "우체국": "post_office", "경찰서": "police", "유치원": "kindergarten",
            "도서관": "library", "주차공간": "parking_space", "주유소": "fuel",
            "어린이집": "childcare", "목욕탕": "public_bath", "영화관": "cinema",
            "예술센터": "arts_centre", "시장": "marketplace",
            "종교시설": "place_of_worship",
            "슈퍼마켓": "supermarket", "편의점": "convenience", "제과점": "bakery",
            "서점": "books", "세탁소": "laundry", "미용실": "hairdresser",
            "꽃집": "florist", "의류": "clothes", "뷰티": "beauty", "모텔": "motel",
            "게스트하우스": "hostel", "박물관": "museum", "전망대": "viewpoint",
            "사우나": "sauna", "게이트": "gate", "차단기": "lift_gate",
        }
        if any(k in _KO_TO_EN for k in points_data):
            points_data = {
                _KO_TO_EN.get(k, k): v for k, v in points_data.items()
            }
            with open(CACHE_FILE, "wb") as f:
                pickle.dump(points_data, f)
            print("  cache migrated to English keys")
        print(f"  point features: {len(points_data)} categories (from cache)")
    else:
        print("  point features: none -- run 'python3 main.py' first")
        points_data = {}

    ps.init()
    ps.set_up_dir("z_up")
    ps.set_ground_plane_mode("shadow_only")
    ps.set_background_color((0.15, 0.15, 0.18))

    def _register_buildings(name, verts, faces, colors, fallback_color):
        if verts is None:
            return
        mesh = ps.register_surface_mesh(name, verts, faces, smooth_shade=False)
        if colors is not None:
            mesh.add_color_quantity("texture", colors,
                                    defined_on="faces", enabled=True)
        else:
            mesh.set_color(fallback_color)

    _register_buildings("buildings (OSM)", buildings_v, buildings_f,
                        buildings_c, (0.95, 0.85, 0.20))
    _register_buildings("buildings (Vworld)", vworld_v, vworld_f,
                        vworld_c, (0.85, 0.20, 0.20))
    _register_buildings("generated buildings", generated_v, generated_f,
                        generated_c, (0.50, 0.75, 0.90))

    if roads_v is not None:
        rd = ps.register_surface_mesh(
            "roads", roads_v, roads_f,
            color=(0.35, 0.35, 0.40),
            smooth_shade=False,
        )
        rd.set_edge_width(0.0)

    if signals_v is not None:
        ps.register_surface_mesh(
            "traffic signals", signals_v, signals_f,
            color=(0.15, 0.15, 0.15),
            smooth_shade=False,
        )

    if crossings_v is not None:
        cw = ps.register_surface_mesh(
            "crossings", crossings_v, crossings_f,
            color=(0.95, 0.95, 0.95),
            smooth_shade=False,
        )
        cw.set_edge_width(0.0)

    if sidewalks_v is not None:
        sw_mesh = ps.register_surface_mesh(
            "sidewalks", sidewalks_v, sidewalks_f,
            color=(0.75, 0.73, 0.70),
            smooth_shade=False,
        )
        sw_mesh.set_edge_width(0.0)

    if markings_v is not None:
        m_mesh = ps.register_surface_mesh(
            "road markings", markings_v, markings_f,
            smooth_shade=False,
        )
        m_mesh.set_edge_width(0.0)
        if markings_c is not None:
            m_mesh.add_color_quantity(
                "kind_color", markings_c, defined_on="faces", enabled=True
            )

    # 교차로 노드 포인트
    try:
        from vworld_loader import load_as_gdf
        nodes_gdf = load_as_gdf("lt_p_moctnode")
        if nodes_gdf is not None:
            inter = nodes_gdf[nodes_gdf.get('nd_type_h', '') == '교차로시·종점'] \
                if 'nd_type_h' in nodes_gdf.columns else nodes_gdf
            pts = np.array([[row.geometry.x, row.geometry.y, 2.0]
                            for _, row in inter.iterrows()
                            if row.geometry is not None])
            if len(pts) > 0:
                nc = ps.register_point_cloud(
                    "intersections", pts, color=(0.0, 0.0, 0.0)
                )
                nc.set_radius(2.0, relative=False)
                print(f"  교차로 노드: {len(pts)}개")
    except Exception as e:
        print(f"  교차로 노드 로드 실패: {e}")

    # Register each point feature as a separate toggleable layer
    for label, coords in points_data.items():
        pts = np.array([[x, y, 1.5] for x, y in coords])
        color = POINT_COLORS.get(label, (1.0, 1.0, 1.0))
        pc = ps.register_point_cloud(label, pts, color=color)
        pc.set_radius(8.0, relative=False)

    _coord_text = ["클릭해서 위치 확인"]

    def user_callback():
        psim.SetNextWindowPos([10, 10], 1)  # 1 = ImGuiCond_Once
        psim.Begin("좌표", True)
        psim.Text(_coord_text[0])
        psim.End()

        if ps.have_selection():
            result = ps.get_selection()
            if result.is_hit:
                lx, ly = result.position[0], result.position[1]
                utm_x, utm_y = lx + _cx, ly + _cy
                lon, lat = _t_inv.transform(utm_x, utm_y)
                _coord_text[0] = f"lat: {lat:.6f}\nlon: {lon:.6f}"

    ps.set_user_callback(user_callback)

    print("\nControls:")
    print("  left drag  : rotate")
    print("  right drag : pan")
    print("  scroll     : zoom")
    print("  left panel : toggle layers")
    ps.show()


if __name__ == "__main__":
    main()
