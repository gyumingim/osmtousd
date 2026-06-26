"""Cycle4 — PDF 정확한 방법: 합성 사전학습 → 실 fine-tune (C). 믹스(B)·real-only(A)와 비교.
합성359로 pretrain → real50/100서 finetune (시드3). C>B면 pretrain→finetune이 더 나은 방법."""
import subprocess, csv, shutil, statistics, os
RUNS = "/home/karma/OSMtoUSD/poc_city_render/runs"
YOLO = "/home/karma/OSMtoUSD/drone_det/venv/bin/yolo"
OUT = "cycle2_data"
AB = os.path.abspath(OUT)

def best(run):
    r = list(csv.DictReader(open(f"{RUNS}/{run}/results.csv")))
    return max(float(x["metrics/mAP50(B)"]) for x in r)

def train(name, model, yaml, seed, epochs=120):
    shutil.rmtree(f"{RUNS}/{name}", ignore_errors=True)
    subprocess.run([YOLO, "detect", "train", f"model={model}", f"data={yaml}",
                    "imgsz=640", "batch=16", f"epochs={epochs}", "patience=30", "cache=False",
                    "workers=6", "device=0", "mosaic=0.0", f"seed={seed}",
                    f"project={RUNS}", f"name={name}", "exist_ok=True"],
                   stdout=open(f"s4_{name}.log", "w"), stderr=subprocess.STDOUT)
    return best(name)

# 합성 단일클래스 yaml (val=test로 진행 확인용)
open(f"{OUT}/d_synth.yaml", "w").write(f"path: {AB}\ntrain: synth/images\nval: test/images\nnc: 1\nnames: ['drone']\n")
# 1) 합성 pretrain (1회)
print("합성 pretrain 중...", flush=True)
train("s4_pretrain", "yolo11s.pt", f"{OUT}/d_synth.yaml", 0, epochs=100)
PRE = f"{RUNS}/s4_pretrain/weights/best.pt"
print(f"pretrain 완료: {PRE}", flush=True)

rows = []
for N in [50, 100]:
    for s in [0, 1, 2]:
        c = train(f"s4_C{N}_{s}", PRE, f"{OUT}/dA_{N}.yaml", s)   # 합성pretrain → real-only finetune
        rows.append((N, s, round(c, 4)))
        with open("sweep4_results.csv", "w") as f:
            f.write("N,seed,C_synthpretrain+realFT\n")
            for r in rows:
                f.write(",".join(map(str, r))+"\n")
        print(f"N={N} seed={s}: C={c:.3f}", flush=True)

print("=== C 평균 (vs A=real만, B=믹스) ===", flush=True)
ref = {50: (0.202, 0.413), 100: (0.311, 0.557)}
for N in [50, 100]:
    Cs = [r[2] for r in rows if r[0] == N]
    if Cs:
        cm = statistics.mean(Cs); a, b = ref[N]
        print(f"N={N}: A(real)={a:.3f} B(mix)={b:.3f} C(pretrain→FT)={cm:.3f} | C-A={cm-a:+.3f} C-B={cm-b:+.3f}", flush=True)
print("SWEEP4_DONE", flush=True)
