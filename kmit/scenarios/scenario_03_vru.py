"""
시나리오 ③ — 보행자·이륜차 상호작용 VRU (TODO 1-G)

ego 전방 횡단지점에서 보행자(정상횡단/무단횡단)와 이륜차(끼어들기)가
실제로 움직이는 상호작용 장면. sensor_drive를 ACTOR_MODE=vru로 구동.

핵심: 움직이는 VRU + 행동(behavior) 라벨 + 프레임별 궤적 기록(JSON actors).

Usage:
    python3 scenarios/scenario_03_vru.py
"""
import os
import subprocess
import sys

ISAAC_PY = "/home/karma/isaacsim/_build/linux-x86_64/release/python.sh"
SENSOR_DRIVE = "/home/karma/OSMtoUSD/sensor_drive.py"
ISAAC_CWD = "/home/karma/isaacsim"
SCENARIO = "scenario_03"

# VRU는 저속 접근에서 상호작용 관찰 (도심 서행)
EGO_SPEED_KPH = "20"
COMBOS = [
    ("day",  "clear"),
    ("dusk", "clear"),
]
NUM_FRAMES = os.environ.get("NUM_FRAMES", "12")


def run_combo(light, weather):
    subdir = f"{SCENARIO}/{light}_{weather}"
    print(f"\n{'='*60}\n[시나리오③ VRU] {light}+{weather} → output/{subdir}\n"
          f"{'='*60}", flush=True)
    env = dict(
        os.environ,
        ENV_LIGHTING=light,
        ENV_WEATHER=weather,
        SPEED_KPH=EGO_SPEED_KPH,
        ACTOR_MODE="vru",
        OUTPUT_SUBDIR=subdir,
        NUM_FRAMES=NUM_FRAMES,
    )
    return subprocess.run([ISAAC_PY, SENSOR_DRIVE], env=env,
                          cwd=ISAAC_CWD).returncode


def main():
    print(f"=== 시나리오③ VRU: {len(COMBOS)}조합 × {NUM_FRAMES}프레임 "
          f"(움직이는 보행자/이륜차) ===")
    results = {}
    for light, weather in COMBOS:
        rc = run_combo(light, weather)
        results[f"{light}_{weather}"] = "OK" if rc == 0 else f"FAIL({rc})"
    print("\n=== 시나리오③ 완료 ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    if any(v != "OK" for v in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
