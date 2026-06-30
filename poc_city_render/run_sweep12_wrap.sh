#!/bin/bash
cd /home/karma/OSMtoUSD/poc_city_render
/home/karma/OSMtoUSD/drone_det/venv/bin/python run_sweep12.py > sweep12.log 2>&1
echo "SWEEP12_DONE" > sweep12_done.txt
