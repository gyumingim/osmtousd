#!/bin/bash
cd /home/karma/isaacsim
for RUN in $(seq 0 119); do
  while nvidia-smi --query-compute-apps=process_name --format=csv,noheader 2>/dev/null | grep -qi isaac; do sleep 2; done
  RUN=$RUN ./_build/linux-x86_64/release/python.sh /home/karma/OSMtoUSD/poc_city_render/gen_v1_dataset.py > /home/karma/OSMtoUSD/poc_city_render/stdout_gen_$RUN.log 2>&1
  sleep 9
done
cd /home/karma/OSMtoUSD/poc_city_render
PY=/home/karma/OSMtoUSD/drone_det/venv/bin/python
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
print(n)" > big_synthcount.txt
YOLO=/home/karma/OSMtoUSD/drone_det/venv/bin/yolo
RUNS=/home/karma/OSMtoUSD/poc_city_render/runs
rm -rf $RUNS/so_big
$YOLO detect train model=yolo11s.pt data=cycle2_data/d_synth_dvb.yaml imgsz=1280 batch=4 \
  epochs=120 patience=30 cache=False workers=4 device=0 seed=0 \
  mosaic=1.0 close_mosaic=15 mixup=0.15 copy_paste=0.3 hsv_h=0.02 hsv_s=0.8 hsv_v=0.5 \
  degrees=10 translate=0.15 scale=0.6 fliplr=0.5 erasing=0.4 \
  project=$RUNS name=so_big exist_ok=True > so_big.log 2>&1
$PY -c "import csv;r=list(csv.DictReader(open('runs/so_big/results.csv')));print('합성only 대량 -> dvb: mAP %.3f (synth %s장, vs 322장 0.245)'%(max(float(x['metrics/mAP50(B)']) for x in r), open('big_synthcount.txt').read().strip()))" > big_result.txt 2>&1
echo BIG_DONE > big_done.txt
