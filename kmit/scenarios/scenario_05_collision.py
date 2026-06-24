"""
시나리오 ⑤ — 사고위험·근접 상황 (TODO 1-I)

ego 경로 옆 고장차 + 측면 교차 진입차량으로 위험 코스 구성.
프레임별 TTC(Time-to-Collision) 자동 계산 → 접근/경고/임박/충돌 단계 라벨.

실제 접촉 감지: ego가 차로 위 고장차에 접근 → 무반응(사고)이면 충돌
이벤트(임팩트속도·프레임·대상) 기록 + 충돌후 정지, 제동(회피)이면 정지.
[한계] PhysX 충격력/파손은 미모델(운동학적 접촉 감지·임팩트속도까지).

Usage:
    python3 scenarios/scenario_05_collision.py
"""
import os
import glob
import json
import subprocess

ISAAC_PY = "/home/karma/isaacsim/_build/linux-x86_64/release/python.sh"
SENSOR_DRIVE = "/home/karma/OSMtoUSD/kmit/sensor_drive.py"
ISAAC_CWD = "/home/karma/isaacsim"
BASE = "/home/karma/OSMtoUSD/kmit/output"
SCENARIO = "scenario_05"

# 사고 vs 회피 — (속도, ego반응). 무반응 돌진=실제 충돌, 제동=회피
CASES = [
    ("imminent", "60", "0"),   # 고속 무반응 → 실제 충돌 발생
    ("avoidance", "25", "1"),  # 서행 제동 → 회피
]
NUM_FRAMES = os.environ.get("NUM_FRAMES", "12")


def run_case(name, speed, react):
    subdir = f"{SCENARIO}/{name}"
    print(f"\n{'='*60}\n[시나리오⑤ 충돌] {name} @ {speed}km/h react={react} "
          f"→ output/{subdir}\n{'='*60}", flush=True)
    env = dict(os.environ, ENV_LIGHTING="day", ENV_WEATHER="clear",
               SPEED_KPH=speed, ACTOR_MODE="collision", EGO_REACT=react,
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
    for name, speed, react in CASES:
        rc = run_case(name, speed, react)
        results[name] = "OK" if rc == 0 else f"FAIL({rc})"
    print("\n=== 시나리오⑤ 완료 ===")
    for name, _, _ in CASES:
        if results[name] == "OK":
            print(f"  {name}: {results[name]}  TTC열={ttc_summary(name)}")
        else:
            print(f"  {name}: {results[name]}")


if __name__ == "__main__":
    main()
