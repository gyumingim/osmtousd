"""
데이터셋 패키징 (TODO 2-C / 공통 인프라 데이터 표준화)

output/scenario_*/<combo>/ → packages/<scenario>_<combo>.zip 표준 구조:
    data/     합성 프레임 PNG
    labels/   프레임 JSON + 세그/인스턴스/깊이 PNG
    meta/     metadata.json (시나리오·환경·통계) + README.md

Usage:
    python3 pipeline/packager.py [output_dir] [packages_dir]
"""
import os
import sys
import glob
import json
import zipfile
from collections import Counter

BASE = sys.argv[1] if len(sys.argv) > 1 else "/home/karma/OSMtoUSD/output"
PKG_DIR = sys.argv[2] if len(sys.argv) > 2 else "/home/karma/OSMtoUSD/packages"

SCENARIO_NAMES = {
    "scenario_01": "극한 기상 자율주행",
    "scenario_02": "산단 AMR 물류",
    "scenario_03": "보행자·이륜차 VRU",
    "scenario_04": "V2X 협력주행",
    "scenario_05": "사고·충돌",
}


def build_metadata(combo_dir, scenario, combo):
    frames = sorted(glob.glob(os.path.join(combo_dir, "frame_*.json")))
    classes, ttc = Counter(), Counter()
    env = {}
    for jp in frames:
        d = json.load(open(jp))
        env = d.get("environment", env)
        for boxes in d.get("bbox2d", {}).values():
            for b in boxes:
                classes[b.get("label", "?")] += 1
        if "ttc" in d:
            ttc[d["ttc"].get("phase", "?")] += 1
    return {
        "scenario": scenario,
        "scenario_name": SCENARIO_NAMES.get(scenario, scenario),
        "variant": combo,
        "environment": env,
        "frame_count": len(frames),
        "sensors": ["camera_x4", "lidar", "radar", "ultrasonic",
                    "proximity_raycast"],
        "labels": ["bbox2d", "bbox3d", "semantic_seg", "instance_seg",
                   "depth", "lidar_pcd", "radar_csv", "ultrasonic_csv"],
        "class_distribution": dict(classes),
        "ttc_phases": dict(ttc) if ttc else None,
        "source": "Synthetic (Isaac Sim / 구미 1산단 디지털트윈)",
    }


def make_readme(meta):
    lines = [
        f"# {meta['scenario_name']} — {meta['variant']}",
        "",
        f"- 데이터 유형: **Synthetic** (합성)",
        f"- 시나리오: {meta['scenario']} ({meta['scenario_name']})",
        f"- 환경: {meta['environment']}",
        f"- 프레임 수: {meta['frame_count']}",
        f"- 센서: {', '.join(meta['sensors'])}",
        f"- 라벨: {', '.join(meta['labels'])}",
        f"- 클래스 분포: {meta['class_distribution']}",
        "",
        "## 구조",
        "- `data/` 합성 프레임 PNG (멀티센서 + 라벨 시각화)",
        "- `labels/` 프레임 JSON(bbox2d/3d·ego·궤적·TTC) + 세그/깊이 PNG",
        "- `meta/metadata.json` 데이터셋 스펙",
    ]
    return "\n".join(lines)


def package_combo(combo_dir):
    parts = combo_dir.rstrip("/").split(os.sep)
    scenario, combo = parts[-2], parts[-1]
    meta = build_metadata(combo_dir, scenario, combo)
    if meta["frame_count"] == 0:           # 빈 폴더(렌더 실패) → 기존 zip 보존
        return None, 0, 0
    os.makedirs(PKG_DIR, exist_ok=True)
    zip_path = os.path.join(PKG_DIR, f"{scenario}_{combo}.zip")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        # data/ ← 합성 프레임 PNG, cinematic/ ← 체이스캠 영상
        for png in sorted(glob.glob(os.path.join(combo_dir, "frame_*.png"))):
            bn = os.path.basename(png)
            if bn.startswith("frame_view_"):
                z.write(png, f"cinematic/{bn}")
            else:
                z.write(png, f"data/{bn}")
        # labels/ ← 프레임 JSON/YAML + 세그/깊이/인스턴스/pcd/csv
        for jp in sorted(glob.glob(os.path.join(combo_dir, "frame_*.json"))):
            z.write(jp, f"labels/{os.path.basename(jp)}")
        for yp in sorted(glob.glob(os.path.join(combo_dir, "frame_*.yaml"))):
            z.write(yp, f"labels/{os.path.basename(yp)}")
        for lp in sorted(glob.glob(os.path.join(combo_dir, "labels", "*"))):
            z.write(lp, f"labels/{os.path.basename(lp)}")
        # V2X 로그가 있으면 포함
        v2x = os.path.join(combo_dir, "v2x_log.json")
        if os.path.exists(v2x):
            z.write(v2x, "labels/v2x_log.json")
        # 센서 캘리브레이션 포함
        calib = os.path.join(combo_dir, "calibration.json")
        if os.path.exists(calib):
            z.write(calib, "meta/calibration.json")
        # 궤적 라벨 포함
        traj = os.path.join(combo_dir, "trajectories.json")
        if os.path.exists(traj):
            z.write(traj, "labels/trajectories.json")
        # meta/
        z.writestr("meta/metadata.json",
                   json.dumps(meta, indent=2, ensure_ascii=False))
        z.writestr("README.md", make_readme(meta))
    return zip_path, meta["frame_count"], os.path.getsize(zip_path)


def main():
    combos = sorted(d for d in glob.glob(os.path.join(BASE, "scenario_*", "*"))
                    if os.path.isdir(d))
    print(f"=== 패키징: {len(combos)}개 데이터셋 → {PKG_DIR} ===\n")
    total = made = 0
    for cd in combos:
        zp, n, sz = package_combo(cd)
        if zp is None:
            print(f"  ⏭️  {os.path.basename(cd.rstrip('/'))}: 빈 폴더 — 스킵(기존 보존)")
            continue
        print(f"  ✅ {os.path.basename(zp)}: {n}프레임 {sz/1e6:.1f}MB")
        total += sz
        made += 1
    print(f"\n=== 완료: {made}개 ZIP, 총 {total/1e6:.1f}MB ===")


if __name__ == "__main__":
    main()
