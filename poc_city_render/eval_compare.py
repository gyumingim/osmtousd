"""모델 평가+비교: 합성 val mAP(GT) + 실사진 9장 추론(정성).
사용: venv/bin/python eval_compare.py <model.pt> <tag>"""
import sys, glob, os, math
import numpy as np
from ultralytics import YOLO
from PIL import Image, ImageDraw

MODEL = sys.argv[1] if len(sys.argv) > 1 else "runs/pose_1280s/weights/best.pt"
TAG = sys.argv[2] if len(sys.argv) > 2 else "1280s"
DS = "/home/karma/OSMtoUSD/poc_city_render/dataset_pose/data.yaml"
REAL = "/home/karma/OSMtoUSD/poc_city_render/realtest/images"
m = YOLO(MODEL)

# 1) 합성 val 정량(GT 있음)
print(f"=== [{TAG}] 합성 val mAP ===")
mt = m.val(data=DS, imgsz=1280, verbose=False, plots=False)
print(f"  box  mAP50={mt.box.map50:.3f}  mAP50-95={mt.box.map:.3f}  P={mt.box.mp:.3f} R={mt.box.mr:.3f}")
try:
    print(f"  pose mAP50={mt.pose.map50:.3f}  mAP50-95={mt.pose.map:.3f}")
except Exception:
    print("  pose: N/A")

# 2) 실사진 정성(GT 없음 → 탐지율+신뢰도+육안)
imgs = sorted(glob.glob(REAL+"/*.jpg"))
res = m.predict(imgs, conf=0.10, imgsz=1280, verbose=False)
T = 320; cols = 3; rows = math.ceil(len(imgs)/cols); sh = Image.new("RGB", (cols*T, rows*T), (15, 15, 15))
hit = 0; confs = []
for i, (fp, r) in enumerate(zip(imgs, res)):
    im = Image.open(fp).convert("RGB"); W0, H0 = im.size; im = im.resize((T, T)); d = ImageDraw.Draw(im)
    n = len(r.boxes); hit += (n > 0)
    for b in r.boxes:
        x0, y0, x1, y1 = b.xyxy[0].tolist(); c = float(b.conf[0]); confs.append(c)
        sx, sy = T/W0, T/H0
        d.rectangle([x0*sx, y0*sy, x1*sx, y1*sy], outline=(255, 30, 30), width=3)
        d.text((x0*sx, max(0, y0*sy-10)), f"{c:.2f}", fill=(255, 255, 0))
    d.text((4, 4), f"{os.path.basename(fp)} n={n}", fill=(0, 255, 255))
    sh.paste(im, ((i % cols)*T, (i//cols)*T))
out = f"/home/karma/OSMtoUSD/poc_city_render/realtest_{TAG}.png"; sh.save(out)
print(f"=== [{TAG}] 실사진 ===")
print(f"  9장중 탐지 {hit}장 | 총박스 {len(confs)} | conf {sorted([round(c,2) for c in confs],reverse=True)[:10]}")
print(f"  평균conf {np.mean(confs):.2f}" if confs else "  탐지0")
print(f"  → {out}")
