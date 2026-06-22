"""
시나리오 ② — 산업단지 AMR 물류 (TODO 1-F)

구미 1산단 환경에서 AMR 페이스(저속 8km/h) 주행 데이터 수집.
시나리오①과 동일 엔진(sensor_drive.py)을 저속·주야 변주로 구동.

[한계/TODO] 전용 AMR 로봇 에셋 없음(ego는 무형 Xform), 지게차/작업자는
정적 배치(ACTOR_MODE=static). 실제 AMR 모델·창고·로딩독·동적 작업자
상호작용은 미구현 — Omniverse Warehouse 샘플 연동 시 보강 예정.

Usage:
    python3 scenarios/scenario_02_amr.py
"""
import os
import subprocess
import sys

ISAAC_PY = "/home/karma/isaacsim/_build/linux-x86_64/release/python.sh"
SENSOR_DRIVE = "/home/karma/OSMtoUSD/sensor_drive.py"
ISAAC_CWD = "/home/karma/isaacsim"
SCENARIO = "scenario_02"

AMR_SPEED_KPH = "8"   # AMR 저속 (승용차 100 대비)
# AMR 운용 시간대 변주 (물류는 주야간 운영)
COMBOS = [
    ("day",   "clear"),
    ("day",   "cloudy"),
    ("night", "clear"),
]
NUM_FRAMES = os.environ.get("NUM_FRAMES", "10")


def run_combo(light, weather):
    subdir = f"{SCENARIO}/{light}_{weather}"
    print(f"\n{'='*60}\n[시나리오② AMR] {light}+{weather} @ {AMR_SPEED_KPH}km/h "
          f"→ output/{subdir}\n{'='*60}", flush=True)
    env = dict(
        os.environ,
        ENV_LIGHTING=light,
        ENV_WEATHER=weather,
        SPEED_KPH=AMR_SPEED_KPH,
        OUTPUT_SUBDIR=subdir,
        NUM_FRAMES=NUM_FRAMES,
    )
    return subprocess.run([ISAAC_PY, SENSOR_DRIVE], env=env,
                          cwd=ISAAC_CWD).returncode


def main():
    print(f"=== 시나리오② AMR물류: {len(COMBOS)}조합 × {NUM_FRAMES}프레임 "
          f"@ {AMR_SPEED_KPH}km/h ===")
    results = {}
    for light, weather in COMBOS:
        rc = run_combo(light, weather)
        results[f"{light}_{weather}"] = "OK" if rc == 0 else f"FAIL({rc})"
    print("\n=== 시나리오② 완료 ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    if any(v != "OK" for v in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
