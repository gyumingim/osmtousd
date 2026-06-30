#!/bin/bash
cd /home/karma/OSMtoUSD/poc_city_render
/home/karma/OSMtoUSD/drone_det/venv/bin/python run_sweep7.py > sweep7.log 2>&1
echo "SWEEP7_DONE" > sweep7_done.txt
