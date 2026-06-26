"""eval.py — 크기(=거리 대리)별 성능 분해 진단. 방법론 루프의 '②진단' 도구.

표준 mAP 외에, GT 박스를 크기 구간으로 나눠 recall을 잰다.
→ "어느 크기(거리)에서 놓치나"를 정량화 → AI-2에 줄 'sim 생성 주문'의 근거.
GPU 필요(추론). GPU 비면 실행:  venv/bin/python eval.py
"""
import os
import glob
import numpy as np
from ultralytics import YOLO

ROOT = os.path.dirname(os.path.abspath(__file__))
WEIGHTS = os.path.join(ROOT, "runs", "drone_y11n", "weights", "best.pt")
VAL_IMG = os.path.join(ROOT, "data", "images", "val")
VAL_LBL = os.path.join(ROOT, "data", "labels", "val")
BUCKETS = [(0, 16, "<16px"), (16, 32, "16~32px"),
           (32, 64, "32~64px"), (64, 1e9, "≥64px")]


def _iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    ua = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / ua if ua > 0 else 0


def main():
    if not os.path.exists(WEIGHTS):
        raise SystemExit(f"가중치 없음: {WEIGHTS} (train.py 먼저)")
    model = YOLO(WEIGHTS)
    # 표준 mAP
    m = model.val(data=os.path.join(ROOT, "data", "data.yaml"), verbose=False)
    print(f"=== 전체 ===  mAP50 {m.box.map50:.3f} · mAP50-95 {m.box.map:.3f}"
          f" · P {m.box.mp:.3f} · R {m.box.mr:.3f}\n")

    # 크기별 recall (GT를 예측과 IoU>0.5 매칭)
    hit = {b[2]: 0 for b in BUCKETS}
    tot = {b[2]: 0 for b in BUCKETS}
    for img in sorted(glob.glob(os.path.join(VAL_IMG, "*.jpg"))):
        lf = os.path.join(VAL_LBL, os.path.basename(img)[:-4] + ".txt")
        if not os.path.exists(lf):
            continue
        r = model.predict(img, conf=0.25, verbose=False)[0]
        H, W = r.orig_shape
        preds = [list(map(float, b)) for b in r.boxes.xyxy.cpu().numpy()] \
            if r.boxes is not None else []
        for line in open(lf):
            p = line.split()
            if len(p) != 5:
                continue
            xc, yc, wn, hn = map(float, p[1:])
            gx1, gy1 = (xc-wn/2)*W, (yc-hn/2)*H
            gx2, gy2 = (xc+wn/2)*W, (yc+hn/2)*H
            minpx = min(wn*W, hn*H)
            name = next(b[2] for b in BUCKETS if b[0] <= minpx < b[1])
            tot[name] += 1
            if any(_iou([gx1, gy1, gx2, gy2], pr) > 0.5 for pr in preds):
                hit[name] += 1

    print("=== 크기별 recall (어디서 놓치나) ===")
    for _, _, name in BUCKETS:
        t = tot[name]
        rec = hit[name] / t if t else 0
        print(f"  {name:9}: recall {rec:.3f}  ({hit[name]}/{t})")
    print("\n→ recall 낮은 구간 = AI-2에 'sim 그 거리 더 생성' 주문 근거")


if __name__ == "__main__":
    main()
