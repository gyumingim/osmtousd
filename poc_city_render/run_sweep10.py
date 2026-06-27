"""Cycle10 — 교차도메인 강건성(안티드론 실배포 = 도메인시프트).
벤치1 실데이터로 학습 → 벤치2(ITU, 다른 출처)서 테스트.
A(real만) vs C(개선합성 pretrain→실FT). C>A면 합성이 도메인시프트 강건성↑ = 과제 핵심가치.
개선합성 pretrain은 s9_pretrain 재사용. 쿨다운·토큰무관."""
import subprocess, csv, shutil, os, statistics, time

RUNS = "/home/karma/OSMtoUSD/poc_city_render/runs"
YOLO = "/home/karma/OSMtoUSD/drone_det/venv/bin/yolo"
OUT = "cycle2_data"; AB = os.path.abspath(OUT)
PRE = f"{RUNS}/s9_pretrain/weights/best.pt"   # 개선합성 pretrain (Cycle9)
assert os.path.exists(PRE), "s9_pretrain 없음"

# cross yaml: train=벤치1 real_N, val=벤치2 test2 (도메인시프트 평가)
for N in [50, 100]:
    open(f"{OUT}/x_{N}.yaml", "w").write(
        f"path: {AB}\ntrain: real{N}/images\nval: test2/images\nnc: 1\nnames: ['drone']\n")

def best(run):
    r = list(csv.DictReader(open(f"{RUNS}/{run}/results.csv")))
    return max(float(x["metrics/mAP50(B)"]) for x in r)

def train(name, model, yaml, seed):
    shutil.rmtree(f"{RUNS}/{name}", ignore_errors=True)
    subprocess.run([YOLO, "detect", "train", f"model={model}", f"data={yaml}", "imgsz=640",
                    "batch=16", "epochs=120", "patience=30", "cache=False", "workers=6", "device=0",
                    "mosaic=0.0", f"seed={seed}", f"project={RUNS}", f"name={name}", "exist_ok=True"],
                   stdout=open(f"s10_{name}.log", "w"), stderr=subprocess.STDOUT)
    time.sleep(20)
    return best(name)

rows = []
for N in [50, 100]:
    for s in [0, 1, 2]:
        a = train(f"s10_A{N}_{s}", "yolo11s.pt", f"{OUT}/x_{N}.yaml", s)     # 벤치1 real만 → 벤치2
        c = train(f"s10_C{N}_{s}", PRE, f"{OUT}/x_{N}.yaml", s)              # 개선합성pretrain → 벤치1 real FT → 벤치2
        rows.append((N, s, round(a, 4), round(c, 4)))
        with open("sweep10_results.csv", "w") as f:
            f.write("N,seed,A_cross_realonly,C_cross_synthpretrain+realFT\n")
            for r in rows:
                f.write(",".join(map(str, r)) + "\n")
        print(f"N={N} s={s}: A={a:.3f} C={c:.3f} d={c-a:+.3f}", flush=True)

print("=== 교차도메인(벤치1학습→벤치2테스트): 합성 pretrain이 강건성↑? (시드평균) ===", flush=True)
for N in [50, 100]:
    A = [r[2] for r in rows if r[0] == N]; C = [r[3] for r in rows if r[0] == N]
    if A:
        am, cm = statistics.mean(A), statistics.mean(C)
        print(f"N={N}: A={am:.3f}(std {statistics.pstdev(A):.3f}) C={cm:.3f}(std {statistics.pstdev(C):.3f}) delta={cm-am:+.3f}", flush=True)
print("SWEEP10_DONE", flush=True)
