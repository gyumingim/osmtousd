#!/bin/bash
cd /home/karma/OSMtoUSD/poc_city_render
/home/karma/OSMtoUSD/drone_det/venv/bin/python run_sweep6.py > sweep6.log 2>&1
echo "SWEEP6_DONE" > sweep6_done.txt
