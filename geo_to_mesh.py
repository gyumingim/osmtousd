import numpy as np
import mapbox_earcut as earcut
from shapely.geometry import Polygon, MultiPolygon

# Default building heights (m) by type -- used when height/levels tags missing
_DEFAULT_HEIGHTS = {
    "apartments": 30.0,
    "dormitory": 20.0,
    "hotel": 20.0,
    "office": 18.0,
    "commercial": 12.0,
    "retail": 5.0,
    "university": 15.0,
    "school": 9.0,
    "hospital": 15.0,
    "public": 9.0,
    "government": 9.0,
    "residential": 9.0,
    "house": 6.0,
    "industrial": 8.0,
    "warehouse": 8.0,
    "train_station": 12.0,
    "yes": 10.0,
}

# Road width (m) by highway type
_ROAD_WIDTHS = {
    "motorway": 8.0,
    "trunk": 7.0,
    "primary": 6.0,
    "secondary": 5.0,
    "tertiary": 4.0,
    "unclassified": 3.5,
    "residential": 3.5,
    "living_street": 3.0,
    "service": 3.0,
    "pedestrian": 3.0,
    "track": 3.0,
    "footway": 1.5,
    "cycleway": 1.5,
    "path": 1.5,
    "steps": 1.5,
    "busway": 4.0,
}

# Vworld road_rank → 도로 폭(m)
# 표준(1-6): 고속~기타 / moctlink 코드(101-107): 고속~시군도
_VWORLD_ROAD_WIDTHS = {
    "1": 12.0, "2": 8.0, "3": 7.0, "4": 6.0, "5": 4.0, "6": 3.0,
    "101": 12.0, "103": 8.0, "106": 6.0, "107": 4.0,
}

SIDEWALK_Z = 0.09
ROAD_Z = 0.10
MARKING_Z = 0.15  # 노면선표시 — 도로(0.10m)보다 충분히 위

# kind → (선 폭(m), RGB색상)
_MARKING_STYLES = {
    "501": (0.50, (1.0, 0.9, 0.0)),   # 중앙선 — 노란색
    "503": (0.30, (1.0, 1.0, 1.0)),   # 차선(점선) — 흰색
    "505": (0.30, (1.0, 1.0, 1.0)),   # 차선(실선) — 흰색
    "506": (0.30, (1.0, 1.0, 1.0)),   # 유도선 — 흰색
    "515": (0.50, (1.0, 0.6, 0.0)),   # 버스전용 — 주황
    "525": (0.60, (1.0, 1.0, 1.0)),   # 정지선 — 흰색
    "530": (0.40, (0.4, 0.8, 1.0)),   # 자전거전용 — 하늘색
    "531": (0.30, (0.4, 0.8, 1.0)),   # 자전거횡단 — 하늘색
}


def get_building_height(row) -> float:
    h = row.get("height")
    if h is not None and h == h:
        try:
            v = float(str(h).replace("m", "").strip())
            if v > 0:
                return v
        except ValueError:
            pass

    # OSM: building:levels / Vworld: grnd_flr
    levels = row.get("building:levels") or row.get("grnd_flr")
    if levels is not None and levels == levels:
        try:
            v = float(str(levels).strip())
            if v > 0:
                return v * 3.0
        except ValueError:
            pass

    btype = str(row.get("building", "yes"))
    return _DEFAULT_HEIGHTS.get(btype, 5.0)


def _triangulate(polygon: Polygon):
    """Polygon -> (verts_2d np.float64, tris Nx3)"""
    exterior = np.array(polygon.exterior.coords[:-1], dtype=np.float64)
    holes = [
        np.array(ring.coords[:-1], dtype=np.float64)
        for ring in polygon.interiors
    ]

    all_verts = np.concatenate([exterior] + holes) if holes else exterior

    ends = [len(exterior)]
    for hole in holes:
        ends.append(ends[-1] + len(hole))
    rings = np.array(ends, dtype=np.uint32)

    idx = earcut.triangulate_float64(all_verts[:, :2], rings)
    if len(idx) == 0:
        return all_verts, np.empty((0, 3), dtype=np.uint32)
    return all_verts, idx.reshape(-1, 3)


