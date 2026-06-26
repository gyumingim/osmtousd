#!/bin/bash
# RUN 0..5 순차 실행(각 새 Isaac 프로세스=고정카메라). 동시 실행 방지.
cd /home/karma/isaacsim || exit 1
for RUN in $(seq 0 39); do
  # 이전 Isaac 완전 종료 대기(중복 방지)
  while nvidia-smi --query-compute-apps=process_name --format=csv,noheader 2>/dev/null | grep -qi isaacsim; do sleep 2; done
  echo "=== RUN $RUN 시작 ==="
  RUN=$RUN ./_build/linux-x86_64/release/python.sh /home/karma/OSMtoUSD/poc_city_render/gen_v1_dataset.py \
      > /home/karma/OSMtoUSD/poc_city_render/stdout_v1_$RUN.log 2>&1
  grep "완료" /home/karma/OSMtoUSD/poc_city_render/run_v1_$RUN.log 2>/dev/null
done
echo "=== ALL RUNS DONE ==="
echo "총 양성: $(grep -hl . /home/karma/OSMtoUSD/poc_city_render/dataset_v1/labels/*.txt 2>/dev/null | xargs -r grep -l '^0 ' 2>/dev/null | wc -l) / $(ls /home/karma/OSMtoUSD/poc_city_render/dataset_v1/images/ | wc -l)"
