"""Cycle12 — Cycle11 C붕괴(N50 0.112) 원인규명. C는 s9_pretrain(ITU용) 재사용이었음.
dvb용 신선 개선합성 pretrain → dvb real FT면 N50서도 작동하나? = pretrain→FT 방법 견고성.
신선pretrain(val=test3 epoch선택) → real3_50/100 FT × 3시드. Cycle11 C(붕괴)와 비교."""
import subprocess, csv, shutil, os, statistics, time

RUNS = "/home/karma/OSMtoUSD/poc_city_render/runs"
YOLO = "/home/karma/OSMtoUSD/drone_det/venv/bin/yolo"
OUT = "cycle2_data"; AB = os.path.abspath(OUT)

open(f"{OUT}/d_synth_dvb.yaml", "w").write(f"path: {AB}\ntrain: synth/images\nval: test3/images\nnc: 1\nnames: ['drone']\n")

def best(run):
    r = list(csv.DictReader(open(f"{RUNS}/{run}/results.csv")))
    return max(float(x["metrics/mAP50(B)"]) for x in r)

def train(name, model, yaml, seed, epochs=120, patience=30):
    shutil.rmtree(f"{RUNS}/{name}", ignore_errors=True)
    subprocess.run([YOLO, "detect", "train", f"model={model}", f"data={yaml}", "imgsz=640",
                    "batch=16", f"epochs={epochs}", f"patience={patience}", "cache=False", "workers=6",
                    "device=0", "mosaic=0.0", f"seed={seed}", f"project={RUNS}", f"name={name}", "exist_ok=True"],
                   stdout=open(f"s12_{name}.log", "w"), stderr=subprocess.STDOUT)
    time.sleep(20)
    return best(name)

print("dvb용 신선 개선합성 pretrain...", flush=True)
train("s12_pretrain", "yolo11s.pt", f"{OUT}/d_synth_dvb.yaml", 0, epochs=100, patience=25)
PRE = f"{RUNS}/s12_pretrain/weights/best.pt"

Cref = {50: 0.112, 100: 0.797}   # Cycle11 C (s9 재사용)
Aref = {50: 0.337, 100: 0.688}; Bref = {50: 0.656, 100: 0.739}
rows = []
for N in [50, 100]:
    for s in [0, 1, 2]:
        c = train(f"s12_C{N}_{s}", PRE, f"{OUT}/h_A{N}.yaml", s)   # 신선pretrain → dvb real FT
        rows.append((N, s, round(c, 4)))
        with open("sweep12_results.csv", "w") as f:
            f.write("N,seed,C_freshDvbPretrain+realFT\n")
            for r in rows:
                f.write(",".join(map(str, r)) + "\n")
        print(f"N={N} s={s}: C_fresh={c:.3f}", flush=True)

print("=== dvb: 신선pretrain→FT vs (Cycle11 C재사용, A, B) ===", flush=True)
for N in [50, 100]:
    Cs = [r[2] for r in rows if r[0] == N]
    if Cs:
        cm = statistics.mean(Cs)
        print(f"N={N}: A={Aref[N]:.3f} B(mix)={Bref[N]:.3f} | C(s9재사용)={Cref[N]:.3f} → C(신선)={cm:.3f}", flush=True)
print("SWEEP12_DONE", flush=True)
