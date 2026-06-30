#!/bin/bash
cd /home/karma/OSMtoUSD/poc_city_render
/home/karma/OSMtoUSD/drone_det/venv/bin/python run_sweep9.py > sweep9.log 2>&1
echo "SWEEP9_DONE" > sweep9_done.txt
