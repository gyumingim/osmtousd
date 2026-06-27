"""B1 실배경 합성 (Cut-Paste, Dwibedi'17): 합성드론을 실배경에 붙임 → 배경 단조 갭 해소.
드론 컷아웃: 합성 sky배경 프레임서 하늘색 빼서 마스크. 배경: dvb-train 드론없는 실외(test와 분리).
출력: cycle2_data/synth_composite/ (실배경 + 합성드론, YOLO box). val=dvb test3."""
import glob, os, json, cv2, numpy as np, random, sys
random.seed(0)
OUT = "cycle2_data/synth_composite"
N_OUT = int(sys.argv[1]) if len(sys.argv) > 1 else 450

# 1) 합성 sky배경 드론 프레임 → 컷아웃(RGBA)
cutouts = []
for jf in glob.glob("dataset_v1/sequences/*.json"):
    d = json.load(open(jf))
    if d.get("background") != "sky":   # 하늘배경만(깨끗한 마스크)
        continue
    for fr in d["frames"]:
        bb = fr.get("bbox_xywh_norm"); px = fr.get("px", 0)
        if not bb or px < 45:           # 충분히 큰 것만(컷아웃 깨끗)
            continue
        img = cv2.imread("dataset_v1/images/" + fr["file"])
        if img is None: continue
        H, W = img.shape[:2]
        cx, cy, w, h = bb
        x1 = max(0, int((cx-w/2)*W)-4); y1 = max(0, int((cy-h/2)*H)-4)
        x2 = min(W, int((cx+w/2)*W)+4); y2 = min(H, int((cy+h/2)*H)+4)
        crop = img[y1:y2, x1:x2]
        if crop.size == 0 or crop.shape[0] < 8 or crop.shape[1] < 8: continue
        # 하늘색 = 테두리 픽셀 중앙값, 드론 = 거기서 먼 픽셀
        bd = np.concatenate([crop[0], crop[-1], crop[:, 0], crop[:, -1]])
        sky = np.median(bd, axis=0)
        dist = np.linalg.norm(crop.astype(float) - sky, axis=2)
        mask = (dist > 28).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        if mask.sum() < 30: continue
        rgba = np.dstack([crop, mask*255])
        cutouts.append(rgba)
print(f"드론 컷아웃 {len(cutouts)}개 추출", flush=True)

bgs = []
for lf in glob.glob("benchmarks/dvb/train/labels/*.txt"):
    if '1' not in set(l.split()[0] for l in open(lf) if l.split()):
        ip = lf.replace("/labels/", "/images/").rsplit(".", 1)[0]
        for e in (".jpg", ".png", ".jpeg"):
            if os.path.exists(ip+e): bgs.append(ip+e); break
print(f"실배경 {len(bgs)}장", flush=True)

os.makedirs(f"{OUT}/images", exist_ok=True); os.makedirs(f"{OUT}/labels", exist_ok=True)
for i in range(N_OUT):
    bg = cv2.imread(random.choice(bgs))
    if bg is None: continue
    H, W = bg.shape[:2]
    rows = []
    for _ in range(random.randint(1, 3)):
        co = random.choice(cutouts); ch, cw = co.shape[:2]
        tgt = random.randint(20, 130)                       # dvb 작은드론 스케일
        sc = tgt/max(ch, cw); nw, nh = max(6, int(cw*sc)), max(6, int(ch*sc))
        co2 = cv2.resize(co, (nw, nh))
        px = random.randint(0, max(1, W-nw)); py = random.randint(0, max(1, H-nh))
        roi = bg[py:py+nh, px:px+nw]
        if roi.shape[:2] != (nh, nw): continue
        a = (co2[:, :, 3:4].astype(float)/255.0)
        bg[py:py+nh, px:px+nw] = (co2[:, :, :3]*a + roi*(1-a)).astype(np.uint8)
        rows.append(f"0 {(px+nw/2)/W:.6f} {(py+nh/2)/H:.6f} {nw/W:.6f} {nh/H:.6f}")
    if rows:
        cv2.imwrite(f"{OUT}/images/c{i:04d}.jpg", bg)
        open(f"{OUT}/labels/c{i:04d}.txt", "w").write("\n".join(rows))
n = len(glob.glob(f"{OUT}/images/*.jpg"))
AB = os.path.abspath("cycle2_data")
open("cycle2_data/d_composite.yaml", "w").write(
    f"path: {AB}\ntrain: synth_composite/images\nval: test3/images\nnc: 1\nnames: ['drone']\n")
print(f"합성완료 {n}장 → {OUT}", flush=True)
