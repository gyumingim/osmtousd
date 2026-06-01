"""
Apply procedural textures to an existing USD building scene.

Usage:
    python3 apply_textures.py [usd_file]

UV is computed via triplanar mapping from vertex positions -- no OSM
re-download needed. Run after main.py has generated the USD geometry.
"""
import sys
import os
import numpy as np
from pxr import Usd, UsdGeom

from texture_gen import generate_all_textures, get_texture_path
from material import create_material, bind_material, set_uv_primvar

USD_FILE = "busan_univ.usda"
BAY_W = 3.0    # meters per window bay (UV tiling unit)
FLOOR_H = 3.0  # meters per floor

# Style assigned to each building group
GROUP_STYLES = {
    "/World/Buildings":          None,      # auto by index (varied)
    "/World/VworldBuildings":    None,
    "/World/GeneratedBuildings": "generic",
    "/World/Roads":              "asphalt",
    "/World/Crossings":          "asphalt",
}

# OSM building index -> style cycle
_OSM_CYCLE = [
    "residential", "residential", "residential",
    "commercial", "commercial",
    "educational",
    "generic",
]

# Vworld building index -> style cycle (mostly industrial for Gumi)
_VW_CYCLE = [
    "industrial", "industrial", "industrial",
    "generic", "commercial",
]


def _triplanar_uv(pts_np):
    """
    Compute face-varying UV for one triangle via triplanar projection.
    pts_np: (3, 3) float array — triangle vertices
    Returns [(u0,v0), (u1,v1), (u2,v2)]
    """
    e1 = pts_np[1] - pts_np[0]
    e2 = pts_np[2] - pts_np[0]
    n = np.cross(e1, e2)
    nlen = np.linalg.norm(n)
    if nlen < 1e-6:
        return [(0.0, 0.0)] * 3
    n /= nlen
    ax, ay, az = abs(n[0]), abs(n[1]), abs(n[2])

    uvs = []
    for p in pts_np:
        if az >= ax and az >= ay:
            # Horizontal face (roof / ground) → XY
            uvs.append((p[0] / BAY_W, p[1] / BAY_W))
        elif ax >= ay:
            # Wall facing ±X → YZ
            uvs.append((p[1] / BAY_W, p[2] / FLOOR_H))
        else:
            # Wall facing ±Y → XZ
            uvs.append((p[0] / BAY_W, p[2] / FLOOR_H))
    return uvs


def _mesh_uvs(pts, face_counts, face_indices):
    """Compute full face-varying UV list for a mesh."""
    pts_np = np.array(pts, dtype=np.float32)
    uv_list = []
    fi = 0
    for fc in face_counts:
        verts = pts_np[[face_indices[fi + k] for k in range(fc)]]
        if fc == 3:
            uv_list.extend(_triplanar_uv(verts))
        else:
            # Fan triangulate for safety
            for t in range(fc - 2):
                tri = np.array([verts[0], verts[t + 1], verts[t + 2]])
                uv_list.extend(_triplanar_uv(tri))
        fi += fc
    return uv_list


def _style_for(group_path, index):
    fixed = GROUP_STYLES.get(group_path)
    if fixed:
        return fixed
    if "Vworld" in group_path:
        return _VW_CYCLE[index % len(_VW_CYCLE)]
    return _OSM_CYCLE[index % len(_OSM_CYCLE)]


def apply_textures(usd_path):
    print(f"Opening: {usd_path}")
    stage = Usd.Stage.Open(usd_path)

    print("Generating textures...")
    generate_all_textures()

    mat_cache = {}
    total = 0

    for group_path in GROUP_STYLES:
        group_prim = stage.GetPrimAtPath(group_path)
        if not group_prim.IsValid():
            continue
        children = list(group_prim.GetChildren())
        print(f"  {group_path}: {len(children)} meshes")

        for idx, child in enumerate(children):
            mesh = UsdGeom.Mesh(child)
            pts_attr = mesh.GetPointsAttr().Get()
            counts_attr = mesh.GetFaceVertexCountsAttr().Get()
            indices_attr = mesh.GetFaceVertexIndicesAttr().Get()
            if pts_attr is None:
                continue

            pts = list(pts_attr)
            counts = list(counts_attr)
            indices = list(indices_attr)

            style = _style_for(group_path, idx)
            variation = idx % 4
            tex_path = get_texture_path(style, variation)

            # Reuse material if same texture
            if tex_path not in mat_cache:
                mat_path = f"/World/Materials/M_{len(mat_cache)}"
                mat_cache[tex_path] = create_material(
                    stage, mat_path, tex_path,
                    roughness=0.75, metallic=0.0,
                )

            uv_list = _mesh_uvs(pts, counts, indices)
            set_uv_primvar(mesh, uv_list)
            bind_material(child, mat_cache[tex_path])
            total += 1

    stage.Save()
    print(f"Done: {total} meshes textured, "
          f"{len(mat_cache)} unique materials")
    print(f"Saved: {usd_path}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else USD_FILE
    if not os.path.exists(path):
        print(f"File not found: {path}")
        sys.exit(1)
    apply_textures(path)
