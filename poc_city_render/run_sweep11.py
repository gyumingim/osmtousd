"""Cycle11 — ★과제 본질 벤치(drone-vs-bird): 작은 원거리 드론(중앙48px) + 새 distractor.
벤치1/2는 큰 근접드론(중앙221/317px)이라 과제(원거리 tiny 안티드론)와 안 맞았음. 이게 진짜 regime.
class1=드론(1654), class0=새(하드네거티브). 단일 drone(class1만) 탐지.
A(real만) vs B(real+개선합성) vs C(개선합성pretrain→실FT), N50/100×3시드. test=dvb valid+test.
개선합성 pretrain은 s9_pretrain 재사용(같은 개선합성 모델). 쿨다운·토큰무관·CSV증분."""
import subprocess, csv, shutil, glob, os, random, statistics, time

RUNS = "/home/karma/OSMtoUSD/poc_city_render/runs"
YOLO = "/home/karma/OSMtoUSD/drone_det/venv/bin/yolo"
OUT = "cycle2_data"; AB = os.path.abspath(OUT)
DVB = "benchmarks/dvb"
PRE = f"{RUNS}/s9_pretrain/weights/best.pt"   # 개선합성 pretrain 재사용
random.seed(0)

def drone_rows(lbl):  # class1(드론)만 → 단일 drone(class0)
    out = []
    if os.path.exists(lbl):
        for l in open(lbl):
            p = l.split()
            if len(p) >= 5 and int(float(p[0])) == 1:
                out.append("0 " + " ".join(p[1:5]))
    return out

def copy_set(imgs, sub):
    shutil.rmtree(f"{OUT}/{sub}", ignore_errors=True)
    os.makedirs(f"{OUT}/{sub}/images"); os.makedirs(f"{OUT}/{sub}/labels")
    n = 0
    for img in imgs:
        lf = img.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt"
        rows = drone_rows(lf)
        if rows:
            bn = os.path.basename(img); shutil.copy(img, f"{OUT}/{sub}/images/{bn}")
            open(f"{OUT}/{sub}/labels/" + bn.rsplit(".", 1)[0] + ".txt", "w").write("\n".join(rows)); n += 1
    return n

test_imgs = sorted(glob.glob(f"{DVB}/valid/images/*")) + sorted(glob.glob(f"{DVB}/test/images/*"))
nt = copy_set(test_imgs, "test3")
pool = [i for i in sorted(glob.glob(f"{DVB}/train/images/*")) if drone_rows(i.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt")]
random.shuffle(pool)
print(f"test3(드론)={nt}장 | dvb train 드론-pos={len(pool)}장", flush=True)
for N in [50, 100]:
    copy_set(pool[:N], f"real3_{N}")
    open(f"{OUT}/h_A{N}.yaml", "w").write(f"path: {AB}\ntrain: real3_{N}/images\nval: test3/images\nnc: 1\nnames: ['drone']\n")
    open(f"{OUT}/h_B{N}.yaml", "w").write(f"path: {AB}\ntrain:\n  - real3_{N}/images\n  - synth/images\nval: test3/images\nnc: 1\nnames: ['drone']\n")

def best(run):
    r = list(csv.DictReader(open(f"{RUNS}/{run}/results.csv")))
    return max(float(x["metrics/mAP50(B)"]) for x in r)

def train(name, model, yaml, seed):
    shutil.rmtree(f"{RUNS}/{name}", ignore_errors=True)
    subprocess.run([YOLO, "detect", "train", f"model={model}", f"data={yaml}", "imgsz=640",
                    "batch=16", "epochs=120", "patience=30", "cache=False", "workers=6", "device=0",
                    "mosaic=0.0", f"seed={seed}", f"project={RUNS}", f"name={name}", "exist_ok=True"],
                   stdout=open(f"s11_{name}.log", "w"), stderr=subprocess.STDOUT)
    time.sleep(20)
    return best(name)

rows = []
for N in [50, 100]:
    for s in [0, 1, 2]:
        a = train(f"s11_A{N}_{s}", "yolo11s.pt", f"{OUT}/h_A{N}.yaml", s)
        b = train(f"s11_B{N}_{s}", "yolo11s.pt", f"{OUT}/h_B{N}.yaml", s)
        c = train(f"s11_C{N}_{s}", PRE, f"{OUT}/h_A{N}.yaml", s)
        rows.append((N, s, round(a, 4), round(b, 4), round(c, 4)))
        with open("sweep11_results.csv", "w") as f:
            f.write("N,seed,A_real,B_real+synth,C_synthpretrain+FT\n")
            for r in rows:
                f.write(",".join(map(str, r)) + "\n")
        print(f"N={N} s={s}: A={a:.3f} B={b:.3f} C={c:.3f}", flush=True)

print("=== ★과제본질(drone-vs-bird, 작은드론): 합성 도움? (시드평균) ===", flush=True)
for N in [50, 100]:
    A = [r[2] for r in rows if r[0] == N]; B = [r[3] for r in rows if r[0] == N]; C = [r[4] for r in rows if r[0] == N]
    if A:
        am, bm, cm = statistics.mean(A), statistics.mean(B), statistics.mean(C)
        print(f"N={N}: A={am:.3f} | B(mix)={bm:.3f}({bm-am:+.3f}) | C(pre→FT)={cm:.3f}({cm-am:+.3f})", flush=True)
print("SWEEP11_DONE", flush=True)
