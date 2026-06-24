#!/bin/bash
# 슈퍼컴 노드 환경 점검·설정 (TODO 2-A)
# job_submit.sh에서 source. 헤드리스 렌더링 전제.

# Isaac Sim headless 렌더 설정
export OMNI_KIT_ALLOW_ROOT=1
export ACCEPT_EULA=Y
export PRIVACY_CONSENT=Y
# 디스플레이 없는 노드: EGL/오프스크린 렌더
export DISPLAY="${DISPLAY:-}"

ISAAC_ROOT="${ISAAC_ROOT:-$HOME/isaacsim}"
ISAAC_PY="$ISAAC_ROOT/_build/linux-x86_64/release/python.sh"

echo "[env] ISAAC_ROOT=$ISAAC_ROOT"

# GPU 가용성 확인
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader
else
  echo "[env][경고] nvidia-smi 없음 — GPU 노드인지 확인 필요"
fi

# Isaac python 런타임 확인
if [[ ! -x "$ISAAC_PY" ]]; then
  echo "[env][오류] Isaac python 없음: $ISAAC_PY"
  exit 1
fi

# 에셋 서버 접근 확인 (실모델 차량/사람 스트리밍에 필요)
if curl -sI --max-time 8 \
    https://omniverse-content-production.s3.us-west-2.amazonaws.com \
    >/dev/null 2>&1; then
  echo "[env] 에셋 서버 접근 OK"
else
  echo "[env][경고] 에셋 서버 접근 불가 — 실모델 에셋 캐시 필요"
fi

echo "[env] 환경 점검 완료"
