import math
import numpy as np
import mapbox_earcut as earcut
from shapely.geometry import Polygon, MultiPolygon, LineString, Point
from shapely.strtree import STRtree
from shapely.ops import substring

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


def _dashed_segments(geom, dash=2.0, gap=2.0):
    """LineString(또는 Multi) → 점선 구간 LineString 리스트."""
    from shapely.geometry import LineString as SLS
    lines = list(geom.geoms) if hasattr(geom, 'geoms') else [geom]
    result = []
    for line in lines:
        total = line.length
        pos, drawing = 0.0, True
        while pos < total:
            end = min(pos + (dash if drawing else gap), total)
            if drawing and end - pos > 0.1:
                n = max(2, int((end - pos) / 0.3) + 1)
                pts = [line.interpolate(t)
                       for t in np.linspace(pos, end, n)]
                result.append(SLS([(p.x, p.y) for p in pts]))
            pos, drawing = end, not drawing
    return result


def surface_line_to_mesh(row):
    """노면선표시 row → (pts, fc, fi, color) (kind별 폭·색상, MARKING_Z)."""
    kind = str(row.get("kind", ""))
    width, color = _MARKING_STYLES.get(kind, (0.10, (1.0, 1.0, 1.0)))
    geom = row.geometry

    # 유도선(506)은 점선 처리
    if kind == '506':
        segs = _dashed_segments(geom, dash=1.5, gap=1.5)
        if not segs:
            return None
        all_pts, all_fc, all_fi, offset = [], [], [], 0
        for seg in segs:
            buf = seg.buffer(width / 2, cap_style=2, join_style=2)
            if buf.is_empty or not buf.is_valid:
                continue
            result = _poly_to_flat_mesh(buf, MARKING_Z)
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


def _crossing_angle(dx1, dy1, dx2, dy2):
    """두 방향벡터 사이의 교차각 (0~90도). 평행이면 0, 수직이면 90."""
    l1 = math.sqrt(dx1**2 + dy1**2)
    l2 = math.sqrt(dx2**2 + dy2**2)
    if l1 < 1e-6 or l2 < 1e-6:
        return 90.0
    cos_a = (dx1*dx2 + dy1*dy2) / (l1 * l2)
    cos_a = max(-1.0, min(1.0, cos_a))
    angle = math.degrees(math.acos(cos_a))
    return min(angle, 180.0 - angle)


def _road_dir_at(road_geom, pt):
    """road_geom에서 pt에 가장 가까운 세그먼트의 방향 반환."""
    lines = (list(road_geom.geoms)
             if hasattr(road_geom, 'geoms') else [road_geom])
    best_d, best_dx, best_dy = float('inf'), 0.0, 0.0
    for line in lines:
        coords = list(line.coords)
        for i in range(len(coords) - 1):
            seg = LineString([coords[i], coords[i + 1]])
            d = seg.distance(pt)
            if d < best_d:
                best_d = d
                best_dx = coords[i+1][0] - coords[i][0]
                best_dy = coords[i+1][1] - coords[i][1]
    return best_dx, best_dy


def _stop_line_mesh(pt_coords, dx, dy, rvwd):
    """교차로 진입 직전 정지선 메시 생성."""
    length = math.sqrt(dx * dx + dy * dy)
    if length < 0.01:
        return None
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    half = rvwd / 2
    line = LineString([
        (pt_coords[0] + half * px, pt_coords[1] + half * py),
        (pt_coords[0] - half * px, pt_coords[1] - half * py),
    ])
    return _line_to_marking_mesh(line, 0.50, (1.0, 1.0, 1.0))


