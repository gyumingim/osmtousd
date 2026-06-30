#!/bin/bash
cd /home/karma/OSMtoUSD/poc_city_render
YOLO=/home/karma/OSMtoUSD/drone_det/venv/bin/yolo
RUNS=/home/karma/OSMtoUSD/poc_city_render/runs
rm -rf $RUNS/pose1
$YOLO pose train model=yolo11s-pose.pt data=dataset_pose/data.yaml imgsz=1280 batch=4 \
  epochs=150 patience=40 cache=False workers=4 device=0 seed=0 fliplr=0.0 \
  mosaic=0.5 close_mosaic=20 hsv_s=0.6 hsv_v=0.4 translate=0.1 scale=0.4 \
  project=$RUNS name=pose1 exist_ok=True > pose1.log 2>&1
echo "POSE_DONE" > pose_done.txt
