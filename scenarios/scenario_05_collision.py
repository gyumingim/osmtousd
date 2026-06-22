"""
시나리오 ⑤ — 사고위험·근접 상황 (TODO 1-I)

ego 경로 옆 고장차 + 측면 교차 진입차량으로 위험 코스 구성.
프레임별 TTC(Time-to-Collision) 자동 계산 → 접근/경고/임박/충돌 단계 라벨.

[한계/TODO] 실제 PhysX 충격(임팩트)은 미발생 — 운동학적 TTC 라벨만 생성.
또한 ego 폐루프가 전방 장애물에 제동하므로 회피 거동이 섞임. 진짜
충돌 이벤트(충격력·파손·충돌 후 거동)는 미구현.

Usage:
    python3 scenarios/scenario_05_collision.py
"""
import os
import glob
import json
import subprocess

ISAAC_PY = "/home/karma/isaacsim/_build/linux-x86_64/release/python.sh"
SENSOR_DRIVE = "/home/karma/OSMtoUSD/sensor_drive.py"
ISAAC_CWD = "/home/karma/isaacsim"
BASE = "/home/karma/OSMtoUSD/output"
SCENARIO = "scenario_05"

# 사고 직전/순간/회피 — 속도로 파라미터화 (고속일수록 TTC 짧음)
CASES = [
    ("imminent", "60"),   # 고속 접근 → 충돌 임박
    ("avoidance", "25"),  # 서행 → 회피 여지
]
NUM_FRAMES = os.environ.get("NUM_FRAMES", "12")


def run_case(name, speed):
    subdir = f"{SCENARIO}/{name}"
    print(f"\n{'='*60}\n[시나리오⑤ 충돌] {name} @ {speed}km/h → output/{subdir}\n"
          f"{'='*60}", flush=True)
    env = dict(os.environ, ENV_LIGHTING="day", ENV_WEATHER="clear",
               SPEED_KPH=speed, ACTOR_MODE="collision",
               OUTPUT_SUBDIR=subdir, NUM_FRAMES=NUM_FRAMES)
    return subprocess.run([ISAAC_PY, SENSOR_DRIVE], env=env,
                          cwd=ISAAC_CWD).returncode


def ttc_summary(name):
    files = sorted(glob.glob(os.path.join(BASE, SCENARIO, name,
                                           "frame_*.json")))
    seq = []
    for f in files:
        t = json.load(open(f)).get("ttc", {})
        seq.append((t.get("ttc_s"), t.get("phase")))
    return seq


def main():
    print(f"=== 시나리오⑤ 사고·충돌: {len(CASES)}케이스 × {NUM_FRAMES}프레임 ===")
    results = {}
    for name, speed in CASES:
        rc = run_case(name, speed)
        results[name] = "OK" if rc == 0 else f"FAIL({rc})"
    print("\n=== 시나리오⑤ 완료 ===")
    for name, _ in CASES:
        if results[name] == "OK":
            print(f"  {name}: {results[name]}  TTC열={ttc_summary(name)}")
        else:
            print(f"  {name}: {results[name]}")


if __name__ == "__main__":
    main()
