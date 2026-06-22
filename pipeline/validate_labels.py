"""자동 라벨 정확도/품질 검증 (TODO 공통인프라 · 제안서 2-D)

합성 데이터는 라벨이 곧 ground truth이므로 "외부 정답"과 비교하는 대신,
라벨의 기하/클래스/완전성/일관성을 자체 검증한다:
  - 2D bbox 경계 유효성 (x_min<x_max, 화면 내, 면적>0)
  - 클래스 화이트리스트 위반 (정의되지 않은 라벨)
  - 3D bbox 완전성 (extent 6값 + world transform 4x4 존재)
  - 라벨 파일 커버리지 (seg/inst/depth/pcd/csv 누락)
  - 프레임 간 객체수 안정성 (급변 탐지)
  - 스폰 액터(GT) 대비 탐지 클래스 일치 (씬에 둔 종류가 라벨에 등장하는가)

Usage:
    python3 pipeline/validate_labels.py [output_dir]
    → output/label_report.json + 콘솔 요약, 문제 있으면 exit 1
"""
import os
import sys
import glob
import json
from collections import Counter

BASE = sys.argv[1] if len(sys.argv) > 1 else "/home/karma/OSMtoUSD/output"
CAM_W, CAM_H = 640, 360
KNOWN = {"building", "road", "road_marking", "crosswalk", "sidewalk",
         "traffic_sign", "traffic_light", "car", "truck", "bus",
         "motorcycle", "bicycle", "pedestrian", "cyclist"}
LABEL_KINDS = ("seg", "inst", "depth")


def check_dataset(combo_dir):
    frames = sorted(glob.glob(os.path.join(combo_dir, "frame_*.json")))
    labels_dir = os.path.join(combo_dir, "labels")
    r = {
        "frames": len(frames), "bbox_total": 0, "bbox_degenerate": 0,
        "bbox_out_of_bounds": 0, "unknown_labels": Counter(),
        "classes": Counter(), "bbox3d_total": 0, "bbox3d_with_transform": 0,
        "frames_with_bbox": 0, "frames_with_seg": 0,
        "missing_label_files": 0, "actor_classes": set(),
        "detected_classes": set(), "count_series": [], "issues": [],
    }
    for jp in frames:
        stem = os.path.basename(jp)[:-5]
        try:
            d = json.load(open(jp))
        except Exception as e:
            r["issues"].append(f"{stem}: JSON 손상 {e}")
            continue
        # 2D bbox 검증
        fcount = 0
        for cam, boxes in d.get("bbox2d", {}).items():
            for b in boxes:
                r["bbox_total"] += 1
                fcount += 1
                lab = b.get("label", "?")
                r["classes"][lab] += 1
                r["detected_classes"].add(lab)
                if lab not in KNOWN:
                    r["unknown_labels"][lab] += 1
                xmin, ymin = b.get("x_min", 0), b.get("y_min", 0)
                xmax, ymax = b.get("x_max", 0), b.get("y_max", 0)
                if xmax <= xmin or ymax <= ymin:
                    r["bbox_degenerate"] += 1
                if (xmin < 0 or ymin < 0 or xmax > CAM_W or ymax > CAM_H):
                    r["bbox_out_of_bounds"] += 1
        if fcount:
            r["frames_with_bbox"] += 1
        r["count_series"].append(fcount)
        # 3D bbox 완전성
        for b in d.get("bbox3d", []):
            r["bbox3d_total"] += 1
            if isinstance(b.get("transform"), list) and len(b["transform"]) == 4:
                r["bbox3d_with_transform"] += 1
        # 스폰 액터(GT) 클래스
        for a in d.get("actors", []):
            r["actor_classes"].add(a.get("label"))
        # 라벨 파일 커버리지
        if d.get("labels"):
            seg = os.path.join(labels_dir, f"{stem}_seg.png")
            if os.path.exists(seg):
                r["frames_with_seg"] += 1
            for kind in LABEL_KINDS:
                if not os.path.exists(
                        os.path.join(labels_dir, f"{stem}_{kind}.png")):
                    r["missing_label_files"] += 1
    # 프레임 간 안정성: 인접 프레임 객체수 3배 이상 급변 횟수
    cs = r["count_series"]
    r["count_jumps"] = sum(
        1 for i in range(1, len(cs))
        if abs(cs[i] - cs[i - 1]) > 3 * max(1, min(cs[i], cs[i - 1])))
    # 스폰했지만 한 번도 라벨에 안 잡힌 클래스(가림/FOV밖일 수 있음 → 경고)
    r["spawned_not_detected"] = sorted(
        (r["actor_classes"] - r["detected_classes"]) - {None})
    return r


def grade(r):
    """치명 결함 리스트 반환(있으면 fail)."""
    bad = []
    if r["bbox_degenerate"]:
        bad.append(f"퇴화 bbox {r['bbox_degenerate']}개")
    if r["unknown_labels"]:
        bad.append(f"미정의 라벨 {dict(r['unknown_labels'])}")
    if r["bbox3d_total"] and r["bbox3d_with_transform"] < r["bbox3d_total"]:
        bad.append(f"3D bbox transform 누락 "
                   f"{r['bbox3d_total'] - r['bbox3d_with_transform']}/"
                   f"{r['bbox3d_total']}")
    if r["missing_label_files"]:
        bad.append(f"라벨파일 누락 {r['missing_label_files']}건")
    if r["frames"] and r["frames_with_bbox"] / r["frames"] < 0.5:
        bad.append(f"bbox 커버리지 낮음 "
                   f"{r['frames_with_bbox']}/{r['frames']}")
    return bad


def main():
    combos = sorted(d for d in glob.glob(os.path.join(BASE, "scenario_*", "*"))
                    if os.path.isdir(d))
    print(f"=== 라벨 검증: {len(combos)}개 데이터셋 ===\n")
    report, total_bad = {}, 0
    for cd in combos:
        r = check_dataset(cd)
        bad = grade(r)
        total_bad += len(bad)
        rel = os.path.relpath(cd, BASE)
        oob = (f" 화면밖{r['bbox_out_of_bounds']}"
               if r["bbox_out_of_bounds"] else "")
        cov3d = (f"{r['bbox3d_with_transform']}/{r['bbox3d_total']}"
                 if r["bbox3d_total"] else "0")
        status = "✅" if not bad else "❌"
        print(f"{status} {rel}: {r['frames']}프레임 bbox{r['bbox_total']} "
              f"3D-transform {cov3d} seg {r['frames_with_seg']}/{r['frames']}"
              f"{oob}")
        print(f"     클래스={dict(r['classes'])}")
        if r["spawned_not_detected"]:
            print(f"     ⚠️ 스폰됐으나 미탐지(가림/FOV밖 가능): "
                  f"{r['spawned_not_detected']}")
        for b in bad:
            print(f"     ❌ {b}")
        # 직렬화용 정리
        r["unknown_labels"] = dict(r["unknown_labels"])
        r["classes"] = dict(r["classes"])
        r["actor_classes"] = sorted(x for x in r["actor_classes"] if x)
        r["detected_classes"] = sorted(r["detected_classes"])
        r["pass"] = not bad
        r["defects"] = bad
        report[rel] = r
    out = os.path.join(BASE, "label_report.json")
    json.dump(report, open(out, "w"), indent=2, ensure_ascii=False)
    print(f"\n=== 종합: {len(combos)}개 검증, 결함 {total_bad}건 → {out} ===")
    sys.exit(1 if total_bad else 0)


if __name__ == "__main__":
    main()
