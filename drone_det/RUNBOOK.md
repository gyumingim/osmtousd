# RUNBOOK — GPU 비면 바로 실행할 실험 (방법론 검증)

> GPU가 시뮬 AI에게서 풀리면, 아래를 **순서대로** 돌려 방법론을 숫자로 검증.
> 전부 `cd ~/OSMtoUSD/drone_det` 후 `venv/bin/python` 으로.
> 결과는 STATUS.md / METHODOLOGY.md 5절(가설표)에 기록.

## 0. GPU 비었는지 확인 (충돌 방지)
```bash
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
# 시뮬/다른 프로세스가 쓰면 대기. (8GB 공유 → 동시 학습 금지)
```

## 실험 1 — 해상도: 1280이 초소형 미탐을 줄이나 ⭐
가설: 640→1280이면 <32px recall↑ (데이터 38.6%가 small).
```bash
# 베이스(640)는 이미 있음: runs/drone_y11n  → eval로 크기별 recall 기록
venv/bin/python eval.py            # 640 기준선

# 1280 재학습 (train.py는 IMGSZ 환경변수 지원)
EPOCHS=50 BATCH=8 IMGSZ=1280 venv/bin/python train.py   # 8GB라 batch↓
venv/bin/python eval.py            # 1280 크기별 recall → 640과 비교
```
판정: `<16px`/`16~32px` recall 이 1280에서 올라가면 가설 PASS.

## 실험 2 — 증강(=DR 프록시)이 일반화 올리나
가설: 강한 증강이 도메인 변화에 강해짐(sim→real 대비 연습).
```bash
# train.py에 증강 파라미터 추가해 비교(약 vs 강). Ultralytics 기본 증강 on.
# 약: mosaic=0 mixup=0 / 강: mosaic=1 mixup=0.1 copy_paste=0.1 hsv 확대
# (train.py model.train(...)에 인자 추가 후) 두 모델 eval 비교
```

## 실험 3 — frame-dynamics 효과 (영상 필요 → 시퀀스 데이터 나온 뒤)
가설: 광류/프레임차분 입력이 오탐↓·recall↑.
```bash
# frame_dynamics.py 로 시퀀스 → 3채널(차분/광류) 생성 → 별 모델 학습 후 비교
venv/bin/python frame_dynamics.py   # CPU 검증은 이미 PASS
```

## 실험 4 — P2 헤드(소형객체) 효과
⚠️ `yolo11-p2.yaml`은 ultralytics에 **없음**(확인됨). 사용 가능: `yolov8-p2.yaml`,
`yolo26-p2.yaml`. → yolo26-p2로 하거나 yolo11에 P2 헤드 cfg를 직접 작성.
```bash
EPOCHS=50 BATCH=8 IMGSZ=1280 venv/bin/python -c "from ultralytics import YOLO; \
  YOLO('yolo26-p2.yaml').train(data='data/data.yaml', epochs=50, imgsz=1280, batch=8)"
# → small mAP를 P2 없는 모델과 eval.py 크기별 recall로 비교
```

## 공개벤치 평가 (Sim-to-Real 지표, PDF 30%)
```bash
# DUT Anti-UAV / Anti-UAV 를 YOLO 포맷으로 받아 data.yaml 지정 후:
venv/bin/python -c "from ultralytics import YOLO; \
  YOLO('runs/drone_y11n/weights/best.pt').val(data='BENCH/data.yaml')"
```

---
## 산출물 흐름
```
실험 결과 → METHODOLOGY.md 5절 갱신 → 'sim 생성 주문' 도출 → DATA_SPEC.md 갱신 → AI-2
```
