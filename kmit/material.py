"""UsdShade PBR material with diffuse texture."""
from pxr import UsdShade, UsdGeom, Sdf, Vt, Gf
import numpy as np


def create_material(stage, mat_path: str, texture_path: str,
                    roughness: float = 0.7, metallic: float = 0.0):
    """
    Create a UsdPreviewSurface material with a diffuse texture.
    Returns UsdShade.Material.
    """
    mat = UsdShade.Material.Define(stage, mat_path)

    shader = UsdShade.Shader.Define(stage, f"{mat_path}/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(1.0)

    tex = UsdShade.Shader.Define(stage, f"{mat_path}/Diffuse")
    tex.CreateIdAttr("UsdUVTexture")
    tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(texture_path)
    tex.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
    tex.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")

    st_reader = UsdShade.Shader.Define(stage, f"{mat_path}/ST")
    st_reader.CreateIdAttr("UsdPrimvarReader_float2")
    st_reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")

    tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
        st_reader.ConnectableAPI(), "result"
    )
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
        tex.ConnectableAPI(), "rgb"
    )
    mat.CreateSurfaceOutput().ConnectToSource(
        shader.ConnectableAPI(), "surface"
    )
    return mat


def bind_material(mesh_prim, mat):
    UsdShade.MaterialBindingAPI(mesh_prim).Bind(mat)


def set_uv_primvar(mesh, uv_coords):
    """
    Assign face-varying UV (st) primvar to a UsdGeom.Mesh.
    uv_coords: list of (u, v) tuples, one per face-vertex (len = sum(faceVertexCounts)).
    """
    primvars_api = UsdGeom.PrimvarsAPI(mesh)
    pv = primvars_api.CreatePrimvar(
        "st",
        Sdf.ValueTypeNames.TexCoord2fArray,
        UsdGeom.Tokens.faceVarying,
    )
    pv.Set(Vt.Vec2fArray([Gf.Vec2f(float(u), float(v)) for u, v in uv_coords]))
