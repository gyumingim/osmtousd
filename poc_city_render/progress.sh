#!/bin/bash
# 실시간 진행 — bash progress.sh (언제든)
cd /home/karma/OSMtoUSD/poc_city_render
V=../drone_det/venv/bin/python
echo "================ 자율 루프 진행 ================"
echo "[완료된 사이클 결과]"
for f in sweep3_results.csv sweep4_results.csv sweep5_results.csv; do
  [ -f "$f" ] && { echo "  $f:"; sed 's/^/    /' "$f"; }
done
echo ""
echo "[현재 학습]"
RUN=$(ps -eo args 2>/dev/null | grep "[y]olo detect train" | grep -oE "name=[A-Za-z0-9_]+" | head -1 | cut -d= -f2)
if [ -n "$RUN" ]; then
  CSV=runs/$RUN/results.csv
  if [ -f "$CSV" ]; then
    $V -c "
import csv
r=list(csv.DictReader(open('$CSV')))
e=int(r[-1]['epoch']); t=[float(x['time']) for x in r]
per=(t[-1]-t[0])/(len(t)-1) if len(t)>1 else 20
print(f'  실행중: $RUN | epoch {e}/120 ({100*e//120}%) | val mAP50 {float(r[-1][\"metrics/mAP50(B)\"]):.3f} | 이 학습 ~{(120-e)*per/60:.0f}분 남음')
"
  else echo "  실행중: $RUN (라벨 스캔/셋업 중)"; fi
else echo "  (학습 프로세스 없음 — 사이클 완료 또는 대기)"; fi
echo ""
echo "[GPU] $(nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null)"
# 진행 단계(sweep5: 8학습 = 4N x A/C)
done5=$(ls -d runs/de_A* runs/de_C* 2>/dev/null | wc -l)
grep -q SWEEP5_DONE sweep5.log 2>/dev/null && echo "[Cycle5] ✅ 전체 완료" || echo "[Cycle5] 학습 $done5/8 진행"
echo "================================================"
echo "git log: github.com/gyumingim/osmtousd (results/ 곡선·CSV)"
