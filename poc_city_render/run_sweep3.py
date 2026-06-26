"""Cycle3 — 합성가치 엄밀화. 분산 제거: N=50/100 각 시드 3개 A/B 평균 + mosaic 끔(소량학습 안정).
기존 real50/100, synth, dA/dB yaml 재사용. 토큰무관 detach."""
import subprocess, csv, shutil, statistics
RUNS = "/home/karma/OSMtoUSD/poc_city_render/runs"
YOLO = "/home/karma/OSMtoUSD/drone_det/venv/bin/yolo"
OUT = "cycle2_data"

def best(run):
    r = list(csv.DictReader(open(f"{RUNS}/{run}/results.csv")))
    return max(float(x["metrics/mAP50(B)"]) for x in r)

def train(name, yaml, seed):
    shutil.rmtree(f"{RUNS}/{name}", ignore_errors=True)
    subprocess.run([YOLO, "detect", "train", "model=yolo11s.pt", f"data={yaml}",
                    "imgsz=640", "batch=16", "epochs=120", "patience=30", "cache=False",
                    "workers=6", "device=0", "mosaic=0.0", f"seed={seed}",
                    f"project={RUNS}", f"name={name}", "exist_ok=True"],
                   stdout=open(f"s3_{name}.log", "w"), stderr=subprocess.STDOUT)
    return best(name)

rows = []
for N in [50, 100]:
    for s in [0, 1, 2]:
        a = train(f"s3_A{N}_{s}", f"{OUT}/dA_{N}.yaml", s)
        b = train(f"s3_B{N}_{s}", f"{OUT}/dB_{N}.yaml", s)
        rows.append((N, s, round(a, 4), round(b, 4), round(b-a, 4)))
        with open("sweep3_results.csv", "w") as f:
            f.write("N,seed,A_real,B_real+synth,delta\n")
            for r in rows:
                f.write(",".join(map(str, r))+"\n")
        print(f"N={N} seed={s}: A={a:.3f} B={b:.3f} d={b-a:+.3f}", flush=True)

print("=== 시드평균 (합성가치 정직측정) ===", flush=True)
for N in [50, 100]:
    As = [r[2] for r in rows if r[0] == N]; Bs = [r[3] for r in rows if r[0] == N]
    if As:
        am, bm = statistics.mean(As), statistics.mean(Bs)
        print(f"N={N}: A_mean={am:.3f} B_mean={bm:.3f} delta={bm-am:+.3f} (n={len(As)})", flush=True)
print("SWEEP3_DONE", flush=True)
