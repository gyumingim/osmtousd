"""야간 자율 학습 매트릭스: 합성만 / 실+합성(pretrain→FT) × yolo11 n·s·l + 참조 real-only.
각 모델 dvb 벤치(test3 주, test/test2 보조) 평가. 결과 CSV/MD 누적저장(중단대비)."""
import os, csv, datetime, traceback, gc
import torch
from ultralytics import YOLO

POC = "/home/karma/OSMtoUSD/poc_city_render"
C2  = f"{POC}/cycle2_data"
OUT = f"{POC}/train_runs"; os.makedirs(OUT, exist_ok=True)
DS_SYNTH = f"{POC}/dataset_v1/images"       # 신규 10k 합성(class0)
REAL     = f"{C2}/de_real400/images"        # 실 400(drone-only)
VAL      = f"{C2}/test/images"              # 학습 val(early stop)
EVAL = {"dvb_test3": f"{C2}/test3/images", "dvb_test": f"{C2}/test/images", "dvb_test2": f"{C2}/test2/images"}
COCO = {"n": "/home/karma/OSMtoUSD/drone_det/yolo11n.pt", "s": f"{POC}/yolo11s.pt", "l": f"{POC}/yolo11l.pt"}
BATCH = {"n": 32, "s": 16, "l": 8}
CSVP = f"{POC}/train_results.csv"
MDP  = f"{POC}/TRAIN_RESULTS.md"

def log(m):
    s = f"{datetime.datetime.now():%m-%d %H:%M:%S} {m}"
    print(s, flush=True)
    open(f"{OUT}/orchestrator.log", "a").write(s + "\n")

def avail_mb():
    for l in open("/proc/meminfo"):
        if l.startswith("MemAvailable"): return int(l.split()[1]) // 1024

def mkyaml(path, train, val):
    with open(path, "w") as f:
        if isinstance(train, list):
            f.write("train:\n"); [f.write(f"  - {t}\n") for t in train]
        else: f.write(f"train: {train}\n")
        f.write(f"val: {val}\nnc: 1\nnames: ['drone']\n")

Y_SYNTH = f"{OUT}/d_synth.yaml"; mkyaml(Y_SYNTH, DS_SYNTH, VAL)
Y_REAL  = f"{OUT}/d_real.yaml";  mkyaml(Y_REAL,  REAL,     VAL)
EY = {}
for name, vd in EVAL.items():
    p = f"{OUT}/e_{name}.yaml"; mkyaml(p, vd, vd); EY[name] = p

if not os.path.exists(CSVP):
    csv.writer(open(CSVP, "w")).writerow(
        ["cond", "model", "dvb_test3_map50", "dvb_test3_map5095", "dvb_test_map50", "dvb_test2_map50"])

def train_one(tag, mdl, init_w, data_yaml, epochs, patience):
    b = BATCH[mdl]
    for attempt in range(3):
        try:
            m = YOLO(init_w)
            m.train(data=data_yaml, epochs=epochs, patience=patience, imgsz=640, batch=b,
                    cache=False, workers=4, device=0, project=OUT, name=tag, exist_ok=True,
                    verbose=False, plots=False)
            return f"{OUT}/{tag}/weights/best.pt"
        except RuntimeError as e:
            if "out of memory" in str(e).lower() and b > 2:
                torch.cuda.empty_cache(); gc.collect(); b = max(2, b // 2)
                log(f"  OOM → batch {b} 재시도 ({tag})")
            else: raise
    return None

def eval_dvb(best):
    res = {}
    ev = YOLO(best)
    for name, yp in EY.items():
        vr = ev.val(data=yp, imgsz=640, device=0, project=OUT, name=f"tmp_{name}",
                    exist_ok=True, verbose=False, plots=False)
        res[name] = (round(float(vr.box.map50), 4), round(float(vr.box.map), 4))
    return res

# (tag, model, init가중치, 데이터, epochs, patience). 순서=요청6런 먼저, real-only 참조 뒤.
RUNS = []
for mdl in ["n", "s", "l"]:
    RUNS.append((f"synth_{mdl}", mdl, COCO[mdl], Y_SYNTH, 50, 10))                 # 합성만
    RUNS.append((f"ft_{mdl}",    mdl, f"{OUT}/synth_{mdl}/weights/best.pt", Y_REAL, 40, 10))  # 실+합성(FT)
for mdl in ["n", "s", "l"]:
    RUNS.append((f"real_{mdl}",  mdl, COCO[mdl], Y_REAL, 60, 15))                  # 참조 real-only

log(f"학습매트릭스 시작: {len(RUNS)}런 (avail {avail_mb()}MB, synth={DS_SYNTH})")
for tag, mdl, init_w, data_yaml, ep, pat in RUNS:
    try:
        if not os.path.exists(init_w):
            log(f"SKIP {tag}: init가중치 없음 {init_w}"); continue
        log(f"=== TRAIN {tag} (avail {avail_mb()}MB) ===")
        best = train_one(tag, mdl, init_w, data_yaml, ep, pat)
        if not best or not os.path.exists(best):
            log(f"FAIL {tag}: best.pt 없음"); continue
        r = eval_dvb(best)
        cond = "합성만" if tag.startswith("synth") else ("실+합성FT" if tag.startswith("ft") else "real-only")
        csv.writer(open(CSVP, "a")).writerow(
            [cond, mdl, r["dvb_test3"][0], r["dvb_test3"][1], r["dvb_test"][0], r["dvb_test2"][0]])
        log(f"DONE {tag}: dvb_test3 mAP50={r['dvb_test3'][0]} mAP50-95={r['dvb_test3'][1]} | test={r['dvb_test'][0]} test2={r['dvb_test2'][0]}")
        torch.cuda.empty_cache(); gc.collect()
    except Exception as e:
        log(f"FAIL {tag}: {e}\n{traceback.format_exc()}")

# 마크다운 표
rows = list(csv.reader(open(CSVP)))
with open(MDP, "w") as f:
    f.write(f"# 야간 학습 결과 ({datetime.datetime.now():%Y-%m-%d %H:%M})\n\n")
    f.write("합성=신규10k · 실=de_real400 · 벤치=dvb. 실+합성FT = 합성pretrain→실fine-tune.\n\n")
    f.write("| 조건 | 모델 | dvb_test3 mAP50 | mAP50-95 | test mAP50 | test2 mAP50 |\n")
    f.write("|---|---|---|---|---|---|\n")
    for row in rows[1:]:
        f.write("| " + " | ".join(row) + " |\n")
log("ALL_TRAIN_DONE")
print("ALL_TRAIN_DONE", flush=True)
