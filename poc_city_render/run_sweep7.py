"""Cycle7 — 일반화 검증. 2번째 실벤치(ITU UAV: 다른출처·깨끗한 단일'UAV'·헬기혼입 없음).
benchmark2서 A2(real만) vs B2old(real+old합성) vs B2new(real+개선합성), N50/100 × 3시드.
개선합성이 벤치2서도 도움(>A) + old보다 나으면(>Bold) → Cycle6 개선이 일반화(한 벤치 과적합 아님).
발열관리: 학습 사이 쿨다운. 토큰무관 detach. CSV 증분기록(중단해도 부분결과)."""
import subprocess, csv, shutil, glob, os, random, statistics, time

RUNS = "/home/karma/OSMtoUSD/poc_city_render/runs"
YOLO = "/home/karma/OSMtoUSD/drone_det/venv/bin/yolo"
OUT = "cycle2_data"; AB = os.path.abspath(OUT)
ITU = "benchmarks/uav_itu"
random.seed(0)

def has_box(lbl):
    return os.path.exists(lbl) and any(len(l.split()) >= 5 for l in open(lbl))

def copy_set(imgs, sub):
    shutil.rmtree(f"{OUT}/{sub}", ignore_errors=True)
    os.makedirs(f"{OUT}/{sub}/images"); os.makedirs(f"{OUT}/{sub}/labels")
    n = 0
    for img in imgs:
        lf = img.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt"
        if has_box(lf):
            bn = os.path.basename(img); shutil.copy(img, f"{OUT}/{sub}/images/{bn}")
            rows = ["0 " + " ".join(l.split()[1:5]) for l in open(lf) if len(l.split()) >= 5]  # 단일 drone(class0)
            open(f"{OUT}/{sub}/labels/" + bn.rsplit(".", 1)[0] + ".txt", "w").write("\n".join(rows))
            n += 1
    return n

# test2 = ITU valid+test (안정적 평가 위해 합침)
test_imgs = sorted(glob.glob(f"{ITU}/valid/images/*")) + sorted(glob.glob(f"{ITU}/test/images/*"))
nt = copy_set(test_imgs, "test2")
train_pool = [i for i in sorted(glob.glob(f"{ITU}/train/images/*"))
              if has_box(i.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt")]
random.shuffle(train_pool)
print(f"test2={nt}장 | ITU train UAV-pos={len(train_pool)}장", flush=True)
for N in [50, 100]:
    copy_set(train_pool[:N], f"real2_{N}")

# synth_old (dataset_pose, box포맷) — 비교용
shutil.rmtree(f"{OUT}/synth_old", ignore_errors=True)
os.makedirs(f"{OUT}/synth_old/images"); os.makedirs(f"{OUT}/synth_old/labels")
nso = 0
for img in glob.glob("dataset_pose/images/train/*.png"):
    lf = "dataset_pose/labels/train/" + os.path.basename(img).replace(".png", ".txt")
    rows = ["0 " + " ".join(l.split()[1:5]) for l in open(lf) if len(l.split()) >= 5] if os.path.exists(lf) else []
    if rows:
        bn = os.path.basename(img); shutil.copy(img, f"{OUT}/synth_old/images/{bn}")
        open(f"{OUT}/synth_old/labels/" + bn.replace(".png", ".txt"), "w").write("\n".join(rows)); nso += 1
nsn = len(glob.glob(f"{OUT}/synth/images/*.png"))   # synth = 현재 개선합성
print(f"synth_old={nso}장 synth_new(개선)={nsn}장", flush=True)

for N in [50, 100]:
    open(f"{OUT}/g_A{N}.yaml", "w").write(f"path: {AB}\ntrain: real2_{N}/images\nval: test2/images\nnc: 1\nnames: ['drone']\n")
    open(f"{OUT}/g_Bold{N}.yaml", "w").write(f"path: {AB}\ntrain:\n  - real2_{N}/images\n  - synth_old/images\nval: test2/images\nnc: 1\nnames: ['drone']\n")
    open(f"{OUT}/g_Bnew{N}.yaml", "w").write(f"path: {AB}\ntrain:\n  - real2_{N}/images\n  - synth/images\nval: test2/images\nnc: 1\nnames: ['drone']\n")

def best(run):
    r = list(csv.DictReader(open(f"{RUNS}/{run}/results.csv")))
    return max(float(x["metrics/mAP50(B)"]) for x in r)

def train(name, yaml, seed):
    shutil.rmtree(f"{RUNS}/{name}", ignore_errors=True)
    subprocess.run([YOLO, "detect", "train", "model=yolo11s.pt", f"data={yaml}", "imgsz=640",
                    "batch=16", "epochs=120", "patience=30", "cache=False", "workers=6", "device=0",
                    "mosaic=0.0", f"seed={seed}", f"project={RUNS}", f"name={name}", "exist_ok=True"],
                   stdout=open(f"s7_{name}.log", "w"), stderr=subprocess.STDOUT)
    time.sleep(20)   # 발열 쿨다운(GPU 규칙)
    return best(name)

rows = []
for N in [50, 100]:
    for s in [0, 1, 2]:
        a = train(f"s7_A{N}_{s}", f"{OUT}/g_A{N}.yaml", s)
        bo = train(f"s7_Bo{N}_{s}", f"{OUT}/g_Bold{N}.yaml", s)
        bn = train(f"s7_Bn{N}_{s}", f"{OUT}/g_Bnew{N}.yaml", s)
        rows.append((N, s, round(a, 4), round(bo, 4), round(bn, 4)))
        with open("sweep7_results.csv", "w") as f:
            f.write("N,seed,A_real,Bold_real+oldsynth,Bnew_real+newsynth\n")
            for r in rows:
                f.write(",".join(map(str, r)) + "\n")
        print(f"N={N} s={s}: A={a:.3f} Bold={bo:.3f} Bnew={bn:.3f}", flush=True)

print("=== 일반화 검증 (benchmark2=ITU UAV, 시드평균) ===", flush=True)
for N in [50, 100]:
    A = [r[2] for r in rows if r[0] == N]; Bo = [r[3] for r in rows if r[0] == N]; Bn = [r[4] for r in rows if r[0] == N]
    if A:
        am, bom, bnm = statistics.mean(A), statistics.mean(Bo), statistics.mean(Bn)
        print(f"N={N}: A={am:.3f} | Bold={bom:.3f}({bom-am:+.3f}) | Bnew={bnm:.3f}({bnm-am:+.3f}) | new-old={bnm-bom:+.3f}", flush=True)
print("SWEEP7_DONE", flush=True)
