#!/bin/bash
# 안전 생성: 메모리 워치독 + 세션분할. 14GB RAM 프리즈 재발 방지.
# 워치독이 MemAvailable < FLOOR_MB 감지하면 Isaac만 즉시 kill(머신 안 멈춤).
# 세션마다 Isaac 재시작 → RAM 완전 회수. 단일 인스턴스(동시실행X).
ISAAC=/home/karma/isaacsim/_build/linux-x86_64/release/python.sh
GEN=/home/karma/OSMtoUSD/poc_city_render/gen_v1_dataset.py
POC=/home/karma/OSMtoUSD/poc_city_render
FLOOR_MB=${FLOOR_MB:-1500}     # 이 밑이면 Isaac kill (스왑 폭주 전 차단)
NSEQ=${NSEQ:-125}              # 세션당 250장(=NSEQ*2)
RUN_START=${RUN_START:-0}
RUN_END=${RUN_END:-0}
WLOG=$POC/watchdog.log
STOP=$POC/watchdog.stop
rm -f $STOP $POC/WATCHDOG_KILLED

# --- 워치독 백그라운드 ---
( echo "$(date +%H:%M:%S) WATCHDOG start floor=${FLOOR_MB}MB" > $WLOG
  MIN=99999
  while [ ! -f $STOP ]; do
    AVAIL=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
    [ "$AVAIL" -lt "$MIN" ] && MIN=$AVAIL
    echo "$(date +%H:%M:%S) avail=${AVAIL}MB min=${MIN}MB" >> $WLOG
    if [ "$AVAIL" -lt "$FLOOR_MB" ]; then
      echo "$(date +%H:%M:%S) !!! LOWMEM ${AVAIL}<${FLOOR_MB} -> KILL Isaac" >> $WLOG
      pkill -9 -f isaacsim 2>/dev/null
      pkill -9 -f gen_v1_dataset 2>/dev/null
      touch $POC/WATCHDOG_KILLED
    fi
    sleep 1.5
  done
  echo "$(date +%H:%M:%S) WATCHDOG stop min=${MIN}MB" >> $WLOG ) &
WPID=$!
trap "touch $STOP; kill $WPID 2>/dev/null" EXIT

# --- 세션 순차 실행 ---
for R in $(seq $RUN_START $RUN_END); do
  B0=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
  echo "=== SESSION RUN=$R NSEQ=$NSEQ (avail ${B0}MB) $(date +%H:%M:%S) ==="
  RUN=$R N_SEQ=$NSEQ $ISAAC $GEN > $POC/sess_$R.log 2>&1
  if [ -f $POC/WATCHDOG_KILLED ]; then
    echo "!!! ABORTED by watchdog at RUN=$R (메모리 부족). 중단."
    break
  fi
  N=$(ls $POC/dataset_v1/images/*.jpg 2>/dev/null | wc -l)
  echo "RUN $R done. total imgs=$N"
  sleep 4   # RAM 회수 대기
done
touch $STOP; kill $WPID 2>/dev/null
echo "min avail during run: $(grep -o 'min=[0-9]*MB' $WLOG | tail -1)"
echo "SAFE_GEN_DONE total=$(ls $POC/dataset_v1/images/*.jpg 2>/dev/null | wc -l)"
