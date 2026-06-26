"""실벤치 단일클래스 'drone' AP 평가. 우리모델(quad/heli 등)→전부 drone 취급,
벤치 GT의 drone박스만 타겟. 클래스 불일치 우회 + 진짜 실mAP + 오탐/미탐 신호.
사용: python eval_bench.py <model.pt> <bench_dir> <tag>  (bench_dir엔 data.yaml + test|valid)"""
import sys, glob, os, yaml
import numpy as np
from ultralytics import YOLO

MODEL = sys.argv[1]
BENCH = sys.argv[2]
TAG = sys.argv[3] if len(sys.argv) > 3 else "model"
IMGSZ = int(sys.argv[4]) if len(sys.argv) > 4 else 1280

dy = yaml.safe_load(open(os.path.join(BENCH, "data.yaml")))
names = dy["names"]
if isinstance(names, dict):
    names = [names[k] for k in sorted(names, key=lambda x: int(x))]
drone_idx = {i for i, n in enumerate(names) if "drone" in str(n).lower()}
print(f"bench classes: {names} | drone idx: {drone_idx}", flush=True)

split = "test" if os.path.isdir(os.path.join(BENCH, "test/images")) else "valid"
imgs = sorted(glob.glob(f"{BENCH}/{split}/images/*"))
print(f"{split}: {len(imgs)} images", flush=True)

def load_gt(img):
    lf = img.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt"
    b = []
    if os.path.exists(lf):
        for l in open(lf):
            p = l.split()
            if len(p) >= 5 and int(float(p[0])) in drone_idx:
                xs = [float(v) for v in p[1::2]]; ys = [float(v) for v in p[2::2]]  # polygon→bbox
                b.append([min(xs), min(ys), max(xs), max(ys)])
    return np.array(b, dtype=np.float32).reshape(-1, 4)

def iou1(a, B):
    if len(B) == 0:
        return np.zeros(0, np.float32)
    x1 = np.maximum(a[0], B[:, 0]); y1 = np.maximum(a[1], B[:, 1])
    x2 = np.minimum(a[2], B[:, 2]); y2 = np.minimum(a[3], B[:, 3])
    inter = np.clip(x2-x1, 0, None)*np.clip(y2-y1, 0, None)
    aa = (a[2]-a[0])*(a[3]-a[1]); ab = (B[:, 2]-B[:, 0])*(B[:, 3]-B[:, 1])
    return inter/(aa+ab-inter+1e-9)

m = YOLO(MODEL)
res = m.predict(imgs, conf=0.001, imgsz=IMGSZ, verbose=False, stream=True)
records = []  # (conf, tp)
npos = 0
n_noT_fp = 0  # 드론 없는 이미지에서의 오탐 박스 수(confuser 오탐 신호)
for img, r in zip(imgs, res):
    gt = load_gt(img); npos += len(gt)
    if r.boxes is None or len(r.boxes) == 0:
        continue
    pb = r.boxes.xyxyn.cpu().numpy(); pc = r.boxes.conf.cpu().numpy()
    order = np.argsort(-pc); matched = np.zeros(len(gt), bool)
    for i in order:
        ious = iou1(pb[i], gt)
        if len(ious) and ious.max() >= 0.5 and not matched[ious.argmax()]:
            matched[ious.argmax()] = True; records.append((float(pc[i]), 1))
        else:
            records.append((float(pc[i]), 0))
            if len(gt) == 0 and pc[i] >= 0.25:
                n_noT_fp += 1

records.sort(key=lambda x: -x[0])
tp = np.cumsum([r[1] for r in records]); fp = np.cumsum([1-r[1] for r in records])
rec = tp/(npos+1e-9); prec = tp/(tp+fp+1e-9)
ap = sum((prec[rec >= t].max() if (rec >= t).any() else 0) for t in np.linspace(0, 1, 101))/101
hi = [r for r in records if r[0] >= 0.25]
tp25 = sum(r[1] for r in hi)
print(f"=== [{TAG}] REAL bench (단일클래스 drone, IoU0.5) ===", flush=True)
print(f"  GT drones={npos} | total preds={len(records)}", flush=True)
print(f"  >>> AP50 = {ap:.4f} <<<", flush=True)
print(f"  @conf0.25: recall={tp25/(npos+1e-9):.3f} precision={tp25/(len(hi)+1e-9):.3f} preds={len(hi)}", flush=True)
print(f"  드론없는 이미지 오탐박스(@0.25): {n_noT_fp} (confuser 오탐 신호)", flush=True)
