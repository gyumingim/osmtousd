"""Cycle2 scarce-real 실험 데이터 준비 (CPU). 단일클래스 'drone'.
- test: 벤치 test 중 drone 있는 이미지 (drone-only label)
- real_N: 벤치 train 중 drone 있는 N장 (scarce 실데이터)
- synth: 우리 합성 dataset_pose → 탐지label(class0, keypoint 제거)
A=real_N only / B=real_N + synth → 합성이 scarce real 보강하나 검증.
PDF: 합성 사전학습/벌크 + 실 소량 fine-tune."""
import glob, os, shutil, random
random.seed(0)
B = "benchmarks/drones_yolo11_a"
OUT = "cycle2_data"
DRONE = 3  # 벤치 drone 클래스 idx
N_REAL = 200

def drone_only_label(src_lbl, dst_lbl):
    lines = []
    if os.path.exists(src_lbl):
        for l in open(src_lbl):
            p = l.split()
            if len(p) >= 5 and int(p[0]) == DRONE:
                lines.append("0 " + " ".join(p[1:5]))   # class0=drone
    open(dst_lbl, "w").write("\n".join(lines))
    return len(lines)

def build_real(split, names_imgs, sub):
    """drone 있는 이미지만 골라 drone-only로 복사."""
    os.makedirs(f"{OUT}/{sub}/images", exist_ok=True); os.makedirs(f"{OUT}/{sub}/labels", exist_ok=True)
    n = 0
    for img in names_imgs:
        lf = img.replace("/images/", "/labels/").rsplit(".", 1)[0]+".txt"
        if os.path.exists(lf) and any(l.split() and l.split()[0] == str(DRONE) for l in open(lf)):
            bn = os.path.basename(img)
            shutil.copy(img, f"{OUT}/{sub}/images/{bn}")
            drone_only_label(lf, f"{OUT}/{sub}/labels/"+bn.rsplit(".", 1)[0]+".txt")
            n += 1
    return n

# test (drone 있는 것 전부)
ntest = build_real("test", sorted(glob.glob(f"{B}/test/images/*")), "test")
# real_N (drone 있는 train에서 N장)
train_drone = [i for i in sorted(glob.glob(f"{B}/train/images/*"))
               if os.path.exists(i.replace("/images/", "/labels/").rsplit(".", 1)[0]+".txt")
               and any(l.split() and l.split()[0] == str(DRONE) for l in open(i.replace("/images/", "/labels/").rsplit(".", 1)[0]+".txt"))]
random.shuffle(train_drone)
nreal = build_real("train", train_drone[:N_REAL], f"real{N_REAL}")
# synth (dataset_pose → 탐지 단일클래스)
os.makedirs(f"{OUT}/synth/images", exist_ok=True); os.makedirs(f"{OUT}/synth/labels", exist_ok=True)
nsyn = 0
for img in glob.glob("dataset_pose/images/train/*.png"):
    lf = "dataset_pose/labels/train/"+os.path.basename(img).replace(".png", ".txt")
    bn = os.path.basename(img)
    out_l = []
    if os.path.exists(lf):
        for l in open(lf):
            p = l.split()
            if len(p) >= 5:
                out_l.append("0 " + " ".join(p[1:5]))   # 박스만, class0
    if out_l:  # 드론 있는 합성프레임만
        shutil.copy(img, f"{OUT}/synth/images/{bn}")
        open(f"{OUT}/synth/labels/"+bn.replace(".png", ".txt"), "w").write("\n".join(out_l)); nsyn += 1

AB = os.path.abspath(OUT)
open(f"{OUT}/data_A.yaml", "w").write(f"path: {AB}\ntrain: real{N_REAL}/images\nval: test/images\nnc: 1\nnames: ['drone']\n")
open(f"{OUT}/data_B.yaml", "w").write(f"path: {AB}\ntrain:\n  - real{N_REAL}/images\n  - synth/images\nval: test/images\nnc: 1\nnames: ['drone']\n")
print(f"test={ntest}장 | real{N_REAL}={nreal}장 | synth={nsyn}장")
print(f"A(real only)={nreal} / B(real+synth)={nreal+nsyn}  → data_A.yaml, data_B.yaml")