def build_road_markings(gdf, nodes_gdf=None):
    """n3a0020000 GDF → 중앙선(노란) + 내부 차선(흰) + 정지선(흰) 메시 리스트.

    교차점에서 인접 도로 rvwd/2 만큼 끝을 잘라내고 정지선 생성.
    nodes_gdf: 뷰어 시각화용 (클리핑 미사용)
    """
    rows_list = list(gdf.iterrows())
    road_geoms = [row.geometry for _, row in rows_list]
    road_rvwd_list = [float(row.get('rvwd') or 0) for _, row in rows_list]
    road_tree = STRtree(road_geoms)

    meshes = []
    seen_stops = set()  # (ix, iy) 2m 격자 — 정지선 중복 방지

    for row_i, (_, row) in enumerate(rows_list):
        dvyn = str(row.get('dvyn') or '')
        if dvyn != 'CSU002':
            continue

        geom = row.geometry
        rdln = int(row.get('rdln') or 1)
        rvwd = float(row.get('rvwd') or 0)

        if rdln < 2:
            continue

        src_lines = list(geom.geoms) if hasattr(geom, 'geoms') else [geom]
        clipped_lines = []

        for line in src_lines:
            coords = list(line.coords)
            if len(coords) < 2:
                continue
            total = line.length
            start_cut = end_cut = 0.0

            cur_dx_s = coords[1][0] - coords[0][0]
            cur_dy_s = coords[1][1] - coords[0][1]
            cur_dx_e = coords[-1][0] - coords[-2][0]
            cur_dy_e = coords[-1][1] - coords[-2][1]
            start_pt = Point(coords[0])
            end_pt = Point(coords[-1])

            for ti in road_tree.query(start_pt.buffer(20)):
                if ti == row_i:
                    continue
                if road_geoms[ti].distance(start_pt) < 5.0:
                    odx, ody = _road_dir_at(road_geoms[ti], start_pt)
                    if _crossing_angle(cur_dx_s, cur_dy_s, odx, ody) < 20:
                        continue  # 같은 방향 연속 세그먼트
                    w = road_rvwd_list[ti]
                    if w / 2 > start_cut:
                        start_cut = w / 2

            for ti in road_tree.query(end_pt.buffer(20)):
                if ti == row_i:
                    continue
                if road_geoms[ti].distance(end_pt) < 5.0:
                    odx, ody = _road_dir_at(road_geoms[ti], end_pt)
                    if _crossing_angle(cur_dx_e, cur_dy_e, odx, ody) < 20:
                        continue  # 같은 방향 연속 세그먼트
                    w = road_rvwd_list[ti]
                    if w / 2 > end_cut:
                        end_cut = w / 2

            new_end = total - end_cut
            if start_cut >= new_end:
                continue

            new_line = substring(line, start_cut, new_end)
            if new_line is None or new_line.is_empty:
                continue
            clipped_lines.append(new_line)

            if start_cut > 0 and rvwd > 0:
                sp = line.interpolate(start_cut)
                key = (round(sp.x / 2), round(sp.y / 2))
                if key not in seen_stops:
                    seen_stops.add(key)
                    dx = coords[1][0] - coords[0][0]
                    dy = coords[1][1] - coords[0][1]
                    m = _stop_line_mesh((sp.x, sp.y), dx, dy, rvwd)
                    if m:
                        meshes.append(m)

            if end_cut > 0 and rvwd > 0:
                ep = line.interpolate(new_end)
                key = (round(ep.x / 2), round(ep.y / 2))
                if key not in seen_stops:
                    seen_stops.add(key)
                    dx = coords[-1][0] - coords[-2][0]
                    dy = coords[-1][1] - coords[-2][1]
                    m = _stop_line_mesh((ep.x, ep.y), dx, dy, rvwd)
                    if m:
                        meshes.append(m)

        if not clipped_lines:
            continue

        if len(clipped_lines) == 1:
            clipped = clipped_lines[0]
        else:
            from shapely.geometry import MultiLineString
            clipped = MultiLineString(clipped_lines)

        m = _line_to_marking_mesh(clipped, 0.30, (1.0, 0.9, 0.0))
        if m:
            meshes.append(m)

        lanes_per_dir = rdln // 2
        if lanes_per_dir >= 2 and rvwd > 0:
            lane_w = rvwd / rdln
            all_lines = (list(clipped.geoms)
                         if hasattr(clipped, 'geoms') else [clipped])
            for k in range(1, lanes_per_dir):
                dist = lane_w * k
                for side in ('left', 'right'):
                    for ln in all_lines:
                        try:
                            og = ln.parallel_offset(dist, side)
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


# ── 교차로 요소 (횡단보도 + 신호등) ─────────────────────────────────────────

