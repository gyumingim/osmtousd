"""
배치 렌더링 파이프라인 (TODO 2-B)

5종 시나리오를 순차 실행(실패 시 재시도) 후 품질검증 + 패키징까지 일괄.
각 시나리오는 자체 오케스트레이터(scenarios/scenario_0X_*.py).

Env:
    NUM_FRAMES   시나리오별 프레임 수 (기본 시나리오 스크립트 기본값)
    SKIP_RENDER  "1"이면 렌더 건너뛰고 검증·패키징만 (기존 산출물 대상)
    MAX_RETRY    시나리오 실패 시 재시도 횟수 (기본 1)

Usage:
    python3 pipeline/batch_render.py
    SKIP_RENDER=1 python3 pipeline/batch_render.py   # 후처리만
"""
import os
import subprocess
import sys
import time

ROOT = "/home/karma/OSMtoUSD"
SCENARIOS = [
    "scenarios/scenario_01_weather.py",
    "scenarios/scenario_02_amr.py",
    "scenarios/scenario_03_vru.py",
    "scenarios/scenario_04_v2x.py",
    "scenarios/scenario_05_collision.py",
]
MAX_RETRY = int(os.environ.get("MAX_RETRY", "1"))


def run_scenario(script):
    """시나리오 1개 실행 (재시도 포함) → 성공여부."""
    for attempt in range(1, MAX_RETRY + 2):
        print(f"\n[배치] {script} (시도 {attempt})", flush=True)
        t0 = time.time()
        rc = subprocess.run([sys.executable, os.path.join(ROOT, script)],
                            cwd=ROOT).returncode
        dt = time.time() - t0
        if rc == 0:
            print(f"[배치] {script} 성공 ({dt:.0f}s)", flush=True)
            return True
        print(f"[배치] {script} 실패 rc={rc} ({dt:.0f}s)", flush=True)
    return False


def main():
    report = {}
    if os.environ.get("SKIP_RENDER") != "1":
        print(f"=== 배치 렌더링: {len(SCENARIOS)}개 시나리오 ===")
        for s in SCENARIOS:
            report[s] = "OK" if run_scenario(s) else "FAIL"
    else:
        print("=== SKIP_RENDER: 렌더 생략, 검증·패키징만 ===")

    # 후처리: 품질검증 + 패키징
    print("\n=== 품질 검증 ===", flush=True)
    qc = subprocess.run([sys.executable, "pipeline/quality_check.py"],
                        cwd=ROOT).returncode
    print("\n=== 패키징 ===", flush=True)
    pk = subprocess.run([sys.executable, "pipeline/packager.py"],
                        cwd=ROOT).returncode

    print("\n=== 배치 파이프라인 완료 ===")
    for s, st in report.items():
        print(f"  {os.path.basename(s)}: {st}")
    print(f"  품질검증: {'OK' if qc == 0 else 'WARN'}")
    print(f"  패키징: {'OK' if pk == 0 else 'FAIL'}")
    failed = [s for s, st in report.items() if st == "FAIL"] or pk != 0
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
