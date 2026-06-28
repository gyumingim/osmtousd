#!/bin/bash
# 후속: yolo11s vs yolo11l 깨끗비교(동일 합성·실데이터) N=100/200/400, A(real)·C(pretrain→FT).
# 라지가 데이터많으면 과적합 벗어나 이기나 = max정확도 가이드. l_pretrain·s_pre 재사용. 증분기록.
POC=/home/karma/OSMtoUSD/poc_city_render
PY=/home/karma/OSMtoUSD/drone_det/venv/bin/python
YOLO=/home/karma/OSMtoUSD/drone_det/venv/bin/yolo
RUNS=$POC/runs
cd $POC
Ss="imgsz=1280 batch=4 epochs=80 patience=20 cache=False workers=4 device=0 mosaic=1.0 close_mosaic=15 seed=0"
Ls="imgsz=1280 batch=2 epochs=60 patience=15 cache=False workers=3 device=0 mosaic=1.0 close_mosaic=12 seed=0"
best() { $PY -c "import csv;r=list(csv.DictReader(open('runs/$1/results.csv')));print(round(max(float(x['metrics/mAP50(B)']) for x in r),4))" 2>/dev/null; }

# real3_200/400 + yaml (test3·real3_100·synth는 8hr에서 존재)
$PY - <<'PYEOF'
import glob,os,shutil,random
random.seed(0)
DVB="benchmarks/dvb"
def has1(l): return os.path.exists(l) and any(len(x.split())>=5 and int(float(x.split()[0]))==1 for x in open(l))
def d1(l): return ["0 "+" ".join(x.split()[1:5]) for x in open(l) if len(x.split())>=5 and int(float(x.split()[0]))==1]
def build(imgs,sub):
    shutil.rmtree(f"cycle2_data/{sub}",ignore_errors=True)
    os.makedirs(f"cycle2_data/{sub}/images");os.makedirs(f"cycle2_data/{sub}/labels");c=0
    for img in imgs:
        lf=img.replace("/images/","/labels/").rsplit(".",1)[0]+".txt"; rows=d1(lf)
        if rows:
            bn=os.path.basename(img);shutil.copy(img,f"cycle2_data/{sub}/images/{bn}")
            open(f"cycle2_data/{sub}/labels/"+bn.rsplit(".",1)[0]+".txt","w").write("\n".join(rows));c+=1
    return c
pool=[i for i in sorted(glob.glob(f"{DVB}/train/images/*")) if has1(i.replace("/images/","/labels/").rsplit(".",1)[0]+".txt")]
random.shuffle(pool)
AB=os.path.abspath("cycle2_data")
for N in (200,400):
    print(f"real3_{N}",build(pool[:N],f"real3_{N}"))
    open(f"cycle2_data/h_A{N}.yaml","w").write(f"path: {AB}\ntrain: real3_{N}/images\nval: test3/images\nnc: 1\nnames: ['drone']\n")
PYEOF
echo "model,N,A,C" > followup_results.csv

# yolo11s pretrain (synth-only-s)
rm -rf $RUNS/s_pre; $YOLO detect train model=yolo11s.pt $Ss data=cycle2_data/d_synth_dvb.yaml project=$RUNS name=s_pre exist_ok=True > fs_pre.log 2>&1
echo "synth-only,s,$(best s_pre)," >> followup_results.csv
for N in 100 200 400; do
  rm -rf $RUNS/s_A${N} $RUNS/s_C${N}
  $YOLO detect train model=yolo11s.pt $Ss data=cycle2_data/h_A${N}.yaml project=$RUNS name=s_A${N} exist_ok=True > fs_A${N}.log 2>&1
  $YOLO detect train model=$RUNS/s_pre/weights/best.pt $Ss data=cycle2_data/h_A${N}.yaml project=$RUNS name=s_C${N} exist_ok=True > fs_C${N}.log 2>&1
  echo "yolo11s,$N,$(best s_A${N}),$(best s_C${N})" >> followup_results.csv
done
# yolo11l: N=100 이미 있음, 200/400 (l_pretrain 재사용)
echo "yolo11l,100,0.4285,0.5382" >> followup_results.csv
for N in 200 400; do
  rm -rf $RUNS/l_A${N} $RUNS/l_C${N}
  $YOLO detect train model=yolo11l.pt $Ls data=cycle2_data/h_A${N}.yaml project=$RUNS name=l_A${N} exist_ok=True > fl_A${N}.log 2>&1
  $YOLO detect train model=$RUNS/l_pretrain/weights/best.pt $Ls data=cycle2_data/h_A${N}.yaml project=$RUNS name=l_C${N} exist_ok=True > fl_C${N}.log 2>&1
  echo "yolo11l,$N,$(best l_A${N}),$(best l_C${N})" >> followup_results.csv
done
echo FOLLOWUP_DONE > followup_done.txt
