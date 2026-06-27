# STATUS — 드론 탐지 모델 (독립 프로젝트)

> Isaac Sim 합성데이터 기반 안티드론(드론=표적) 탐지. KMIT·OSMtoUSD와 무관한 독립 프로젝트.

## ✅ 검증 완료 (Cycle 3~9, 2벤치·다중시드) — 상세: `FINDINGS.md`
- **합성가치 입증**: scarce real + 개선합성 → 벤치1 N50 0.20→**0.52**, 시뮬현실화로 old대비 +0.107
- **일반화**: 2번째 벤치(ITU UAV)서도 개선합성>old (+0.14/+0.26) + **학습분산 3~4배↓**
- **★마스터 결론(정직)**: 합성가치는 **`real-only 충분성`에 조건부** (corr -0.90).
  real약함(<0.5 mAP)→합성 크게도움 / real강함(>0.5)→방법무관 해침(도메인갭).
- **함의**: 합성은 *실라벨 부족+어려운* 안티드론에 유효(pretrain→실FT). 실데이터 충분하면 쓰지 말 것.
- 결과물: `poc_city_render/` (시뮬·러너), `results/` (곡선·CSV, github.com/gyumingim/osmtousd)
- 시뮬 현실화 커밋됨: 맑은하늘·파란HDRI·과노출보정·중간드론·노이즈↓ (`gen_v1_dataset.py`)

## 🤝 협업 메모 (3-AI 분업, STATUS 공유)
- **AI-1(나)** = **Sim-to-Real + 드론인식 *방법론* 설계·검증** (시뮬 연동 ❌)
- **AI-2** = 시뮬 생성 + 데이터셋 추출 (GPU 사용 중)
- **AI-3** = 자료조사
- **내 폴더**: `/home/karma/OSMtoUSD/drone_det/`
- **내 일**: 측정·진단·방법론 → AI-2에 'sim 생성 주문', AI-3 자료 검증·채택.

## 📚 방법론 산출물 (GPU 없이 작성·검증 완료)
- **METHODOLOGY.md** — 정적 레시피 + 반복 갭-클로징 루프 + 가설표
- **DATA_SPEC.md** — AI-2에 줄 데이터 계약(포맷·메타·생성 주문)
- **frame_dynamics.py** — 광류/프레임차분 전처리 (CPU 셀프테스트 PASS)
- **eval.py** — 크기/거리별 recall 진단 도구 (GPU 비면 실행)
- **RUNBOOK.md** — GPU 풀리면 돌릴 실험 명령
- **데이터 진단**: 박스 38.6%가 COCO small(<32px), 25%<20px
- **CPU 실측 진단**(GPU 0): 크기별 recall <16px 0.77 / 16~32 0.77 / 32~64 **0.71(최저)** / ≥64 0.85
  → ⚠️ "초소형 최악" 가정 *틀림*. 이 데이터가 tiny regime을 못 담음
  = **sim이 통제된 초소형(10~500m) 생성해야 할 직접 근거** (METHODOLOGY 1-b)

## ⏳ GPU 대기 (시뮬 AI 사용 중 → 학습 보류)
- 실험(1280 vs 640, 증강, P2, 벤치)은 RUNBOOK대로 GPU 풀리면 즉시 실행
- ⚠️ RUNBOOK 수정: yolo11-p2.yaml 없음 → yolo26-p2.yaml 사용

## 전체 목표
영상에서 드론을 탐지하는 CNN 모델 구축 (PDF: CNN 기반·시계열·Jetson·Sim-to-Real).

## 세부 목표 (현재 단계 = MVP)
실제 공개 데이터로 **작동하는 YOLO 드론 탐지기 베이스라인** 완성 → 추후 합성데이터·시계열·엣지 확장.

## 했던 일
- 환경 셋업 완료: venv + ultralytics 8.4.75 + torch 2.12.1(CUDA True, RTX 4060)
- 데이터 준비 완료: HF `pathikg` 스트리밍 → COCO→YOLO 변환(손계산 검증 일치)
  → `data/` train 2000장(2036박스)·val 400장(432박스), data.yaml
- 스크립트 작성: `prepare_data.py`·`train.py`·`infer.py`·README
- 2 epoch 스모크 학습 OK(GPU 정상, OOM 없음)

## 하고 있는 일
- (없음) MVP 베이스라인 완료.

## ✅ MVP 결과 (베이스라인 완성)
- 학습: YOLO11n 41 epoch (세션 종료로 50중 41에서 중단, best.pt 저장)
- **검증 성능 (val 400장): mAP50 0.830 · mAP50-95 0.381 · P 0.867 · R 0.770**
  → PDF 목표 "mAP ≥80%" 충족
- 추론 속도: 1.9ms/장 (GPU, ~500FPS) → 실시간·엣지 여유
- 샘플 예측: 원거리 들판 드론·근접 FPV 드론 정상 탐지 (runs/predict/samples/)
- 가중치: runs/drone_y11n/weights/best.pt

## 알려진 한계 (정직)
- 근접/겹친 드론에서 박스 중복(NMS conf/iou 튜닝 여지)
- 데이터 2000장(소량)·단일 도메인 → 일반화 한계. 합성데이터로 확장 시 개선 기대

## 할 일 (이후 단계, 별도 승인)
1. 합성데이터(Isaac Sim) 생성 → Sim-to-Real
2. 시계열(ByteTrack/OC-SORT) 추적 헤드
3. Jetson TensorRT 경량화

## 사용 기술
- Ultralytics YOLO11 (CNN 탐지기, PDF "CNN 기반" 충족)
- PyTorch + CUDA (RTX 4060 8GB)
- HuggingFace datasets (데이터 확보)
- 추후: ByteTrack/OC-SORT(시계열), TensorRT(Jetson), Isaac Sim(합성데이터)

## 문제점 및 해결방안
- (해결) torch·ultralytics 미설치 → venv에 설치 중
- (대응) pathikg 4.65GB 과대 → 스트리밍으로 소량(2000장)만 사용
- (주의) GPU 8GB → 배치/이미지 크기 작게, YOLO11n부터

## 데이터셋 출처
- HuggingFace: `pathikg/drone-detection-dataset` (54k장, COCO, 단일클래스 drone, YouTube 프레임)
