"""시나리오 파라미터 조합 생성기 (TODO 공통인프라)

sensor_drive.py가 env var로 완전 파라미터화돼 있으므로, 조명×기상×액터모드×
속도×프레임 그리드를 열거해 일괄 생성한다. 대량 생성(목표 1만 프레임) 확장용.

머신 보호: Isaac Sim은 한 번에 하나씩만 순차 실행(동시 실행 금지).

Usage:
    python3 pipeline/run_scenario.py --dry-run        # 조합만 출력
    python3 pipeline/run_scenario.py --frames 50      # 실제 생성
    python3 pipeline/run_scenario.py --grid vru       # 프리셋 그리드 선택
"""
import os
import sys
import argparse
import itertools
import subprocess

ISAAC_PY = "/home/karma/isaacsim/_build/linux-x86_64/release/python.sh"
SENSOR_DRIVE = "/home/karma/OSMtoUSD/sensor_drive.py"
ISAAC_CWD = "/home/karma/isaacsim"

# 프리셋 그리드 (조명, 기상, 액터모드, 속도kph)
GRIDS = {
    "weather": {  # 극한기상 변주
        "light": ["day", "dusk", "night"],
        "weather": ["clear", "rain", "fog", "snow", "night_storm"],
        "mode": ["static"], "speed": [100],
    },
    "vru": {
        "light": ["day", "dusk"], "weather": ["clear", "rain"],
        "mode": ["vru"], "speed": [30],
    },
    "traffic": {
        "light": ["day", "night"], "weather": ["clear", "fog"],
        "mode": ["traffic"], "speed": [25],
    },
    "full": {  # 전체 교차 (대량)
        "light": ["day", "dusk", "night"],
        "weather": ["clear", "rain", "fog", "snow"],
        "mode": ["static", "vru", "traffic"], "speed": [40],
    },
}


def combos(grid):
    g = GRIDS[grid]
    # night_storm은 night에서만 의미
    for light, weather, mode, speed in itertools.product(
            g["light"], g["weather"], g["mode"], g["speed"]):
        if weather == "night_storm" and light != "night":
            continue
        yield light, weather, mode, speed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", default="weather", choices=list(GRIDS))
    ap.add_argument("--frames", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="custom")
    a = ap.parse_args()

    cs = list(combos(a.grid))
    print(f"=== 그리드 '{a.grid}': {len(cs)}개 조합 × {a.frames}프레임 "
          f"= {len(cs) * a.frames} 프레임 ===")
    for light, weather, mode, speed in cs:
        sub = f"{a.out}/{mode}_{light}_{weather}_{speed}"
        print(f"  · {light:5} {weather:12} {mode:8} {speed}km/h → {sub}")
        if a.dry_run:
            continue
        env = dict(os.environ, ENV_LIGHTING=light, ENV_WEATHER=weather,
                   ACTOR_MODE=mode, SPEED_KPH=str(speed),
                   NUM_FRAMES=str(a.frames), OUTPUT_SUBDIR=sub)
        rc = subprocess.run([ISAAC_PY, SENSOR_DRIVE], env=env,
                            cwd=ISAAC_CWD).returncode      # 순차(동시금지)
        print(f"    {'✅' if rc == 0 else f'❌ rc={rc}'}")
    if a.dry_run:
        print("\n(--dry-run: 실제 생성 안 함. --frames N 으로 실행)")


if __name__ == "__main__":
    main()
