#!/bin/bash
POC=/home/karma/OSMtoUSD/poc_city_render
ISAAC=/home/karma/isaacsim/_build/linux-x86_64/release/python.sh
WLOG=$POC/mcbench_watchdog.log; STOP=$POC/mcbench.stop; rm -f $STOP; : > $WLOG
( MIN=99999
  while [ ! -f $STOP ]; do
    A=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
    [ "$A" -lt "$MIN" ] && MIN=$A
    [ "$A" -lt 1200 ] && { pkill -9 -f isaacsim; echo "KILL lowmem $A $(date +%H:%M:%S)" >> $WLOG; }
    echo "$(date +%H:%M:%S) avail=$A min=$MIN" >> $WLOG; sleep 1.5
  done ) &
WP=$!
echo "=== NCAM=1 (단일카메라) ==="
NCAM=1 KIMG=18 $ISAAC $POC/multicam_bench.py 2>&1 | grep -E "RESULT|Error|Traceback|bad alloc" | tail -5
echo "=== NCAM=3 (멀티카메라) ==="
NCAM=3 KIMG=18 $ISAAC $POC/multicam_bench.py 2>&1 | grep -E "RESULT|Error|Traceback|bad alloc" | tail -5
touch $STOP; kill $WP 2>/dev/null
echo "min avail 동안: $(grep -o 'min=[0-9]*' $WLOG | tail -1)MB"
echo MCBENCH_DONE
