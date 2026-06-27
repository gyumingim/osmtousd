# drone_det — 영상 기반 드론 탐지기 (YOLO11)

안티드론(드론=표적) 탐지 모델. 공개 데이터로 베이스라인 학습 → 추후 합성데이터·시계열·엣지 확장.
독립 프로젝트 (KMIT·OSMtoUSD와 무관). 진행상황은 `STATUS.md`.

## ★ 핵심 결과 (합성데이터 가치 검증 — 상세: `FINDINGS.md`, 곡선: `../results/`)

**Isaac Sim 합성데이터가 드론탐지에 가치 있나? → 과제 regime(작은 원거리 드론)에서 깨끗하게 YES.**

- **과제 본질 입증** (drone-vs-bird, 48px 작은 드론): real만 0.34 → **합성 mix 0.66 (+0.32)** (N=50, 3시드)
- **시뮬 현실화** (맑은하늘·파란HDRI·과노출보정·중간드론): old합성 대비 +0.107, **2벤치 일반화** + 학습분산 3~4배↓
- **★마스터 결론** (3벤치 8점, corr -0.84): 합성가치는 **`real-only 충분성`에 조건부**.
  real약함(어렵/실라벨희소)→**크게 도움**, real강함(쉬움)→방법무관 해침(도메인갭)
- **최적 방법**: 매우 scarce(≤50)→**real+합성 mix**, 충분(≥100)→**합성 pretrain→실 fine-tune**
- **깨달음**: 공개벤치 다수가 큰 근접드론이라 안티드론(원거리 tiny)과 regime 다름 → 그 영역은 실데이터 희소 = **합성이 필수**

## 구성
| 파일 | 역할 |
|---|---|
| `prepare_data.py` | HF `pathikg/drone-detection-dataset` → YOLO 포맷 추출 (COCO→YOLO 변환) |
| `train.py` | YOLO11n 드론 탐지 학습 → `runs/drone_y11n/` |
| `infer.py` | 학습 모델로 추론/검증 (mAP + 박스 그린 이미지) |
| `data/` | 학습 데이터 (images/labels train·val + data.yaml) |
| `runs/drone_y11n/weights/best.pt` | 학습된 가중치 |

## 실행 (전부 venv 파이썬으로)
```bash
cd drone_det

# 1) 데이터 준비 (소량 추출, 기본 train 2000 / val 400)
N_TRAIN=2000 N_VAL=400 venv/bin/python prepare_data.py

# 2) 학습 (기본 50 epoch, RTX 4060 8GB 기준)
EPOCHS=50 BATCH=16 venv/bin/python train.py

# 3) 검증 + 샘플 예측
venv/bin/python infer.py

# 4) 내 이미지/폴더로 테스트
venv/bin/python infer.py path/to/image.jpg
```

## 환경
- Python venv (`venv/`), Ultralytics YOLO11 + PyTorch CUDA
- GPU: RTX 4060 8GB / 단일 클래스 `drone`

## 데이터 출처
HuggingFace `pathikg/drone-detection-dataset` (단일클래스 drone, YouTube 프레임, COCO→YOLO 변환).
