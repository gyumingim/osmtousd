#!/bin/bash
cd /home/karma/OSMtoUSD/poc_city_render
YOLO=/home/karma/OSMtoUSD/drone_det/venv/bin/yolo
PY=/home/karma/OSMtoUSD/drone_det/venv/bin/python
RUNS=/home/karma/OSMtoUSD/poc_city_render/runs
# 1) 합성-only 재학습 (6종 다양화), aug+1280
rm -rf $RUNS/so_6drone
$YOLO detect train model=yolo11s.pt data=cycle2_data/d_synth_dvb.yaml imgsz=1280 batch=4 \
  epochs=120 patience=30 cache=False workers=4 device=0 seed=0 \
  mosaic=1.0 close_mosaic=15 mixup=0.15 copy_paste=0.3 hsv_h=0.02 hsv_s=0.8 hsv_v=0.5 \
  degrees=10 translate=0.15 scale=0.6 fliplr=0.5 erasing=0.4 \
  project=$RUNS name=so_6drone exist_ok=True > so_6drone.log 2>&1
sleep 15
# 2) pose 재학습 (6종, 더 많은 데이터)
rm -rf $RUNS/pose1
$YOLO pose train model=yolo11s-pose.pt data=dataset_pose/data.yaml imgsz=1280 batch=4 \
  epochs=150 patience=40 cache=False workers=4 device=0 seed=0 fliplr=0.0 \
  mosaic=0.5 close_mosaic=20 hsv_s=0.6 hsv_v=0.4 translate=0.1 scale=0.4 \
  project=$RUNS name=pose1 exist_ok=True > pose1b.log 2>&1
sleep 15
# 3) 결과 집계
$PY -c "
import csv
r=list(csv.DictReader(open('runs/so_6drone/results.csv')))
m=max(float(x['metrics/mAP50(B)']) for x in r)
print(f'합성only 6종 aug+1280 -> dvb: mAP {m:.3f} (vs 2종 0.211)')" > track2_result.txt 2>&1
$PY pnp_e2e.py 2>&1 | grep -E "오차|SUMMARY" >> track2_result.txt 2>&1
echo "TRACK2_DONE" > track2_done.txt
