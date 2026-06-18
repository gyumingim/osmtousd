"""시간대별 조명 프리셋 — DistantLight(태양) + DomeLight(천공).

Usage:
    from environment import apply_lighting
    apply_lighting(stage, "dusk")
"""
from pxr import UsdLux, UsdGeom, Gf

# preset → (태양각도 XYZ, 태양세기, 태양색, 돔세기, 돔색)
LIGHTING_PRESETS = {
    "dawn": {  # 새벽 — 낮고 따뜻한 햇빛
        "sun_rot": (-12, 0, 30), "sun_int": 900,
        "sun_color": (1.0, 0.72, 0.5),
        "dome_int": 300, "dome_color": (0.85, 0.75, 0.7),
    },
    "day": {  # 주간 — 높고 흰 햇빛
        "sun_rot": (-60, 0, 45), "sun_int": 3500,
        "sun_color": (1.0, 0.98, 0.95),
        "dome_int": 1000, "dome_color": (1.0, 1.0, 1.0),
    },
    "dusk": {  # 황혼 — 낮고 붉은 햇빛
        "sun_rot": (-8, 0, 60), "sun_int": 1100,
        "sun_color": (1.0, 0.5, 0.28),
        "dome_int": 250, "dome_color": (0.75, 0.5, 0.45),
    },
    "night": {  # 야간 — 햇빛 거의 없음, 푸른 천공
        "sun_rot": (-80, 0, 0), "sun_int": 25,
        "sun_color": (0.6, 0.7, 1.0),
        "dome_int": 45, "dome_color": (0.18, 0.22, 0.4),
    },
}


def apply_lighting(stage, preset, sun_path="/World/SunLight",
                   dome_path="/World/DomeLight"):
    """프리셋 조명을 씬에 적용 (없으면 생성)."""
    if preset not in LIGHTING_PRESETS:
        raise ValueError(f"알 수 없는 조명 프리셋: {preset} "
                         f"(가능: {list(LIGHTING_PRESETS)})")
    cfg = LIGHTING_PRESETS[preset]

    sun = UsdLux.DistantLight.Define(stage, sun_path)
    sun.CreateIntensityAttr(float(cfg["sun_int"]))
    sun.CreateColorAttr(Gf.Vec3f(*cfg["sun_color"]))
    sun.CreateAngleAttr(0.53)
    UsdGeom.XformCommonAPI(sun).SetRotate(
        Gf.Vec3f(*cfg["sun_rot"]), UsdGeom.XformCommonAPI.RotationOrderXYZ)

    dome = UsdLux.DomeLight.Define(stage, dome_path)
    dome.CreateIntensityAttr(float(cfg["dome_int"]))
    dome.CreateColorAttr(Gf.Vec3f(*cfg["dome_color"]))
    return cfg
