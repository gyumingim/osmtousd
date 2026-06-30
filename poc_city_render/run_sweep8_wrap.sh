#!/bin/bash
cd /home/karma/OSMtoUSD/poc_city_render
/home/karma/OSMtoUSD/drone_det/venv/bin/python run_sweep8.py > sweep8.log 2>&1
echo "SWEEP8_DONE" > sweep8_done.txt
