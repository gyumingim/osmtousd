#!/bin/bash
# 슈퍼컴퓨팅센터 배치 잡 제출 템플릿 (TODO 2-A)
# 실제 GPU 노드 계정·SLURM 환경에서 사용. 로컬 검증 불가(인프라 의존).
#
# 사용:
#   sbatch supercomp/job_submit.sh
#   또는 시나리오 분할:  sbatch --array=1-5 supercomp/job_submit.sh

#SBATCH --job-name=osmtousd-render
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=12:00:00
#SBATCH --output=logs/render_%A_%a.out
#SBATCH --error=logs/render_%A_%a.err

set -euo pipefail

ISAAC_ROOT="${ISAAC_ROOT:-$HOME/isaacsim}"
PROJECT="${PROJECT:-$HOME/OSMtoUSD}"
ISAAC_PY="$ISAAC_ROOT/_build/linux-x86_64/release/python.sh"

cd "$PROJECT"
mkdir -p logs

# 환경 점검
source supercomp/env_setup.sh

# SLURM array면 시나리오 1개씩, 아니면 전체 배치
SCENARIOS=(
  scenarios/scenario_01_weather.py
  scenarios/scenario_02_amr.py
  scenarios/scenario_03_vru.py
  scenarios/scenario_04_v2x.py
  scenarios/scenario_05_collision.py
)

if [[ -n "${SLURM_ARRAY_TASK_ID:-}" ]]; then
  idx=$(( SLURM_ARRAY_TASK_ID - 1 ))
  echo "[SLURM] 시나리오 $idx: ${SCENARIOS[$idx]}"
  NUM_FRAMES="${NUM_FRAMES:-10000}" python3 "${SCENARIOS[$idx]}"
else
  echo "[SLURM] 전체 배치 (headless 렌더 → 검증 → 패키징)"
  NUM_FRAMES="${NUM_FRAMES:-10000}" python3 pipeline/batch_render.py
fi

echo "[SLURM] 잡 완료"
