"""토큰 무관 로컬 러너 — scarce-real 스윕. 합성이 '실데이터 적을수록' 도움되나 검증.
각 N(실데이터 장수)마다: A=real_N only vs B=real_N+합성359 → test mAP 비교.
결과 sweep_results.csv에 증분 기록. 4060 순차(Isaac 동시 금지 전제). setsid로 detach해 토큰 끊겨도 계속."""
import subprocess, glob, os, shutil, random, csv
random.seed(0)
B = "benchmarks/drones_yolo11_a"
OUT = "cycle2_data"
DRONE = 3
YOLO = "/home/karma/OSMtoUSD/drone_det/venv/bin/yolo"
SIZES = [25, 50, 100, 200]

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

def build_real(imgs, sub):
    shutil.rmtree(f"{OUT}/{sub}", ignore_errors=True)
    os.makedirs(f"{OUT}/{sub}/images"); os.makedirs(f"{OUT}/{sub}/labels")
    for img in imgs:
        bx = poly_boxes(img.replace("/images/", "/labels/").rsplit(".", 1)[0]+".txt")
        if bx:
            bn = os.path.basename(img); shutil.copy(img, f"{OUT}/{sub}/images/{bn}")
            open(f"{OUT}/{sub}/labels/"+bn.rsplit(".", 1)[0]+".txt", "w").write(
                "\n".join(f"0 {a:.6f} {b:.6f} {c:.6f} {d:.6f}" for a, b, c, d in bx))

RUNS = "/home/karma/OSMtoUSD/poc_city_render/runs"

def best(run):
    r = list(csv.DictReader(open(f"{RUNS}/{run}/results.csv")))
    return max(float(x["metrics/mAP50(B)"]) for x in r)

def train(name, yaml):
    shutil.rmtree(f"{RUNS}/{name}", ignore_errors=True)
    subprocess.run([YOLO, "detect", "train", "model=yolo11s.pt", f"data={yaml}",
                    "imgsz=640", "batch=16", "epochs=100", "patience=25", "cache=False",
                    "workers=6", "device=0", f"project={RUNS}", f"name={name}", "exist_ok=True"],
                   stdout=open(f"sweep_{name}.log", "w"), stderr=subprocess.STDOUT)
    return best(name)

AB = os.path.abspath(OUT)
rows = []
for N in SIZES:
    build_real(train_drone[:N], f"real{N}")
    open(f"{OUT}/dA_{N}.yaml", "w").write(f"path: {AB}\ntrain: real{N}/images\nval: test/images\nnc: 1\nnames: ['drone']\n")
    open(f"{OUT}/dB_{N}.yaml", "w").write(f"path: {AB}\ntrain:\n  - real{N}/images\n  - synth/images\nval: test/images\nnc: 1\nnames: ['drone']\n")
    a = train(f"sw_A{N}", f"{OUT}/dA_{N}.yaml")
    b = train(f"sw_B{N}", f"{OUT}/dB_{N}.yaml")
    rows.append((N, round(a, 4), round(b, 4), round(b-a, 4)))
    with open("sweep_results.csv", "w") as f:
        f.write("real_N,A_realonly,B_real+synth,delta\n")
        for r in rows:
            f.write(",".join(map(str, r))+"\n")
    print(f"N={N}: A(real)={a:.3f} B(real+synth)={b:.3f} delta={b-a:+.3f}", flush=True)
print("SWEEP_DONE", flush=True)
