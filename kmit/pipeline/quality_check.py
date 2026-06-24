"""
데이터 품질 검증 (TODO 2-D)

output/scenario_*/<combo>/ 각 데이터셋을 스캔해 무결성·통계 리포트 생성:
  - 프레임 PNG 손상 여부 (PIL 로드)
  - 프레임 JSON 유효성 + 필수 키
  - 라벨 파일(seg/inst/depth) 누락 여부
  - 통계: 프레임 수·용량·bbox 클래스 분포·TTC 단계 분포

Usage:
    python3 pipeline/quality_check.py [output_dir]
"""
import os
import sys
import glob
import json
from collections import Counter
from PIL import Image

BASE = sys.argv[1] if len(sys.argv) > 1 else "/home/karma/OSMtoUSD/kmit/output"
REQUIRED_KEYS = {"frame", "ego", "bbox2d", "lidar_pts"}


def check_frame(json_path, labels_dir):
    """단일 프레임 검증 → (ok, 문제리스트, bbox클래스카운터)."""
    issues, classes = [], Counter()
    stem = os.path.basename(json_path)[:-5]  # frame_0000
    # JSON
    try:
        d = json.load(open(json_path))
        miss = REQUIRED_KEYS - set(d)
        if miss:
            issues.append(f"{stem}: 필수키 누락 {miss}")
        for cam, boxes in d.get("bbox2d", {}).items():
            for b in boxes:
                classes[b.get("label", "?")] += 1
    except Exception as e:
        issues.append(f"{stem}: JSON 손상 {e}")
        d = {}
    # 합성 PNG
    png = json_path[:-5] + ".png"
    if not os.path.exists(png):
        issues.append(f"{stem}: 합성 PNG 없음")
    else:
        try:
            Image.open(png).verify()
        except Exception as e:
            issues.append(f"{stem}: PNG 손상 {e}")
    # 라벨 파일
    if d.get("labels"):
        for kind in ("seg", "inst", "depth"):
            lp = os.path.join(labels_dir, f"{stem}_{kind}.png")
            if not os.path.exists(lp):
                issues.append(f"{stem}: 라벨 {kind} 없음")
    return (len(issues) == 0), issues, classes, d


def check_combo(combo_dir):
    frames = sorted(glob.glob(os.path.join(combo_dir, "frame_*.json")))
    labels_dir = os.path.join(combo_dir, "labels")
    rep = {"frames": len(frames), "ok": 0, "issues": [],
           "classes": Counter(), "ttc_phases": Counter(), "bytes": 0}
    for jp in frames:
        ok, issues, classes, d = check_frame(jp, labels_dir)
        rep["ok"] += int(ok)
        rep["issues"] += issues
        rep["classes"] += classes
        if "ttc" in d:
            rep["ttc_phases"][d["ttc"].get("phase", "?")] += 1
    # 용량 (라벨 포함)
    for f in glob.glob(os.path.join(combo_dir, "**", "*"), recursive=True):
        if os.path.isfile(f):
            rep["bytes"] += os.path.getsize(f)
    return rep


def main():
    combos = sorted(d for d in glob.glob(os.path.join(BASE, "scenario_*", "*"))
                    if os.path.isdir(d))
    print(f"=== 품질 검증: {len(combos)}개 데이터셋 ===\n")
    total_frames = total_issues = 0
    grand_classes = Counter()
    for cd in combos:
        rep = check_combo(cd)
        rel = os.path.relpath(cd, BASE)
        mb = rep["bytes"] / 1e6
        status = "✅" if not rep["issues"] else f"⚠️ {len(rep['issues'])}건"
        print(f"{status} {rel}: {rep['ok']}/{rep['frames']}프레임 {mb:.1f}MB "
              f"클래스={dict(rep['classes'])}"
              + (f" TTC={dict(rep['ttc_phases'])}" if rep["ttc_phases"] else ""))
        for iss in rep["issues"][:3]:
            print(f"     - {iss}")
        total_frames += rep["frames"]
        total_issues += len(rep["issues"])
        grand_classes += rep["classes"]
    print(f"\n=== 종합: {total_frames}프레임, 문제 {total_issues}건, "
          f"전체 클래스분포 {dict(grand_classes)} ===")
    sys.exit(1 if total_issues else 0)


if __name__ == "__main__":
    main()
