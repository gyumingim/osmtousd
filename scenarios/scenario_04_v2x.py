"""
시나리오 ④ — V2X 통신 기반 협력주행 (TODO 1-H)

주행 수집(sensor_drive) 후, ego·차량 궤적에서 V2X 메시지를 합성:
  - BSM (Basic Safety Message): 각 차량이 매 프레임 위치·속도·방향 방송
  - V2V: 근접 차량쌍 전방충돌 경고
  - V2I/SPaT: 교차로 신호 위상·잔여시간 방송

산출: output/scenario_04/run/v2x_log.json  (협력주행 메시지 로그)

Usage:
    python3 scenarios/scenario_04_v2x.py
"""
import os
import glob
import json
import math
import subprocess

ISAAC_PY = "/home/karma/isaacsim/_build/linux-x86_64/release/python.sh"
SENSOR_DRIVE = "/home/karma/OSMtoUSD/sensor_drive.py"
ISAAC_CWD = "/home/karma/isaacsim"
BASE = "/home/karma/OSMtoUSD/output"
SUBDIR = "scenario_04/run"
DT = 1.0 / 10
V2V_RANGE = 30.0   # V2V 통신/경고 반경 (m)
SPAT_CYCLE = [("green", 30), ("yellow", 4), ("red", 26)]  # 신호 위상(초)


def collect():
    print("=== 시나리오④ 주행 수집 ===", flush=True)
    env = dict(os.environ, ENV_LIGHTING="day", ENV_WEATHER="clear",
               SPEED_KPH="40", OUTPUT_SUBDIR=SUBDIR,
               NUM_FRAMES=os.environ.get("NUM_FRAMES", "12"))
    return subprocess.run([ISAAC_PY, SENSOR_DRIVE], env=env,
                          cwd=ISAAC_CWD).returncode


def spat_phase(t):
    """누적시간 t(초)에서 신호 위상 + 다음전환까지 잔여."""
    total = sum(d for _, d in SPAT_CYCLE)
    tm = t % total
    for phase, dur in SPAT_CYCLE:
        if tm < dur:
            return phase, round(dur - tm, 1)
        tm -= dur
    return "red", 0.0


def bsm(sender, fr, st):
    return {"type": "BSM", "sender": sender, "frame": fr,
            "timestamp": round(fr * DT, 2),
            "x": st["x"], "y": st["y"],
            "speed_kph": st.get("speed_kph", 0.0),
            "heading": st.get("yaw", 0.0)}


def build_v2x():
    files = sorted(glob.glob(os.path.join(BASE, SUBDIR, "frame_*.json")))
    log = []
    for f in files:
        d = json.load(open(f))
        fr = d["frame"]
        ts = round(fr * DT, 2)
        # 차량 목록: ego + vehicle 라벨 액터
        vehicles = {"ego": {"x": d["ego"]["x"], "y": d["ego"]["y"],
                            "speed_kph": d["speed_kph"],
                            "yaw": d["ego"]["yaw_deg"]}}
        for i, a in enumerate(d.get("actors", [])):
            if a["label"] == "vehicle":
                vehicles[f"veh_{i}"] = {"x": a["x"], "y": a["y"],
                                        "speed_kph": 0.0, "yaw": a["yaw"]}
        # BSM 방송
        for vid, st in vehicles.items():
            log.append(bsm(vid, fr, st))
        # V2V 근접 경고
        ids = list(vehicles)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = vehicles[ids[i]], vehicles[ids[j]]
                rng = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
                if rng <= V2V_RANGE:
                    log.append({"type": "V2V", "from": ids[i], "to": ids[j],
                                "frame": fr, "timestamp": ts,
                                "range_m": round(rng, 2),
                                "alert": "proximity"
                                if rng > 8 else "forward_collision_warning"})
        # V2I / SPaT 방송
        phase, ttc = spat_phase(ts)
        log.append({"type": "SPaT", "sender": "RSU_intersection_01",
                    "frame": fr, "timestamp": ts,
                    "phase": phase, "time_to_change_s": ttc})
    return log


def main():
    rc = collect()
    if rc != 0:
        print(f"[오류] 주행 수집 실패 rc={rc}")
        return
    print("=== V2X 메시지 합성 ===", flush=True)
    log = build_v2x()
    out = os.path.join(BASE, SUBDIR, "v2x_log.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"dt": DT, "v2v_range_m": V2V_RANGE,
                   "messages": log}, f, indent=2, ensure_ascii=False)
    counts = {}
    for m in log:
        counts[m["type"]] = counts.get(m["type"], 0) + 1
    print(f"=== 시나리오④ 완료: {len(log)}개 메시지 {counts} → {out} ===")


if __name__ == "__main__":
    main()
