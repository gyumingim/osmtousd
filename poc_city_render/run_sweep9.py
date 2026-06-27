"""Cycle9 — 벤치2서 PDF 정확방법(개선합성 pretrain→실FT, C) vs real-only(A).
Cycle8서 naive MIX(B)는 벤치2 scarce서 붕괴(N10 0.73→0.16): 합성271이 real10을 비율지배.
PDF 방법(C)은 최종 fine-tune이 real만 → 이 붕괴를 피함. 정확방법의 견고성 검증.
real2_N/g_A yaml은 sweep7/8 산출물 재사용. A(real-only)도 그 값 재사용(동일 seed). 쿨다운·토큰무관."""
import subprocess, csv, shutil, glob, os, statistics, time

RUNS = "/home/karma/OSMtoUSD/poc_city_render/runs"
YOLO = "/home/karma/OSMtoUSD/drone_det/venv/bin/yolo"
OUT = "cycle2_data"; AB = os.path.abspath(OUT)

# 개선합성 pretrain용 yaml (val=test2 진행확인용)
open(f"{OUT}/d_synthnew.yaml", "w").write(f"path: {AB}\ntrain: synth/images\nval: test2/images\nnc: 1\nnames: ['drone']\n")

def best(run):
    r = list(csv.DictReader(open(f"{RUNS}/{run}/results.csv")))
    return max(float(x["metrics/mAP50(B)"]) for x in r)

def train(name, model, yaml, seed, epochs=120, patience=30):
    shutil.rmtree(f"{RUNS}/{name}", ignore_errors=True)
    subprocess.run([YOLO, "detect", "train", f"model={model}", f"data={yaml}", "imgsz=640",
                    "batch=16", f"epochs={epochs}", f"patience={patience}", "cache=False", "workers=6",
                    "device=0", "mosaic=0.0", f"seed={seed}", f"project={RUNS}", f"name={name}", "exist_ok=True"],
                   stdout=open(f"s9_{name}.log", "w"), stderr=subprocess.STDOUT)
    time.sleep(20)
    return best(name)

# 1) 개선합성 pretrain (1회)
print("개선합성 pretrain 중...", flush=True)
train("s9_pretrain", "yolo11s.pt", f"{OUT}/d_synthnew.yaml", 0, epochs=100, patience=25)
PRE = f"{RUNS}/s9_pretrain/weights/best.pt"

# A(real-only) sweep7/8 재사용 (동일 데이터·seed)
Aref = {10: 0.728, 25: 0.825, 50: 0.652}
rows = []
for N in [10, 25, 50]:
    for s in [0, 1, 2]:
        c = train(f"s9_C{N}_{s}", PRE, f"{OUT}/g_A{N}.yaml", s)   # 개선합성pretrain → real2_N FT
        rows.append((N, s, round(c, 4)))
        with open("sweep9_results.csv", "w") as f:
            f.write("N,seed,C_improvedSynthPretrain+realFT\n")
            for r in rows:
                f.write(",".join(map(str, r)) + "\n")
        print(f"N={N} s={s}: C={c:.3f}", flush=True)

print("=== 벤치2: 정확방법(C=pretrain→FT) vs A(real) vs B(mix, Cycle8) ===", flush=True)
Bref = {10: 0.160, 25: 0.333, 50: 0.535}   # Cycle8/7 mix
for N in [10, 25, 50]:
    Cs = [r[2] for r in rows if r[0] == N]
    if Cs:
        cm = statistics.mean(Cs)
        print(f"N={N}: A(real)={Aref[N]:.3f} | B(mix)={Bref[N]:.3f} | C(pretrain→FT)={cm:.3f} | C-A={cm-Aref[N]:+.3f} C-B={cm-Bref[N]:+.3f}", flush=True)
print("SWEEP9_DONE", flush=True)
