#!/bin/bash
# 볼륨 스케일링 실험: 2000/5000/10000 합성이미지 → 합성-only 인식률(dvb) → 곡선
# 현실색(A3)+6종드론+증강+1280. 토큰무관. gen과 train 직렬(동시X=머신다운방지).
PY=/home/karma/OSMtoUSD/drone_det/venv/bin/python
YOLO=/home/karma/OSMtoUSD/drone_det/venv/bin/yolo
RUNS=/home/karma/OSMtoUSD/poc_city_render/runs
POC=/home/karma/OSMtoUSD/poc_city_render
echo "n,mAP50" > $POC/vol_results.csv

gen_range() {
  cd /home/karma/isaacsim
  for RUN in $(seq $1 $2); do
    while nvidia-smi --query-compute-apps=process_name --format=csv,noheader 2>/dev/null | grep -qi isaac; do sleep 2; done
    RUN=$RUN ./_build/linux-x86_64/release/python.sh $POC/gen_v1_dataset.py > $POC/stdout_gen_$RUN.log 2>&1
    sleep 9
  done
}

stage() {
  cd $POC
  $PY -c "
import glob,os,shutil
shutil.rmtree('cycle2_data/synth',ignore_errors=True)
os.makedirs('cycle2_data/synth/images');os.makedirs('cycle2_data/synth/labels')
n=0
for img in sorted(glob.glob('dataset_v1/images/*.jpg')):
    lf='dataset_v1/labels/'+os.path.basename(img).replace('.jpg','.txt')
    if os.path.exists(lf) and os.path.getsize(lf)>0:
        bn=os.path.basename(img);shutil.copy(img,'cycle2_data/synth/images/'+bn)
        shutil.copy(lf,'cycle2_data/synth/labels/'+bn.replace('.jpg','.txt'));n+=1
open('cur_n.txt','w').write(str(n))"
  rm -rf $RUNS/so_vol_$1
  $YOLO detect train model=yolo11s.pt data=cycle2_data/d_synth_dvb.yaml imgsz=1280 batch=4 \
    epochs=120 patience=30 cache=False workers=4 device=0 seed=0 \
    mosaic=1.0 close_mosaic=15 mixup=0.15 copy_paste=0.3 hsv_h=0.02 hsv_s=0.8 hsv_v=0.5 \
    degrees=10 translate=0.15 scale=0.6 fliplr=0.5 erasing=0.4 \
    project=$RUNS name=so_vol_$1 exist_ok=True > so_vol_$1.log 2>&1
  $PY -c "import csv;r=list(csv.DictReader(open('runs/so_vol_$1/results.csv')));m=max(float(x['metrics/mAP50(B)']) for x in r);n=open('cur_n.txt').read().strip();open('vol_results.csv','a').write(f'{n},{m:.4f}\n')"
  echo "STAGE $1 DONE" > $POC/vol_stage_$1.txt
}

gen_range 0 12;    stage 2000
gen_range 13 31;   stage 5000
gen_range 32 62;   stage 10000

$PY -c "
import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt,csv
r=list(csv.DictReader(open('$POC/vol_results.csv')))
ns=[322]+[int(x['n']) for x in r];ms=[0.245]+[float(x['mAP50']) for x in r]
plt.figure(figsize=(8,5))
plt.plot(ns,ms,'o-',color='#2e7d32',lw=2,ms=9)
for n,m in zip(ns,ms): plt.annotate(f'{m:.3f}\n({n})',(n,m),textcoords='offset points',xytext=(0,9),ha='center',fontweight='bold',fontsize=8)
plt.xscale('log');plt.xlabel('synthetic training images (log)');plt.ylabel('synth-only -> dvb mAP50 (ZERO real labels)')
plt.title('Does VOLUME break the synth-only plateau? (small drones)')
plt.grid(alpha=0.3);plt.tight_layout();plt.savefig('$POC/../results/synthonly_volume_curve.png',dpi=110)"
echo VOL_DONE > $POC/vol_done.txt