def polygon_to_mesh(polygon: Polygon, height: float, base_z: float = 0.0):
    """
    Extrude polygon by height starting at base_z.
    Returns (points float32 Nx3, face_counts list[int], face_indices list[int])
    """
    verts_2d, tris = _triangulate(polygon)
    if len(tris) == 0:
        return None

    n = len(verts_2d)
    bottom = np.column_stack(
        [verts_2d[:, 0], verts_2d[:, 1], np.full(n, base_z)]
    )
    top = np.column_stack(
        [verts_2d[:, 0], verts_2d[:, 1], np.full(n, base_z + height)]
    )
    points = np.vstack([bottom, top]).astype(np.float32)

    face_counts = []
    face_indices = []

    # Bottom face (reversed winding so normal points down)
    for tri in tris:
        face_counts.append(3)
        face_indices += [int(tri[0]), int(tri[2]), int(tri[1])]

    # Top face
    for tri in tris:
        face_counts.append(3)
        face_indices += [n + int(tri[0]), n + int(tri[1]), n + int(tri[2])]

    # Side walls -- one quad (2 triangles) per edge
    rings = [len(polygon.exterior.coords) - 1]
    for ring in polygon.interiors:
        rings.append(rings[-1] + len(ring.coords) - 1)

    start = 0
    for ring_idx, end in enumerate(rings):
        rn = end - start
        for k in range(rn):
            i = start + k
            j = start + (k + 1) % rn
            if ring_idx == 0:
                face_counts += [3, 3]
                face_indices += [i, j, n + j]
                face_indices += [i, n + j, n + i]
            else:
                face_counts += [3, 3]
                face_indices += [i, n + i, n + j]
                face_indices += [i, n + j, j]
        start = end

    return points, face_counts, face_indices


def polygon_to_mesh_uv(polygon: Polygon, height: float, base_z: float = 0.0,
                       bay_w: float = 3.0, floor_h: float = 3.0):
    """
    Same as polygon_to_mesh but also returns face-varying UV coordinates.
    UV tiling: u = wall_length / bay_w, v = height / floor_h.
    Returns (points, face_counts, face_indices, uv_coords)
    uv_coords: list[(u,v)], one per face-vertex (faceVarying layout).
    """
    result = polygon_to_mesh(polygon, height, base_z)
    if result is None:
        return None
    points, face_counts, face_indices = result

    verts_2d, tris = _triangulate(polygon)
    v_max = height / floor_h

    # Build UV lookup: vertex_index → UV, per face-vertex (faceVarying)
    # Bottom/Top faces use planar XY projection (u=x/bay_w, v=y/bay_w)
    # Side walls use (edge_position/bay_w, z/floor_h)
    uv_coords = []

    # Bottom face UVs (planar XY)
    for tri in tris:
        for vi in [tri[0], tri[2], tri[1]]:
            x, y = verts_2d[vi]
            uv_coords.append((x / bay_w, y / bay_w))

    # Top face UVs (planar XY)
    for tri in tris:
        for vi in [tri[0], tri[1], tri[2]]:
            x, y = verts_2d[vi]
            uv_coords.append((x / bay_w, y / bay_w))

    # Side wall UVs
    rings = [len(polygon.exterior.coords) - 1]
    for ring in polygon.interiors:
        rings.append(rings[-1] + len(ring.coords) - 1)

    start = 0
    for ring_idx, end in enumerate(rings):
        rn = end - start
        u_accum = 0.0
        for k in range(rn):
            i = start + k
            j = start + (k + 1) % rn
            xi, yi = verts_2d[i]
            xj, yj = verts_2d[j]
            edge_len = float(np.sqrt((xj - xi) ** 2 + (yj - yi) ** 2))
            u0, u1 = u_accum / bay_w, (u_accum + edge_len) / bay_w
            # Triangle 1: [i, j, n+j] → (u0,0), (u1,0), (u1,v_max)
            # Triangle 2: [i, n+j, n+i] → (u0,0), (u1,v_max), (u0,v_max)
            uv_coords += [(u0, 0.0), (u1, 0.0), (u1, v_max)]
            uv_coords += [(u0, 0.0), (u1, v_max), (u0, v_max)]
            u_accum += edge_len
        start = end

    return points, face_counts, face_indices, uv_coords


