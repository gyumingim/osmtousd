#!/bin/bash
POC=/home/karma/OSMtoUSD/poc_city_render; YOLO=/home/karma/OSMtoUSD/drone_det/venv/bin/yolo; RUNS=$POC/runs
PY=/home/karma/OSMtoUSD/drone_det/venv/bin/python; cd $POC
Ls="imgsz=1280 batch=2 epochs=60 patience=15 cache=False workers=3 device=0 mosaic=1.0 close_mosaic=12 seed=0"
best(){ $PY -c "import csv;r=list(csv.DictReader(open('runs/$1/results.csv')));print(round(max(float(x['metrics/mAP50(B)']) for x in r),4))" 2>/dev/null; }
# C200 (l_A200 이미 있음)
rm -rf $RUNS/l_C200; $YOLO detect train model=$RUNS/l_pretrain/weights/best.pt $Ls data=cycle2_data/h_A200.yaml project=$RUNS name=l_C200 exist_ok=True > fl_C200.log 2>&1
echo "yolo11l,200,$(best l_A200),$(best l_C200)" >> followup_results.csv
# A400, C400
rm -rf $RUNS/l_A400; $YOLO detect train model=yolo11l.pt $Ls data=cycle2_data/h_A400.yaml project=$RUNS name=l_A400 exist_ok=True > fl_A400.log 2>&1
rm -rf $RUNS/l_C400; $YOLO detect train model=$RUNS/l_pretrain/weights/best.pt $Ls data=cycle2_data/h_A400.yaml project=$RUNS name=l_C400 exist_ok=True > fl_C400.log 2>&1
echo "yolo11l,400,$(best l_A400),$(best l_C400)" >> followup_results.csv
echo FOLLOWUP_DONE > followup_done.txt
