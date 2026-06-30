#!/bin/bash
# 야간 자율: 생성완료 대기 → (Isaac 완전종료 확인) → 학습매트릭스. Isaac⊕학습 동시금지 준수.
POC=/home/karma/OSMtoUSD/poc_city_render
LOG=$POC/overnight.log
echo "$(date) overnight 시작. 생성완료 대기..." > $LOG
# 1) 생성 러너 종료 대기
until ! pgrep -f run_safe_gen >/dev/null 2>&1; do sleep 30; done
# 2) Isaac 프로세스 완전 소멸 대기(GPU/RAM 해제 보장)
until ! pgrep -f isaacsim >/dev/null 2>&1; do sleep 10; done
sleep 10
NIMG=$(ls $POC/dataset_v1/images/*.jpg 2>/dev/null | wc -l)
echo "$(date) 생성완료 ${NIMG}장. avail $(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)MB. 학습시작" >> $LOG
# 3) 학습
source /home/karma/OSMtoUSD/drone_det/venv/bin/activate
cd $POC
python train_eval_matrix.py >> $LOG 2>&1
echo "$(date) OVERNIGHT_DONE total=${NIMG}장 합성" >> $LOG