def building_to_meshes(row):
    """
    GeoDataFrame row -> list of (points, face_counts, face_indices).
    Splits MultiPolygon into individual Polygons.
    """
    height = get_building_height(row)
    geom = row.geometry
    if isinstance(geom, MultiPolygon):
        polys = [g for g in geom.geoms if isinstance(g, Polygon)]
    elif isinstance(geom, Polygon):
        polys = [geom]
    else:
        return []  # skip Point, LineString, GeometryCollection

    results = []
    for poly in polys:
        mesh = polygon_to_mesh(poly, height)
        if mesh is not None:
            results.append(mesh)
    return results


def get_road_width(highway) -> float:
    if isinstance(highway, list):
        highway = highway[0]
    return _ROAD_WIDTHS.get(str(highway), 3.0)


def _poly_to_flat_mesh(poly, z):
    """Polygon → flat mesh tuple at height z. Holes 지원."""
    if not isinstance(poly, Polygon) or poly.is_empty:
        return None
    ext = np.array(poly.exterior.coords[:-1], dtype=np.float64)
    holes = [np.array(r.coords[:-1], dtype=np.float64)
             for r in poly.interiors]
    verts = np.concatenate([ext] + holes) if holes else ext
    ends = np.array(
        [len(ext)] + [len(ext) + sum(len(h) for h in holes[:i+1])
                      for i in range(len(holes))],
        dtype=np.uint32,
    )
    idx = earcut.triangulate_float64(verts[:, :2], ends)
    if len(idx) == 0:
        return None
    tris = idx.reshape(-1, 3)
    n = len(verts)
    pts = np.column_stack(
        [verts[:, 0], verts[:, 1], np.full(n, z)]
    ).astype(np.float32)
    return pts, [3] * len(tris), tris.flatten().tolist()


def _clip_by_buildings(geom, bldg_tree, bldg_geoms):
    """geom에서 인근 건물 폴리곤을 제거해 반환."""
    if bldg_tree is None:
        return geom
    for idx in bldg_tree.query(geom):
        bldg = bldg_geoms[idx]
        if geom.intersects(bldg):
            geom = geom.difference(bldg)
            if geom.is_empty:
                return None
    return geom


def road_to_mesh(row, z=None):
    """Road/footway edge row → flat mesh."""
    if z is None:
        z = ROAD_Z

    rvwd = row.get("rvwd")
    if rvwd is not None:
        try:
            width = float(rvwd)
        except (ValueError, TypeError):
            width = 0
    else:
        width = 0

    if width <= 0:
        rank = row.get("road_rank")
        if rank is not None:
            lanes = row.get("lanes")
            try:
                width = float(lanes) * 3.5 if lanes else 0
            except (ValueError, TypeError):
                width = 0
            if width <= 0:
                width = _VWORLD_ROAD_WIDTHS.get(str(rank), 4.0)
        else:
            width = get_road_width(row.get("highway", "residential"))

    buffered = row.geometry.buffer(width / 2, cap_style=2, join_style=2)
    if buffered.is_empty or not buffered.is_valid:
        return None

    polys = (
        list(buffered.geoms) if hasattr(buffered, 'geoms') else [buffered]
    )
    all_pts, all_fc, all_fi, offset = [], [], [], 0
    for poly in polys:
        result = _poly_to_flat_mesh(poly, z)
        if result is None:
            continue
        pts, fc, fi = result
        all_pts.append(pts)
        all_fc.extend(fc)
        all_fi.extend([i + offset for i in fi])
        offset += len(pts)

    if not all_pts:
        return None
    return np.vstack(all_pts), all_fc, all_fi


