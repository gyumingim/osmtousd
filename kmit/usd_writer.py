from pxr import Usd, UsdGeom, Vt, Gf
import numpy as np


def write_usd(
    output_path: str,
    buildings_meshes: list,
    roads_meshes: list,
    generated_meshes: list = None,
    traffic_signal_meshes: list = None,
    crossing_meshes: list = None,
    vworld_meshes: list = None,
    sidewalk_meshes: list = None,
    marking_meshes: list = None,
    intersection_meshes: list = None,
):
    stage = Usd.Stage.CreateNew(output_path)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    stage.SetMetadata("metersPerUnit", 1.0)

    world = UsdGeom.Xform.Define(stage, "/World")

    _write_group(stage, "/World/Buildings", buildings_meshes, "B")
    _write_group(stage, "/World/Roads", roads_meshes, "R")
    if sidewalk_meshes:
        _write_group(stage, "/World/Sidewalks", sidewalk_meshes, "SW")
    if generated_meshes:
        _write_group(stage, "/World/GeneratedBuildings", generated_meshes, "G")
    if traffic_signal_meshes:
        _write_group(
            stage, "/World/TrafficSignals", traffic_signal_meshes, "T"
        )
    if crossing_meshes:
        _write_group(stage, "/World/Crossings", crossing_meshes, "C")
    if vworld_meshes:
        _write_group(stage, "/World/VworldBuildings", vworld_meshes, "V")
    if marking_meshes:
        _write_group(stage, "/World/RoadMarkings", marking_meshes, "M")
    if intersection_meshes:
        _write_group(stage, "/World/Intersections", intersection_meshes, "I")

    stage.SetDefaultPrim(world.GetPrim())
    stage.Save()
    print(f"Saved: {output_path}")


def _write_mesh(stage, prim_path, points, face_counts, face_indices,
                uv_coords=None, mat=None, color=None):
    from material import set_uv_primvar, bind_material
    mesh = UsdGeom.Mesh.Define(stage, prim_path)
    mesh.CreatePointsAttr().Set(
        Vt.Vec3fArray([
            Gf.Vec3f(float(p[0]), float(p[1]), float(p[2]))
            for p in points
        ])
    )
    mesh.CreateFaceVertexCountsAttr().Set(Vt.IntArray(face_counts))
    mesh.CreateFaceVertexIndicesAttr().Set(Vt.IntArray(face_indices))
    mesh.CreateDoubleSidedAttr().Set(True)

    pts = np.array(points)
    mn, mx = pts.min(axis=0), pts.max(axis=0)
    mesh.CreateExtentAttr().Set(
        Vt.Vec3fArray([Gf.Vec3f(*mn.tolist()), Gf.Vec3f(*mx.tolist())])
    )
    if color is not None:
        mesh.CreateDisplayColorAttr().Set(
            Vt.Vec3fArray([Gf.Vec3f(*color)])
        )
    if uv_coords is not None:
        set_uv_primvar(mesh, uv_coords)
    if mat is not None:
        bind_material(mesh.GetPrim(), mat)
    return mesh


def _write_group(stage, group_path: str, meshes: list, prefix: str):
    UsdGeom.Xform.Define(stage, group_path)
    written = 0
    for i, mesh_data in enumerate(meshes):
        if mesh_data is None:
            continue
        prim_path = f"{group_path}/{prefix}_{i}"
        if len(mesh_data) == 4:
            points, face_counts, face_indices, fourth = mesh_data
            if isinstance(fourth, tuple) and len(fourth) == 3:
                _write_mesh(stage, prim_path, points, face_counts,
                            face_indices, color=fourth)
            else:
                _write_mesh(stage, prim_path, points, face_counts,
                            face_indices, fourth)
        elif len(mesh_data) == 5:
            points, face_counts, face_indices, uv_coords, mat = mesh_data
            _write_mesh(stage, prim_path, points, face_counts,
                        face_indices, uv_coords, mat)
        else:
            points, face_counts, face_indices = mesh_data
            _write_mesh(stage, prim_path, points, face_counts, face_indices)
        written += 1

    print(f"  {group_path}: {written} meshes written")


def write_group_textured(stage, group_path, meshes_with_styles,
                         prefix, mat_cache):
    """
    meshes_with_styles: list of (points, fc, fi, uv_coords, texture_path)
    mat_cache: dict texture_path -> UsdShade.Material (reuse per texture)
    """
    from material import create_material, bind_material, set_uv_primvar
    UsdGeom.Xform.Define(stage, group_path)
    written = 0
    for i, item in enumerate(meshes_with_styles):
        if item is None:
            continue
        points, face_counts, face_indices, uv_coords, tex_path = item
        prim_path = f"{group_path}/{prefix}_{i}"

        if tex_path not in mat_cache:
            mat_path = f"/World/Materials/{prefix}_{len(mat_cache)}"
            mat_cache[tex_path] = create_material(stage, mat_path, tex_path)
        mat = mat_cache[tex_path]

        _write_mesh(stage, prim_path, points, face_counts,
                    face_indices, uv_coords, mat)
        written += 1
    print(f"  {group_path}: {written} textured meshes")
    return mat_cache
