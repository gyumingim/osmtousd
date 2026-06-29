"""Cycle6 — 개선합성(시뮬현실화 A1) 가치 재측정.
dataset_v1(개선 시뮬) → synth 재구성 → B(real+개선synth) 다중시드 재측정.
Cycle3(old synth) 기준과 비교: new_B > old_B면 시뮬개선이 boost를 키움 = 'ttest→자체판단' 정량근거.
A(real-only)는 합성 무관·불변 → Cycle3값 재사용(GPU 절약). 같은 seed/세팅."""
import subprocess, csv, shutil, glob, os, statistics

RUNS = "/home/karma/OSMtoUSD/poc_city_render/runs"
YOLO = "/home/karma/OSMtoUSD/drone_det/venv/bin/yolo"
OUT = "cycle2_data"

# 1) 개선합성(dataset_v1) → synth 재구성 (양성 프레임=라벨 비어있지 않음)
shutil.rmtree(f"{OUT}/synth", ignore_errors=True)
os.makedirs(f"{OUT}/synth/images"); os.makedirs(f"{OUT}/synth/labels")
ns = 0
for img in sorted(glob.glob("dataset_v1/images/*.jpg")):
    lf = "dataset_v1/labels/" + os.path.basename(img).replace(".jpg", ".txt")
    if os.path.exists(lf) and os.path.getsize(lf) > 0:
        bn = os.path.basename(img)
        shutil.copy(img, f"{OUT}/synth/images/{bn}")
        shutil.copy(lf, f"{OUT}/synth/labels/{bn.replace('.png', '.txt')}")
        ns += 1
print(f"개선합성 synth 재구성: {ns}장 (dataset_v1)", flush=True)

def best(run):
    r = list(csv.DictReader(open(f"{RUNS}/{run}/results.csv")))
    return max(float(x["metrics/mAP50(B)"]) for x in r)

def train(name, yaml, seed):
    shutil.rmtree(f"{RUNS}/{name}", ignore_errors=True)
    subprocess.run([YOLO, "detect", "train", "model=yolo11s.pt", f"data={yaml}",
                    "imgsz=640", "batch=16", "epochs=120", "patience=30", "cache=False",
                    "workers=6", "device=0", "mosaic=0.0", f"seed={seed}",
                    f"project={RUNS}", f"name={name}", "exist_ok=True"],
                   stdout=open(f"s6_{name}.log", "w"), stderr=subprocess.STDOUT)
    return best(name)

# Cycle3 기준(old synth, sweep3_results.csv 시드평균)
old = {50: {"A": 0.202, "B": 0.413}, 100: {"A": 0.311, "B": 0.557}}
rows = []
for N in [50, 100]:
    for s in [0, 1, 2]:
        b = train(f"s6_B{N}_{s}", f"{OUT}/dB_{N}.yaml", s)   # real_N + 개선synth
        rows.append((N, s, round(b, 4)))
        with open("sweep6_results.csv", "w") as f:
            f.write("N,seed,B_real+improvedSynth\n")
            for r in rows:
                f.write(",".join(map(str, r))+"\n")
        print(f"N={N} seed={s}: B_new={b:.3f}", flush=True)

print("=== 개선합성 vs old synth (시드평균 B) ===", flush=True)
for N in [50, 100]:
    Bs = [r[2] for r in rows if r[0] == N]
    if Bs:
        bm = statistics.mean(Bs)
        print(f"N={N}: A(real)={old[N]['A']:.3f} | old_B={old[N]['B']:.3f} → new_B={bm:.3f} "
              f"(vs old {bm-old[N]['B']:+.3f}) | new_delta(B-A)={bm-old[N]['A']:+.3f}", flush=True)
print("SWEEP6_DONE", flush=True)
