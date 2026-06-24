"""
시나리오 ① — 극한 기상 조건 자율주행 (TODO 1-E)

동일 경로를 기상·조명 조합별로 반복 수집해 페어 데이터셋 생성.
각 조합은 sensor_drive.py를 별도 Isaac 세션으로 실행 (환경변수 주입).

Usage (Isaac 불필요, 순수 오케스트레이터):
    python3 scenarios/scenario_01_weather.py
"""
import os
import subprocess
import sys

ISAAC_PY = "/home/karma/isaacsim/_build/linux-x86_64/release/python.sh"
SENSOR_DRIVE = "/home/karma/OSMtoUSD/sensor_drive.py"
ISAAC_CWD = "/home/karma/isaacsim"
SCENARIO = "scenario_01"

# (조명, 기상) 조합 — 동일 경로에 대한 환경 변주
COMBOS = [
    ("day",   "clear"),
    ("day",   "rain"),
    ("dusk",  "fog"),
    ("night", "rain"),
    ("day",   "snow"),
    ("night", "night_storm"),
]
NUM_FRAMES = os.environ.get("NUM_FRAMES", "10")


def run_combo(light, weather):
    subdir = f"{SCENARIO}/{light}_{weather}"
    print(f"\n{'='*60}\n[시나리오①] {light} + {weather} → output/{subdir}\n{'='*60}",
          flush=True)
    env = dict(
        os.environ,
        ENV_LIGHTING=light,
        ENV_WEATHER=weather,
        OUTPUT_SUBDIR=subdir,
        NUM_FRAMES=NUM_FRAMES,
    )
    r = subprocess.run([ISAAC_PY, SENSOR_DRIVE], env=env, cwd=ISAAC_CWD)
    return r.returncode


def main():
    print(f"=== 시나리오① 극한기상: {len(COMBOS)}개 조합 × {NUM_FRAMES}프레임 ===")
    results = {}
    for light, weather in COMBOS:
        rc = run_combo(light, weather)
        results[f"{light}_{weather}"] = "OK" if rc == 0 else f"FAIL({rc})"
    print("\n=== 시나리오① 완료 ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    if any(v != "OK" for v in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
