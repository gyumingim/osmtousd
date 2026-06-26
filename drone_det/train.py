"""train.py — YOLO11n 드론 탐지기 학습.

EPOCHS, BATCH, IMGSZ 환경변수로 조절. 결과는 runs/drone_y11n/.
"""
import os
from ultralytics import YOLO

ROOT = os.path.dirname(os.path.abspath(__file__))
EPOCHS = int(os.environ.get("EPOCHS", "50"))
BATCH = int(os.environ.get("BATCH", "16"))
IMGSZ = int(os.environ.get("IMGSZ", "640"))


def main():
    model = YOLO("yolo11n.pt")              # COCO 사전학습 → 드론으로 fine-tune
    model.train(
        data=os.path.join(ROOT, "data", "data.yaml"),
        epochs=EPOCHS, imgsz=IMGSZ, batch=BATCH,
        project=os.path.join(ROOT, "runs"), name="drone_y11n",
        exist_ok=True, verbose=True,
    )


if __name__ == "__main__":
    main()
