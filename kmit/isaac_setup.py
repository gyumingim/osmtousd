"""
Isaac Sim 자율주행 시뮬레이션을 위한 USD 후처리 스크립트.

순서:
  1. Physics: PhysicsScene + 콜라이더
  2. Semantics: 커스텀 속성으로 레이블
  3. Road Graph: 도로 중심선 BasisCurves

Usage:
    python3 isaac_setup.py gumi.usda
"""
import sys
from pxr import Usd, UsdGeom, UsdPhysics, Gf, Vt, Sdf

from vworld_loader import load_as_gdf

USD_PATH = sys.argv[1] if len(sys.argv) > 1 else "gumi.usda"

# 그룹별 물리 콜라이더 근사 방식 + 시맨틱 레이블
_GROUP_CONFIG = {
    "/World/Roads":              ("none",       "road"),
    "/World/RoadMarkings":       ("none",       "road_marking"),
    "/World/Intersections":      ("none",       "crosswalk"),
    "/World/Crossings":          ("none",       "crosswalk"),
    "/World/Buildings":          ("convexHull", "building"),
    "/World/VworldBuildings":    ("convexHull", "building"),
    "/World/GeneratedBuildings": ("convexHull", "building"),
    "/World/TrafficSignals":     ("none",       "traffic_sign"),
}


# ── 1. Physics ────────────────────────────────────────────────────────────────

def setup_physics(stage):
    print("  [1] Physics 설정...")

    # PhysicsScene
    scene = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, -1.0))
    scene.CreateGravityMagnitudeAttr().Set(9.81)

    # 도로 아래 invisible ground plane (z=0)
    plane = UsdGeom.Mesh.Define(stage, "/World/GroundPlane")
    s = 5000.0
    plane.CreatePointsAttr().Set(Vt.Vec3fArray([
        Gf.Vec3f(-s, -s, 0), Gf.Vec3f(s, -s, 0),
        Gf.Vec3f(s,  s, 0), Gf.Vec3f(-s,  s, 0),
    ]))
    plane.CreateFaceVertexCountsAttr().Set(Vt.IntArray([4]))
    plane.CreateFaceVertexIndicesAttr().Set(Vt.IntArray([0, 1, 2, 3]))
    plane.CreateDoubleSidedAttr().Set(True)
    UsdGeom.Imageable(plane).MakeInvisible()
    UsdPhysics.CollisionAPI.Apply(plane.GetPrim())

    # 각 그룹 메시에 CollisionAPI 적용
    total = 0
    for group_path, (approx, _) in _GROUP_CONFIG.items():
        group = stage.GetPrimAtPath(group_path)
        if not group.IsValid():
            continue
        for child in group.GetChildren():
            UsdPhysics.CollisionAPI.Apply(child)
            mc = UsdPhysics.MeshCollisionAPI.Apply(child)
            mc.CreateApproximationAttr().Set(approx)
            total += 1

    print(f"     콜라이더 {total}개 적용")


# ── 2. Semantics ──────────────────────────────────────────────────────────────

def setup_semantics(stage):
    print("  [2] Semantic 레이블 설정...")

    # Isaac Sim 호환: primvar "semanticLabel" (string) 방식
    for group_path, (_, label) in _GROUP_CONFIG.items():
        group = stage.GetPrimAtPath(group_path)
        if not group.IsValid():
            continue

        # 그룹 prim 자체에 레이블 속성 추가
        prim = group
        prim.CreateAttribute(
            "isaac:semantic_label",
            Sdf.ValueTypeNames.String,
        ).Set(label)

        # 각 자식 메시에도 적용 (센서 ray cast 대응)
        for child in group.GetChildren():
            child.CreateAttribute(
                "isaac:semantic_label",
                Sdf.ValueTypeNames.String,
            ).Set(label)

    print(f"     {len(_GROUP_CONFIG)}개 그룹 레이블 완료")


