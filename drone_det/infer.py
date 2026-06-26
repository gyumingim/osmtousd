"""infer.py — 학습된 드론 탐지기로 추론/검증.

사용법:
  venv/bin/python infer.py            # val셋 mAP 측정 + 샘플 6장 예측 저장
  venv/bin/python infer.py <경로>     # 임의 이미지/폴더 추론 → 박스 그려 저장
출력: runs/predict/ 에 박스 그려진 이미지.
"""
import os
import sys
import glob
from ultralytics import YOLO

ROOT = os.path.dirname(os.path.abspath(__file__))
WEIGHTS = os.path.join(ROOT, "runs", "drone_y11n", "weights", "best.pt")
OUT = os.path.join(ROOT, "runs", "predict")


def main():
    if not os.path.exists(WEIGHTS):
        sys.exit(f"학습된 가중치 없음: {WEIGHTS} (먼저 train.py 실행)")
    model = YOLO(WEIGHTS)

    if len(sys.argv) > 1:                          # 사용자 지정 이미지/폴더
        src = sys.argv[1]
        model.predict(src, save=True, project=OUT, name="user",
                      exist_ok=True, conf=0.25)
        print(f"결과 저장: {os.path.join(OUT, 'user')}")
        return

    # 인자 없으면: val 정량 검증 + 샘플 예측
    m = model.val(data=os.path.join(ROOT, "data", "data.yaml"),
                  project=OUT, name="val", exist_ok=True)
    print(f"\n=== val 성능 ===\n  mAP50    = {m.box.map50:.4f}"
          f"\n  mAP50-95 = {m.box.map:.4f}"
          f"\n  precision= {m.box.mp:.4f}\n  recall   = {m.box.mr:.4f}")
    samples = sorted(glob.glob(os.path.join(ROOT, "data", "images",
                                            "val", "*.jpg")))[:6]
    if samples:
        model.predict(samples, save=True, project=OUT, name="samples",
                      exist_ok=True, conf=0.25)
        print(f"샘플 예측 이미지: {os.path.join(OUT, 'samples')}")


if __name__ == "__main__":
    main()
