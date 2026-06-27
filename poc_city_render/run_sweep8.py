"""Cycle8 — 벤치2(ITU UAV) 진짜 scarce 영역(N=10,25)서 개선합성이 도움되나.
Cycle7서 N=50은 real-only가 이미 강함(포화) → 합성가치 애매. scarce일수록 합성 도움(Cycle5가설)을 벤치2서 검증.
A2(real만) vs Bnew(real+개선합성), 3시드. test2/synth는 sweep7 산출물 재사용. 쿨다운·토큰무관."""
import subprocess, csv, shutil, glob, os, random, statistics, time

RUNS = "/home/karma/OSMtoUSD/poc_city_render/runs"
YOLO = "/home/karma/OSMtoUSD/drone_det/venv/bin/yolo"
OUT = "cycle2_data"; AB = os.path.abspath(OUT)
ITU = "benchmarks/uav_itu"
random.seed(0)   # sweep7과 동일 셔플 → real2_10/25는 real2_50의 부분집합(일관)

def has_box(lbl):
    return os.path.exists(lbl) and any(len(l.split()) >= 5 for l in open(lbl))

def copy_set(imgs, sub):
    shutil.rmtree(f"{OUT}/{sub}", ignore_errors=True)
    os.makedirs(f"{OUT}/{sub}/images"); os.makedirs(f"{OUT}/{sub}/labels")
    for img in imgs:
        lf = img.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt"
        if has_box(lf):
            bn = os.path.basename(img); shutil.copy(img, f"{OUT}/{sub}/images/{bn}")
            rows = ["0 " + " ".join(l.split()[1:5]) for l in open(lf) if len(l.split()) >= 5]
            open(f"{OUT}/{sub}/labels/" + bn.rsplit(".", 1)[0] + ".txt", "w").write("\n".join(rows))

train_pool = [i for i in sorted(glob.glob(f"{ITU}/train/images/*"))
              if has_box(i.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt")]
random.shuffle(train_pool)
for N in [10, 25]:
    copy_set(train_pool[:N], f"real2_{N}")
    open(f"{OUT}/g_A{N}.yaml", "w").write(f"path: {AB}\ntrain: real2_{N}/images\nval: test2/images\nnc: 1\nnames: ['drone']\n")
    open(f"{OUT}/g_Bnew{N}.yaml", "w").write(f"path: {AB}\ntrain:\n  - real2_{N}/images\n  - synth/images\nval: test2/images\nnc: 1\nnames: ['drone']\n")
print(f"test2={len(glob.glob(f'{OUT}/test2/images/*'))} | synth(개선)={len(glob.glob(f'{OUT}/synth/images/*'))}", flush=True)

def best(run):
    r = list(csv.DictReader(open(f"{RUNS}/{run}/results.csv")))
    return max(float(x["metrics/mAP50(B)"]) for x in r)

def train(name, yaml, seed):
    shutil.rmtree(f"{RUNS}/{name}", ignore_errors=True)
    subprocess.run([YOLO, "detect", "train", "model=yolo11s.pt", f"data={yaml}", "imgsz=640",
                    "batch=16", "epochs=120", "patience=30", "cache=False", "workers=6", "device=0",
                    "mosaic=0.0", f"seed={seed}", f"project={RUNS}", f"name={name}", "exist_ok=True"],
                   stdout=open(f"s8_{name}.log", "w"), stderr=subprocess.STDOUT)
    time.sleep(20)
    return best(name)

rows = []
for N in [10, 25]:
    for s in [0, 1, 2]:
        a = train(f"s8_A{N}_{s}", f"{OUT}/g_A{N}.yaml", s)
        bn = train(f"s8_Bn{N}_{s}", f"{OUT}/g_Bnew{N}.yaml", s)
        rows.append((N, s, round(a, 4), round(bn, 4)))
        with open("sweep8_results.csv", "w") as f:
            f.write("N,seed,A_real,Bnew_real+improvedsynth\n")
            for r in rows:
                f.write(",".join(map(str, r)) + "\n")
        print(f"N={N} s={s}: A={a:.3f} Bnew={bn:.3f} d={bn-a:+.3f}", flush=True)

print("=== 벤치2 scarce 영역: 개선합성 도움? (시드평균) ===", flush=True)
for N in [10, 25]:
    A = [r[2] for r in rows if r[0] == N]; Bn = [r[3] for r in rows if r[0] == N]
    if A:
        am, bnm = statistics.mean(A), statistics.mean(Bn)
        print(f"N={N}: A={am:.3f}(std {statistics.pstdev(A):.3f}) Bnew={bnm:.3f}(std {statistics.pstdev(Bn):.3f}) delta={bnm-am:+.3f}", flush=True)
print("SWEEP8_DONE", flush=True)
