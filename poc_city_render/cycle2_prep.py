"""Cycle2 scarce-real 실험 데이터 (CPU). 단일클래스 'drone'.
⚠️ 벤치 라벨은 POLYGON(분할) 포맷 → bbox로 변환(min/max). 합성(dataset_pose)은 box포맷.
A=real_N only / B=real_N + synth → 합성이 scarce real 보강하나(PDF 합성벌크+실fine-tune 검증)."""
import glob, os, shutil, random
random.seed(0)
B = "benchmarks/drones_yolo11_a"
OUT = "cycle2_data"
DRONE = 3
N_REAL = 200

def poly_to_drone_boxes(lbl):
    """벤치 polygon 라벨 → drone(class3) 박스들 [cx,cy,w,h]."""
    out = []
    if os.path.exists(lbl):
        for l in open(lbl):
            p = l.split()
            if len(p) >= 7 and int(float(p[0])) == DRONE:   # class + 폴리곤(≥3점)
                xs = [float(v) for v in p[1::2]]; ys = [float(v) for v in p[2::2]]
                x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
                if x1 > x0 and y1 > y0:
                    out.append(((x0+x1)/2, (y0+y1)/2, x1-x0, y1-y0))
    return out

def has_drone(lbl):
    return os.path.exists(lbl) and any(s.split() and int(float(s.split()[0])) == DRONE for s in open(lbl))

def build(imgs, sub):
    os.makedirs(f"{OUT}/{sub}/images", exist_ok=True); os.makedirs(f"{OUT}/{sub}/labels", exist_ok=True)
    n = nb = 0
    for img in imgs:
        lf = img.replace("/images/", "/labels/").rsplit(".", 1)[0]+".txt"
        boxes = poly_to_drone_boxes(lf)
        if boxes:
            bn = os.path.basename(img); shutil.copy(img, f"{OUT}/{sub}/images/{bn}")
            open(f"{OUT}/{sub}/labels/"+bn.rsplit(".", 1)[0]+".txt", "w").write(
                "\n".join(f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for cx, cy, w, h in boxes))
            n += 1; nb += len(boxes)
    return n, nb

ntest, ntb = build(sorted(glob.glob(f"{B}/test/images/*")), "test")
train_drone = [i for i in sorted(glob.glob(f"{B}/train/images/*"))
               if has_drone(i.replace("/images/", "/labels/").rsplit(".", 1)[0]+".txt")]
random.shuffle(train_drone)
nreal, nrb = build(train_drone[:N_REAL], f"real{N_REAL}")

# 합성(dataset_pose) → 탐지 단일클래스 (이미 box포맷, keypoint만 제거)
os.makedirs(f"{OUT}/synth/images", exist_ok=True); os.makedirs(f"{OUT}/synth/labels", exist_ok=True)
nsyn = 0
for img in glob.glob("dataset_pose/images/train/*.png"):
    lf = "dataset_pose/labels/train/"+os.path.basename(img).replace(".png", ".txt")
    rows = []
    if os.path.exists(lf):
        for l in open(lf):
            p = l.split()
            if len(p) >= 5:
                rows.append("0 " + " ".join(p[1:5]))
    if rows:
        bn = os.path.basename(img); shutil.copy(img, f"{OUT}/synth/images/{bn}")
        open(f"{OUT}/synth/labels/"+bn.replace(".png", ".txt"), "w").write("\n".join(rows)); nsyn += 1

AB = os.path.abspath(OUT)
open(f"{OUT}/data_A.yaml", "w").write(f"path: {AB}\ntrain: real{N_REAL}/images\nval: test/images\nnc: 1\nnames: ['drone']\n")
open(f"{OUT}/data_B.yaml", "w").write(f"path: {AB}\ntrain:\n  - real{N_REAL}/images\n  - synth/images\nval: test/images\nnc: 1\nnames: ['drone']\n")
print(f"test={ntest}장({ntb}박스) | real{N_REAL}={nreal}장({nrb}박스) | synth={nsyn}장")
print(f"A={nreal} / B={nreal+nsyn}")