_CROSSWALK_Z = MARKING_Z + 0.01
_SIG_COLOR = (0.12, 0.12, 0.12)
_PED_POLE_H = 3.2
_VEH_POLE_H = 5.0
_STOP_MARGIN = 1.5
_CROSSWALK_DEPTH = 3.5   # 횡단보도 깊이 (m) — 정지선 후퇴 기준


def _box_mesh(corners_bottom, z0, z1, color):
    """corners_bottom: 4개 (x,y) 튜플 리스트 → 박스 메시."""
    pts = np.array(
        [[c[0], c[1], z0] for c in corners_bottom] +
        [[c[0], c[1], z1] for c in corners_bottom],
        dtype=np.float32,
    )
    fi = [
        0, 3, 2,  0, 2, 1,   # bottom
        4, 5, 6,  4, 6, 7,   # top
        0, 1, 5,  0, 5, 4,   # front
        2, 3, 7,  2, 7, 6,   # back
        3, 0, 4,  3, 4, 7,   # left
        1, 2, 6,  1, 6, 5,   # right
    ]
    return pts, [3] * 12, fi, color


def _obox(cx, cy, z0, z1, ux, uy, hl, hw, color):
    """(ux,uy) 방향으로 정렬된 박스. hl=반길이, hw=반폭."""
    px, py = -uy, ux
    return _box_mesh([
        (cx + ux * hl + px * hw, cy + uy * hl + py * hw),
        (cx + ux * hl - px * hw, cy + uy * hl - py * hw),
        (cx - ux * hl - px * hw, cy - uy * hl - py * hw),
        (cx - ux * hl + px * hw, cy - uy * hl + py * hw),
    ], z0, z1, color)


def _make_crosswalk(sp, ux, uy, rvwd):
    """정지선 앞 횡단보도 줄무늬 메시 리스트."""
    stripe_hw = 0.225   # 줄 반폭 (도로 방향)
    gap = 0.35
    n = min(5, max(2, int(rvwd / 2.8)))
    meshes = []
    for i in range(n):
        offset = 0.5 + stripe_hw + i * (stripe_hw * 2 + gap)
        cx = sp.x - ux * offset
        cy = sp.y - uy * offset
        meshes.append(_obox(
            cx, cy,
            _CROSSWALK_Z, _CROSSWALK_Z + 0.025,
            ux, uy, stripe_hw, rvwd / 2,
            (1.0, 1.0, 1.0),
        ))
    return meshes


def _make_ped_signal(ex, ey):
    """보행자 신호등: 기둥 + 신호등 박스."""
    z0 = ROAD_Z + 0.05
    r = 0.06
    c = [(ex - r, ey - r), (ex + r, ey - r),
         (ex + r, ey + r), (ex - r, ey + r)]
    pole = _box_mesh(c, z0, z0 + _PED_POLE_H, _SIG_COLOR)
    hw, hd = 0.18, 0.12
    ch = [(ex - hw, ey - hd), (ex + hw, ey - hd),
          (ex + hw, ey + hd), (ex - hw, ey + hd)]
    head = _box_mesh(ch, z0 + _PED_POLE_H,
                     z0 + _PED_POLE_H + 0.38, (0.08, 0.08, 0.08))
    return [pole, head]


def _make_vehicle_signal(sp, ux, uy, rvwd):
    """ㄱ자 차량 신호등: 기둥 + arm + 신호등 박스."""
    px, py = -uy, ux          # 도로 왼쪽 수직 방향
    z0 = ROAD_Z + 0.05
    pole_top = z0 + _VEH_POLE_H

    # 기둥 위치: 도로 왼쪽 가장자리 + 0.5m
    bx = sp.x + px * (rvwd / 2 + 0.5)
    by = sp.y + py * (rvwd / 2 + 0.5)

    pr = 0.09
    pole = _box_mesh(
        [(bx - pr, by - pr), (bx + pr, by - pr),
         (bx + pr, by + pr), (bx - pr, by + pr)],
        z0, pole_top, _SIG_COLOR,
    )

    # arm: 기둥 꼭대기에서 도로 중심 방향으로
    arm_len = min(rvwd * 0.55, 7.0)
    adx, ady = -px, -py           # 도로 안쪽 방향
    arm_cx = bx + adx * arm_len / 2
    arm_cy = by + ady * arm_len / 2
    al = math.sqrt(adx ** 2 + ady ** 2)
    aux, auy = (adx / al, ady / al) if al > 0 else (1.0, 0.0)
    arm = _obox(arm_cx, arm_cy,
                pole_top - 0.08, pole_top + 0.08,
                aux, auy, arm_len / 2, 0.08, _SIG_COLOR)

    # 신호등 박스: arm 끝, 아래로 매달림
    hx = bx + adx * arm_len
    hy = by + ady * arm_len
    head = _obox(hx, hy,
                 pole_top - 0.55, pole_top,
                 ux, uy, 0.20, 0.23, (0.08, 0.08, 0.08))

    return [pole, arm, head]


