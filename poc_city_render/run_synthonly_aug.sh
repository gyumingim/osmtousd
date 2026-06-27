#!/bin/bash
cd /home/karma/OSMtoUSD/poc_city_render
YOLO=/home/karma/OSMtoUSD/drone_det/venv/bin/yolo
RUNS=/home/karma/OSMtoUSD/poc_city_render/runs
# 강증강 synth-only (모양 일반화 유도) → dvb test
rm -rf $RUNS/so_aug
$YOLO detect train model=yolo11s.pt data=cycle2_data/d_synth_dvb.yaml imgsz=640 batch=16 \
  epochs=120 patience=30 cache=False workers=6 device=0 seed=0 \
  mosaic=1.0 close_mosaic=15 mixup=0.15 copy_paste=0.3 hsv_h=0.02 hsv_s=0.8 hsv_v=0.5 \
  degrees=10 translate=0.15 scale=0.6 fliplr=0.5 erasing=0.4 \
  project=$RUNS name=so_aug exist_ok=True > so_aug.log 2>&1
echo "SO_AUG_DONE" > so_aug_done.txt