def surface_line_to_mesh(row):
    """노면선표시 row → (pts, fc, fi, color) (kind별 폭·색상, MARKING_Z)."""
    kind = str(row.get("kind", ""))
    width, color = _MARKING_STYLES.get(kind, (0.10, (1.0, 1.0, 1.0)))
    geom = row.geometry
    buffered = geom.buffer(width / 2, cap_style=2, join_style=2)
    if buffered.is_empty or not buffered.is_valid:
        return None
    polys = list(buffered.geoms) if hasattr(buffered, "geoms") else [buffered]
    all_pts, all_fc, all_fi, offset = [], [], [], 0
    for poly in polys:
        result = _poly_to_flat_mesh(poly, MARKING_Z)
        if result is None:
            continue
        pts, fc, fi = result
        all_pts.append(pts)
        all_fc.extend(fc)
        all_fi.extend([i + offset for i in fi])
        offset += len(pts)
    if not all_pts:
        return None
    return np.vstack(all_pts), all_fc, all_fi, color


def _line_to_marking_mesh(geom, width, color):
    """LineString → flat marking mesh tuple."""
    buffered = geom.buffer(width / 2, cap_style=2, join_style=2)
    if buffered.is_empty or not buffered.is_valid:
        return None
    polys = list(buffered.geoms) if hasattr(buffered, 'geoms') else [buffered]
    all_pts, all_fc, all_fi, offset = [], [], [], 0
    for poly in polys:
        result = _poly_to_flat_mesh(poly, MARKING_Z)
        if result is None:
            continue
        pts, fc, fi = result
        all_pts.append(pts)
        all_fc.extend(fc)
        all_fi.extend([i + offset for i in fi])
        offset += len(pts)
    if not all_pts:
        return None
    return np.vstack(all_pts), all_fc, all_fi, color


def build_road_markings(gdf):
    """n3a0020000 GDF → 중앙선(노란) + 내부 차선(흰) 메시 리스트.

    dvyn=CSU002(왕복): 중심선 = 중앙선(황색)
                       rdln > 2 이면 차선폭 간격으로 흰 차선 추가
    dvyn=CSU001(일방): 스킵 (중앙분리대 없음)
    """
    meshes = []
    for _, row in gdf.iterrows():
        dvyn = str(row.get('dvyn') or '')
        if dvyn != 'CSU002':
            continue

        geom = row.geometry
        rdln = int(row.get('rdln') or 1)
        rvwd = float(row.get('rvwd') or 0)

        # 1차로 왕복(골목 등)은 중앙선 없음
        if rdln < 2:
            continue

        # 중앙선 (황색)
        m = _line_to_marking_mesh(geom, 0.30, (1.0, 0.9, 0.0))
        if m:
            meshes.append(m)

        # 내부 차선 (흰색) — 편도 2차로 이상일 때 양쪽에 생성
        # rdln = 총 차선수, 편도 차선 = rdln // 2
        # 내부 구분선 개수 = 편도차선 - 1
        lanes_per_dir = rdln // 2
        if lanes_per_dir >= 2 and rvwd > 0:
            lane_w = rvwd / rdln
            lines = (list(geom.geoms)
                     if hasattr(geom, 'geoms') else [geom])
            for k in range(1, lanes_per_dir):
                dist = lane_w * k
                for side in ('left', 'right'):
                    for line in lines:
                        try:
                            og = line.parallel_offset(dist, side)
                            if og is None or og.is_empty:
                                continue
                            m = _line_to_marking_mesh(
                                og, 0.20, (1.0, 1.0, 1.0)
                            )
                            if m:
                                meshes.append(m)
                        except Exception:
                            pass
    return meshes
