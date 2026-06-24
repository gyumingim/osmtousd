"""기상 프리셋 — RTX 안개 + 천공 감광/틴트.

진짜 강수 파티클은 미구현(시나리오 단계). 여기선 가시거리·색조로 근사.

Usage:
    from environment import apply_weather
    apply_weather(stage, "fog")
"""
import carb
from pxr import UsdLux, Gf

# preset → (돔배율, 안개on, 안개색, 안개시작m, 안개끝m, 틴트)
WEATHER_PRESETS = {
    "clear": {  # 맑음
        "dome_mult": 1.0, "fog": False,
        "fog_color": (1, 1, 1), "fog_start": 0, "fog_end": 1000,
    },
    "cloudy": {  # 흐림 — 어둡고 회색
        "dome_mult": 0.6, "fog": False,
        "fog_color": (0.8, 0.8, 0.82), "fog_start": 0, "fog_end": 1000,
    },
    "fog": {  # 안개 — 가시거리 급감
        "dome_mult": 0.7, "fog": True,
        "fog_color": (0.82, 0.83, 0.86), "fog_start": 2, "fog_end": 60,
    },
    "rain": {  # 비 — 어둡고 옅은 안개
        "dome_mult": 0.4, "fog": True,
        "fog_color": (0.55, 0.6, 0.68), "fog_start": 5, "fog_end": 120,
    },
    "snow": {  # 눈 — 밝은 흰 산란, 가시거리 중간 (지면 반사로 밝음)
        "dome_mult": 0.9, "fog": True,
        "fog_color": (0.92, 0.93, 0.95), "fog_start": 3, "fog_end": 45,
    },
    "night_storm": {  # 야간 호우 — 매우 어둡고 가시거리 급감
        "dome_mult": 0.18, "fog": True,
        "fog_color": (0.32, 0.36, 0.45), "fog_start": 3, "fog_end": 55,
    },
}

# LiDAR 강수 감쇠율(포인트 드롭 확률) — sensor_drive.degrade_lidar에서 참조
LIDAR_DROP = {"clear": 0.0, "cloudy": 0.0, "fog": 0.5, "rain": 0.25,
              "snow": 0.45, "night_storm": 0.55}


def apply_weather(stage, preset, dome_path="/World/DomeLight"):
    """프리셋 기상을 적용. 조명(apply_lighting) 이후 호출."""
    if preset not in WEATHER_PRESETS:
        raise ValueError(f"알 수 없는 기상 프리셋: {preset} "
                         f"(가능: {list(WEATHER_PRESETS)})")
    cfg = WEATHER_PRESETS[preset]

    # 천공 감광 (현재 돔 세기에 배율)
    dome = UsdLux.DomeLight.Define(stage, dome_path)
    cur = dome.GetIntensityAttr().Get() or 800.0
    dome.CreateIntensityAttr(float(cur) * cfg["dome_mult"])

    # RTX 안개 (carb 런타임 설정)
    s = carb.settings.get_settings()
    s.set("/rtx/fog/enabled", bool(cfg["fog"]))
    if cfg["fog"]:
        s.set("/rtx/fog/fogColor", list(cfg["fog_color"]))
        s.set("/rtx/fog/fogStartDist", float(cfg["fog_start"]))
        s.set("/rtx/fog/fogEndDist", float(cfg["fog_end"]))
        s.set("/rtx/fog/fogColorIntensity", 1.0)
    return cfg