# ── 3. Road Graph ─────────────────────────────────────────────────────────────

def _line_to_curve(stage, path, line_geom, lane_idx, rdln, rvwd,
                   bidirectional):
    """단일 차선 BasisCurve 생성."""
    coords = [(float(c[0]), float(c[1])) for c in line_geom.coords]
    if len(coords) < 2:
        return False
    curve = UsdGeom.BasisCurves.Define(stage, path)
    curve.CreatePointsAttr().Set(Vt.Vec3fArray([
        Gf.Vec3f(x, y, 0.12) for x, y in coords
    ]))
    curve.CreateCurveVertexCountsAttr().Set(Vt.IntArray([len(coords)]))
    curve.CreateTypeAttr().Set("linear")
    curve.CreateWidthsAttr().Set(Vt.FloatArray([0.15] * len(coords)))
    p = curve.GetPrim()
    p.CreateAttribute("road:lane_index",
                      Sdf.ValueTypeNames.Int).Set(lane_idx)
    p.CreateAttribute("road:total_lanes",
                      Sdf.ValueTypeNames.Int).Set(rdln)
    p.CreateAttribute("road:width_m",
                      Sdf.ValueTypeNames.Float).Set(rvwd)
    p.CreateAttribute("road:bidirectional",
                      Sdf.ValueTypeNames.Bool).Set(bidirectional)
    return True


def setup_road_graph(stage):
    print("  [3] Road Graph — 차선별 BasisCurves 생성...")

    gdf = load_as_gdf("lt_l_n3a0020000")
    if gdf is None:
        print("     [스킵] lt_l_n3a0020000 없음")
        return

    # 이전 RoadGraph 있으면 삭제 후 재생성
    old = stage.GetPrimAtPath("/World/RoadGraph")
    if old.IsValid():
        stage.RemovePrim("/World/RoadGraph")
    UsdGeom.Xform.Define(stage, "/World/RoadGraph")

    written = 0

    for i, (_, row) in enumerate(gdf.iterrows()):
        geom = row.geometry
        src_lines = list(geom.geoms) if hasattr(geom, 'geoms') else [geom]
        rdln = int(row.get('rdln') or 1)
        rvwd = float(row.get('rvwd') or 0)
        bidirectional = str(row.get('dvyn') or '') == 'CSU002'
        lane_w = rvwd / rdln if rdln > 0 and rvwd > 0 else 3.5

        for j, line in enumerate(src_lines):
            if len(list(line.coords)) < 2:
                continue

            # 각 차선 중심선 = centerline ± (k + 0.5) * lane_w
            for k in range(rdln):
                # 중심에서 오른쪽으로 k번째 차선
                half = rdln / 2
                offset = (k - half + 0.5) * lane_w

                try:
                    if abs(offset) < 0.01:
                        lane_line = line
                    elif offset > 0:
                        lane_line = line.parallel_offset(offset, 'right')
                    else:
                        lane_line = line.parallel_offset(-offset, 'left')

                    if lane_line is None or lane_line.is_empty:
                        continue

                    sub_lines = (list(lane_line.geoms)
                                 if hasattr(lane_line, 'geoms')
                                 else [lane_line])
                    for m, sl in enumerate(sub_lines):
                        path = f"/World/RoadGraph/C_{i}_{j}_L{k}_{m}"
                        if _line_to_curve(stage, path, sl, k, rdln,
                                          rvwd, bidirectional):
                            written += 1
                except Exception:
                    pass

    print(f"     차선 커브 {written}개 생성")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"Isaac Sim 설정: {USD_PATH}")
    stage = Usd.Stage.Open(USD_PATH)

    setup_physics(stage)
    setup_semantics(stage)
    setup_road_graph(stage)

    stage.Save()
    print(f"저장 완료: {USD_PATH}")
    print("\n다음 단계: Isaac Sim에서 열고 차량 asset 배치")


if __name__ == "__main__":
    main()
