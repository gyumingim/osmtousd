"""
시나리오 ④ — V2X 통신 기반 협력주행 (TODO 1-H) · 폐루프

기능형 신호등(색 변화) + 신호 앞에서 줄서는 주행차량(적색정지·앞차추종)을
ACTOR_MODE=traffic 으로 실제 시뮬레이션하고, 그 상태에서 V2X 메시지를 생성:
  - SPaT: 씬의 실제 신호 위상
  - BSM: ego·차량 위치/방향 방송
  - V2V: 근접 차량쌍 경고
→ 통신이 거동(정지/추종)에 반영되는 폐루프. output/scenario_04/run/v2x_log.json

Usage:
    python3 scenarios/scenario_04_v2x.py
"""
import os
import json
import subprocess
import sys

ISAAC_PY = "/home/karma/isaacsim/_build/linux-x86_64/release/python.sh"
SENSOR_DRIVE = "/home/karma/OSMtoUSD/sensor_drive.py"
ISAAC_CWD = "/home/karma/isaacsim"
SUBDIR = "scenario_04/run"
NUM_FRAMES = os.environ.get("NUM_FRAMES", "14")


def main():
    print("=== 시나리오④ V2X 협력주행 (폐루프 신호+주행) ===", flush=True)
    env = dict(os.environ, ENV_LIGHTING="day", ENV_WEATHER="clear",
               SPEED_KPH="25", ACTOR_MODE="traffic",
               OUTPUT_SUBDIR=SUBDIR, NUM_FRAMES=NUM_FRAMES)
    rc = subprocess.run([ISAAC_PY, SENSOR_DRIVE], env=env,
                        cwd=ISAAC_CWD).returncode
    log = os.path.join("/home/karma/OSMtoUSD/output", SUBDIR, "v2x_log.json")
    if os.path.exists(log):
        d = json.load(open(log))
        cnt = {}
        for m in d["messages"]:
            cnt[m["type"]] = cnt.get(m["type"], 0) + 1
        phases = sorted({m["phase"] for m in d["messages"]
                         if m["type"] == "SPaT"})
        print(f"=== 완료: V2X {len(d['messages'])}개 {cnt} · 신호위상 {phases} ===")
    else:
        print(f"[경고] v2x_log.json 없음 (rc={rc})")
        sys.exit(1)


if __name__ == "__main__":
    main()
