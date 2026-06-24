#!/bin/bash
# 엔드투엔드 파이프라인 (공통 인프라)
# USD 생성 → 5종 시나리오 렌더 → 품질검증 → 패키징 → 웹 포털 기동
#
# Usage:
#   bash pipeline/full_pipeline.sh            # 전체
#   NUM_FRAMES=100 bash pipeline/full_pipeline.sh
#   SKIP_USD=1 SKIP_RENDER=1 bash pipeline/full_pipeline.sh   # 후처리+웹만

set -uo pipefail
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
ISAAC_PY="${ISAAC_PY:-$HOME/isaacsim/_build/linux-x86_64/release/python.sh}"
cd "$PROJECT"

# 1. USD 생성 (OSM/Vworld → gumi.usda + 텍스처 + Isaac 후처리)
if [[ "${SKIP_USD:-0}" != "1" ]]; then
  echo "=== [1/4] USD 생성 ==="
  python3 main.py || echo "[경고] USD 생성 스킵/실패 (기존 gumi.usda 사용)"
fi

# 2. 시나리오 배치 렌더 + 3. 검증 + 4. 패키징 (batch_render가 일괄)
echo "=== [2-4/4] 배치 렌더 → 검증 → 패키징 ==="
python3 pipeline/batch_render.py
RC=$?

echo ""
echo "=== 파이프라인 종료 (rc=$RC) ==="
echo "포털 실행:  python3 -m uvicorn web.backend.main:app --port 8000"
exit $RC
