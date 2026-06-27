#!/bin/bash
cd /home/karma/OSMtoUSD/poc_city_render
YOLO=/home/karma/OSMtoUSD/drone_det/venv/bin/yolo
PY=/home/karma/OSMtoUSD/drone_det/venv/bin/python
RUNS=/home/karma/OSMtoUSD/poc_city_render/runs
A="imgsz=1280 batch=4 epochs=120 patience=30 cache=False workers=4 device=0 seed=0 mosaic=1.0 close_mosaic=15 mixup=0.15 copy_paste=0.3 hsv_h=0.02 hsv_s=0.8 hsv_v=0.5 degrees=10 translate=0.15 scale=0.6 fliplr=0.5 erasing=0.4"
rm -rf $RUNS/b1_comp $RUNS/b1_comp_synth
$YOLO detect train model=yolo11s.pt data=cycle2_data/d_composite.yaml name=b1_comp project=$RUNS exist_ok=True $A > b1_comp.log 2>&1
sleep 15
$YOLO detect train model=yolo11s.pt data=cycle2_data/d_comp_synth.yaml name=b1_comp_synth project=$RUNS exist_ok=True $A > b1_comp_synth.log 2>&1
sleep 5
$PY -c "
import csv
for r in ['b1_comp','b1_comp_synth']:
    d=list(csv.DictReader(open(f'runs/{r}/results.csv')))
    print(f'{r}: mAP {max(float(x[\"metrics/mAP50(B)\"]) for x in d):.3f}')" > b1_result.txt 2>&1
echo B1_DONE > b1_done.txt