def build_intersection_elements(gdf):
    """정지선 위치마다 횡단보도 + 신호등 생성. (pts,fc,fi,color) 튜플 리스트 반환."""
    rows_list = list(gdf.iterrows())
    road_geoms = [row.geometry for _, row in rows_list]
    road_rvwd_list = [float(row.get('rvwd') or 0) for _, row in rows_list]
    road_tree = STRtree(road_geoms)

    meshes = []
    seen = set()  # (ix, iy) 5m 격자 — 횡단보도/신호등 중복 방지

    for row_i, (_, row) in enumerate(rows_list):
        if str(row.get('dvyn') or '') != 'CSU002':
            continue
        if int(row.get('rdln') or 1) < 2:
            continue
        rvwd = float(row.get('rvwd') or 0)
        if rvwd <= 0:
            continue

        geom = row.geometry
        src_lines = list(geom.geoms) if hasattr(geom, 'geoms') else [geom]

        for line in src_lines:
            coords = list(line.coords)
            if len(coords) < 2:
                continue
            total = line.length

            dx_s = coords[1][0] - coords[0][0]
            dy_s = coords[1][1] - coords[0][1]
            dx_e = coords[-1][0] - coords[-2][0]
            dy_e = coords[-1][1] - coords[-2][1]
            sp_pt = Point(coords[0])
            ep_pt = Point(coords[-1])

            start_cut = end_cut = 0.0
            for ti in road_tree.query(sp_pt.buffer(20)):
                if ti == row_i:
                    continue
                if road_geoms[ti].distance(sp_pt) < 5.0:
                    odx, ody = _road_dir_at(road_geoms[ti], sp_pt)
                    if _crossing_angle(dx_s, dy_s, odx, ody) < 20:
                        continue
                    w = road_rvwd_list[ti]
                    if w / 2 > start_cut:
                        start_cut = w / 2
            for ti in road_tree.query(ep_pt.buffer(20)):
                if ti == row_i:
                    continue
                if road_geoms[ti].distance(ep_pt) < 5.0:
                    odx, ody = _road_dir_at(road_geoms[ti], ep_pt)
                    if _crossing_angle(dx_e, dy_e, odx, ody) < 20:
                        continue
                    w = road_rvwd_list[ti]
                    if w / 2 > end_cut:
                        end_cut = w / 2

            def _place(cut, dx, dy):
                if cut <= 0:
                    return
                cw_dist = cut + _STOP_MARGIN   # 횡단보도 위치 = 기존 정지선 자리
                if cw_dist + _CROSSWALK_DEPTH > total:
                    return
                spt = line.interpolate(cw_dist)
                key = (round(spt.x / 50), round(spt.y / 50))
                if key in seen:
                    return
                seen.add(key)
                ln = math.sqrt(dx ** 2 + dy ** 2)
                if ln < 0.01:
                    return
                ux, uy = dx / ln, dy / ln
                meshes.extend(_make_crosswalk(spt, ux, uy, rvwd))
                for side in (1, -1):
                    ex = spt.x + (-uy * side) * (rvwd / 2 + 0.5)
                    ey = spt.y + (ux * side) * (rvwd / 2 + 0.5)
                    meshes.extend(_make_ped_signal(ex, ey))
                meshes.extend(_make_vehicle_signal(spt, ux, uy, rvwd))

            _place(start_cut, dx_s, dy_s)
            _place(end_cut, dx_e, dy_e)

    return meshes
