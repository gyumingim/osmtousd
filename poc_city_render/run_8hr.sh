#!/bin/bash
# 8시간 자율: 최종 생성기 + yolo11l(라지, VRAM안전 batch=2) 최대정확도.
# Phase A 생성(~2560) → Phase B yolo11l: 합성-only + 합성pretrain→실FT(C) + real-only(A) on dvb.
# 결과 증분기록(부분결과 보존). gen/train 직렬(머신다운 방지). VRAM 5.8/8GB.
POC=/home/karma/OSMtoUSD/poc_city_render
PY=/home/karma/OSMtoUSD/drone_det/venv/bin/python
YOLO=/home/karma/OSMtoUSD/drone_det/venv/bin/yolo
RUNS=$POC/runs
cd $POC
A="imgsz=1280 batch=2 epochs=60 patience=15 cache=False workers=3 device=0 mosaic=1.0 close_mosaic=12 mixup=0.1 hsv_s=0.7 hsv_v=0.4 translate=0.1 scale=0.5 fliplr=0.5 seed=0"
best() { $PY -c "import csv;r=list(csv.DictReader(open('runs/$1/results.csv')));print(round(max(float(x['metrics/mAP50(B)']) for x in r),4))" 2>/dev/null; }

# Phase A: 최종 생성기로 ~2560 synth (16런)
cd /home/karma/isaacsim
for RUN in $(seq 0 15); do
  while nvidia-smi --query-compute-apps=process_name --format=csv,noheader 2>/dev/null | grep -qi isaac; do sleep 2; done
  RUN=$RUN ./_build/linux-x86_64/release/python.sh $POC/gen_v1_dataset.py > $POC/stdout_gen_$RUN.log 2>&1
  sleep 8
done
cd $POC
$PY - <<'PYEOF'
import glob,os,shutil,random
random.seed(0)
shutil.rmtree("cycle2_data/synth",ignore_errors=True)
os.makedirs("cycle2_data/synth/images");os.makedirs("cycle2_data/synth/labels")
n=0
for img in sorted(glob.glob("dataset_v1/images/*.jpg")):
    lf="dataset_v1/labels/"+os.path.basename(img).replace(".jpg",".txt")
    if os.path.exists(lf) and os.path.getsize(lf)>0:
        bn=os.path.basename(img);shutil.copy(img,"cycle2_data/synth/images/"+bn)
        shutil.copy(lf,"cycle2_data/synth/labels/"+bn.replace(".jpg",".txt"));n+=1
print("synth",n)
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
print("test3",build(sorted(glob.glob(f"{DVB}/valid/images/*"))+sorted(glob.glob(f"{DVB}/test/images/*")),"test3"))
pool=[i for i in sorted(glob.glob(f"{DVB}/train/images/*")) if has1(i.replace("/images/","/labels/").rsplit(".",1)[0]+".txt")]
random.shuffle(pool)
print("real3_100",build(pool[:100],"real3_100"))
AB=os.path.abspath("cycle2_data")
open("cycle2_data/d_synth_dvb.yaml","w").write(f"path: {AB}\ntrain: synth/images\nval: test3/images\nnc: 1\nnames: ['drone']\n")
open("cycle2_data/h_A100.yaml","w").write(f"path: {AB}\ntrain: real3_100/images\nval: test3/images\nnc: 1\nnames: ['drone']\n")
PYEOF
echo "=== 8HR result (yolo11l 1280 batch2) ===" > result_8hr.txt

# B0: real-only baseline (A, 빠름 먼저)
rm -rf $RUNS/l_A100; $YOLO detect train model=yolo11l.pt $A data=cycle2_data/h_A100.yaml project=$RUNS name=l_A100 exist_ok=True > l_A100.log 2>&1
echo "A(real-only N100): $(best l_A100)" >> result_8hr.txt; echo A_DONE > stage8_A.txt

# B1: 합성 pretrain (synth-only mAP도 = best)
rm -rf $RUNS/l_pretrain; $YOLO detect train model=yolo11l.pt $A data=cycle2_data/d_synth_dvb.yaml project=$RUNS name=l_pretrain exist_ok=True > l_pretrain.log 2>&1
echo "synth-only(pretrain best): $(best l_pretrain)" >> result_8hr.txt; echo PRE_DONE > stage8_pre.txt

# B2: pretrain → real FT (C, 핵심 deliverable)
rm -rf $RUNS/l_C100; $YOLO detect train model=$RUNS/l_pretrain/weights/best.pt imgsz=1280 batch=2 epochs=60 patience=15 cache=False workers=3 device=0 mosaic=1.0 close_mosaic=12 seed=0 data=cycle2_data/h_A100.yaml project=$RUNS name=l_C100 exist_ok=True > l_C100.log 2>&1
echo "C(pretrain→FT N100): $(best l_C100)" >> result_8hr.txt; echo C_DONE > stage8_C.txt
echo "8HR_DONE" > done_8hr.txt
