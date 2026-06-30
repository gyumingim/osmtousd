#!/bin/bash
cd /home/karma/OSMtoUSD/poc_city_render
/home/karma/OSMtoUSD/drone_det/venv/bin/python run_sweep10.py > sweep10.log 2>&1
echo "SWEEP10_DONE" > sweep10_done.txt
