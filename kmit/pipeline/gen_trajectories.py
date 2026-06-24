"""궤적 라벨 생성 (TODO 1-G 보행자·차량 궤적) — Isaac 비의존.

프레임별 actors/ego 위치를 트랙으로 묶어 trajectories.json 생성. actors는
스폰 순서가 프레임 간 고정이라 인덱스를 트랙ID로 사용. 트랙별 변위·평균속력·
거동을 집계.

[한계] 골격 Pose(관절 키포인트)는 UsdSkel 쿼리(Isaac)가 필요해 별도. 여기선
객체 단위 2D 궤적(x,y,yaw 시퀀스)까지.

Usage:
    python3 pipeline/gen_trajectories.py [output_dir] [--datasets]
"""
import os
import sys
import glob
import json
import math

BASE = "/home/karma/OSMtoUSD/kmit/output"
if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
    BASE = sys.argv[1]
DT = 1.0 / 10


def build_tracks(combo_dir):
    frames = sorted(glob.glob(os.path.join(combo_dir, "frame_*.json")))
    if not frames:
        return None
    tracks = {}        # idx → {class, points:[{frame,x,y,yaw}]}
    ego = []
    for jp in frames:
        d = json.load(open(jp))
        fi = d.get("frame")
        e = d.get("ego", {})
        ego.append({"frame": fi, "x": round(e.get("x", 0), 2),
                    "y": round(e.get("y", 0), 2),
                    "yaw": round(e.get("yaw_deg", 0), 1)})
        for i, a in enumerate(d.get("actors", [])):
            t = tracks.setdefault(i, {"class": a.get("label"),
                                      "behavior": a.get("behavior"),
                                      "points": []})
            t["points"].append({"frame": fi, "x": round(a.get("x", 0), 2),
                                 "y": round(a.get("y", 0), 2),
                                 "yaw": round(a.get("yaw", 0), 1)})

    def stats(pts):
        if len(pts) < 2:
            return 0.0, 0.0
        disp = math.hypot(pts[-1]["x"] - pts[0]["x"],
                          pts[-1]["y"] - pts[0]["y"])
        path = sum(math.hypot(pts[k]["x"] - pts[k - 1]["x"],
                              pts[k]["y"] - pts[k - 1]["y"])
                   for k in range(1, len(pts)))
        avg_spd = path / ((len(pts) - 1) * DT)
        return round(disp, 2), round(avg_spd, 2)

    out_tracks = []
    for idx, t in tracks.items():
        disp, spd = stats(t["points"])
        out_tracks.append({
            "track_id": idx, "class": t["class"], "behavior": t["behavior"],
            "displacement_m": disp, "avg_speed_mps": spd,
            "moving": spd > 0.2, "points": t["points"],
        })
    e_disp, e_spd = stats(ego)
    return {
        "frames": len(frames), "dt_s": DT,
        "ego": {"displacement_m": e_disp, "avg_speed_mps": e_spd,
                "points": ego},
        "num_tracks": len(out_tracks),
        "moving_tracks": sum(1 for t in out_tracks if t["moving"]),
        "tracks": out_tracks,
    }


def main():
    combos = sorted(d for d in glob.glob(os.path.join(BASE, "scenario_*", "*"))
                    if os.path.isdir(d))
    print(f"=== 궤적 생성: {len(combos)}개 데이터셋 ===")
    for cd in combos:
        tr = build_tracks(cd)
        if tr is None:
            continue
        json.dump(tr, open(os.path.join(cd, "trajectories.json"), "w"),
                  indent=1, ensure_ascii=False)
        rel = os.path.relpath(cd, BASE)
        print(f"  ✅ {rel}: 트랙 {tr['num_tracks']}개"
              f"(이동 {tr['moving_tracks']}) ego {tr['ego']['avg_speed_mps']}m/s"
              f" 이동 {tr['ego']['displacement_m']}m")


if __name__ == "__main__":
    main()
