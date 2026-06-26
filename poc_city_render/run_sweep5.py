"""Cycle5 — 데이터효율 곡선. N=50/100/200/400에서 A(real만) vs C(합성pretrain→실FT).
합성으로 같은 mAP를 더 적은 실데이터로? = 실라벨 비용절감 정량화. mosaic=0, 기존 pretrain 재사용."""
import subprocess, csv, shutil, glob, os, random
random.seed(0)
RUNS = "/home/karma/OSMtoUSD/poc_city_render/runs"
YOLO = "/home/karma/OSMtoUSD/drone_det/venv/bin/yolo"
OUT = "cycle2_data"
B = "benchmarks/drones_yolo11_a"
DRONE = 3
AB = os.path.abspath(OUT)
PRE = f"{RUNS}/s4_pretrain/weights/best.pt"

def poly_boxes(lbl):
    out = []
    if os.path.exists(lbl):
        for l in open(lbl):
            p = l.split()
            if len(p) >= 7 and int(float(p[0])) == DRONE:
                xs = [float(v) for v in p[1::2]]; ys = [float(v) for v in p[2::2]]
                if max(xs) > min(xs) and max(ys) > min(ys):
                    out.append(((min(xs)+max(xs))/2, (min(ys)+max(ys))/2, max(xs)-min(xs), max(ys)-min(ys)))
    return out

train_drone = [i for i in sorted(glob.glob(f"{B}/train/images/*"))
               if poly_boxes(i.replace("/images/", "/labels/").rsplit(".", 1)[0]+".txt")]
random.shuffle(train_drone)
print(f"가용 실드론 train: {len(train_drone)}장", flush=True)

def build_real(N):
    sub = f"de_real{N}"; shutil.rmtree(f"{OUT}/{sub}", ignore_errors=True)
    os.makedirs(f"{OUT}/{sub}/images"); os.makedirs(f"{OUT}/{sub}/labels")
    for img in train_drone[:N]:
        bx = poly_boxes(img.replace("/images/", "/labels/").rsplit(".", 1)[0]+".txt")
        if bx:
            bn = os.path.basename(img); shutil.copy(img, f"{OUT}/{sub}/images/{bn}")
            open(f"{OUT}/{sub}/labels/"+bn.rsplit(".", 1)[0]+".txt", "w").write(
                "\n".join(f"0 {a:.6f} {b:.6f} {c:.6f} {d:.6f}" for a, b, c, d in bx))
    open(f"{OUT}/de_{N}.yaml", "w").write(f"path: {AB}\ntrain: {sub}/images\nval: test/images\nnc: 1\nnames: ['drone']\n")

def best(run):
    r = list(csv.DictReader(open(f"{RUNS}/{run}/results.csv")))
    return max(float(x["metrics/mAP50(B)"]) for x in r)

def train(name, model, yaml):
    shutil.rmtree(f"{RUNS}/{name}", ignore_errors=True)
    subprocess.run([YOLO, "detect", "train", f"model={model}", f"data={yaml}", "imgsz=640",
                    "batch=16", "epochs=120", "patience=30", "cache=False", "workers=6",
                    "device=0", "mosaic=0.0", "seed=0", f"project={RUNS}", f"name={name}", "exist_ok=True"],
                   stdout=open(f"de_{name}.log", "w"), stderr=subprocess.STDOUT)
    return best(name)

rows = []
for N in [50, 100, 200, 400]:
    build_real(N)
    a = train(f"de_A{N}", "yolo11s.pt", f"{OUT}/de_{N}.yaml")        # real만(COCO init)
    c = train(f"de_C{N}", PRE, f"{OUT}/de_{N}.yaml")                  # 합성pretrain→real FT
    rows.append((N, round(a, 4), round(c, 4), round(c-a, 4)))
    with open("sweep5_results.csv", "w") as f:
        f.write("N,A_realonly,C_synthpre+realFT,delta\n")
        for r in rows:
            f.write(",".join(map(str, r))+"\n")
    print(f"N={N}: A={a:.3f} C={c:.3f} delta={c-a:+.3f}", flush=True)
print("SWEEP5_DONE", flush=True)
