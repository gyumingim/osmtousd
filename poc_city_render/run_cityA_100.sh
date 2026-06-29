#!/bin/bash
# A수정(시부야복원+거리/각도/색) 검증용 100장: 10런×10프레임. 런마다 모델·HDRI·카메라각 달라 배경 다양.
# 각 런=fresh Isaac세션(freeze 회피: 10프레임<<23임계). RUN=0이 dataset_v1 clear, 1~9 append.
ISAAC=/home/karma/isaacsim/_build/linux-x86_64/release/python.sh
GEN=/home/karma/OSMtoUSD/poc_city_render/gen_v1_dataset.py
POC=/home/karma/OSMtoUSD/poc_city_render
for R in $(seq 0 9); do
  RUN=$R N_SEQ=5 RAW=1 $ISAAC $GEN > $POC/stdout_cA_$R.log 2>&1
  echo "RUN $R: $(grep '완료:' $POC/run_v1_$R.log 2>/dev/null | tail -1)"
done
echo "TOTAL jpg: $(ls $POC/dataset_v1/images/*.jpg 2>/dev/null | wc -l)"
echo CITYA_100_DONE > $POC/cityA_done.txt
