#!/bin/bash
cd /home/karma/OSMtoUSD/poc_city_render
/home/karma/OSMtoUSD/drone_det/venv/bin/python run_sweep11.py > sweep11.log 2>&1
echo "SWEEP11_DONE" > sweep11_done.txt
