#!/bin/bash
cd /home/karma/isaacsim
for RUN in $(seq 0 23); do
  while nvidia-smi --query-compute-apps=process_name --format=csv,noheader 2>/dev/null | grep -qi isaac; do sleep 2; done
  RUN=$RUN ./_build/linux-x86_64/release/python.sh /home/karma/OSMtoUSD/poc_city_render/gen_v1_dataset.py > /home/karma/OSMtoUSD/poc_city_render/stdout_gen_$RUN.log 2>&1
  sleep 10
done
echo "GEN6_DONE" > /home/karma/OSMtoUSD/poc_city_render/gen6_done.txt
