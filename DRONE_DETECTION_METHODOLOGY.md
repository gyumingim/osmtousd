# 드론(안티-UAV) 객체탐지 방법론 — 모델 선택용 정리

> 대상: 객체탐지 모델 선택 담당(AI#1).
> 목적: 본 과제 제약(다중스케일 10m~500m · 시계열 · Jetson 경량화 · Sim-to-Real)에 맞는 모델/기법을 빠르게 고르기.
> 모든 수치·기법은 출처 링크로 검증 가능. 작성일 2026-06-24.

---

## 0. 먼저 — 이 과제의 탐지가 어려운 이유 (모델 선택을 좌우하는 제약)

| 제약 | 의미 | 모델 선택에 주는 영향 |
|---|---|---|
| **초소형 표적** | 500m 드론 = 수 px ~ 수십 px | P2 고해상 헤드 / 슬라이싱 필수 |
| **다중 스케일 (10m~500m)** | 한 모델이 거대~점 크기 동시 처리 | FPN/PAN 다중스케일, scale-aware |
| **복잡 배경** | 구름·건물·산·바다, distractor | 배경 강건성, hard-negative 학습 |
| **새/잔해 오탐** | 실루엣·궤적 유사 → 최대 약점 | **시계열(궤적) 필요**, 단일프레임 한계 |
| **모션블러·가림** | 고속 이동, 부분 가림 | 데이터 증강, 시계열 보완 |
| **Jetson 엣지 배포** | 실기체 탑재(니나노) | 경량 + TensorRT, FPS≥30 목표 |
| **Sim-to-Real** | 합성학습 → 실영상 평가(mAP≥80%) | 백본 일반화, fine-tune 친화 |

---

## 1. 아키텍처 후보 (핵심 결정)

| 계열 | 대표 (2025~26) | 장점 | 단점 | 본 과제 적합도 |
|---|---|---|---|---|
| **YOLO (1-stage CNN)** | YOLOv8 / v10 / v11, 파생 다수 | 빠름·Jetson 친화·생태계 성숙·소형변형 풍부 | 초소형 dense는 보강 필요 | ⭐⭐⭐ **엣지 1순위** |
| **RT-DETR 계열** | [UAV-DETR](https://pmc.ncbi.nlm.nih.gov/articles/PMC12349633/), [SF-DETR](https://pmc.ncbi.nlm.nih.gov/articles/PMC11991380/), [Drone-DETR](https://link.springer.com/article/10.1007/s11227-025-08048-2) | mAP 상한 높음, anchor-free, NMS-free | 무겁고 **소형·밀집에 약함 + 연산량 큼** | ⭐⭐ 정확도 상한 검증용 |
| **2-stage (Faster R-CNN 등)** | — | 정확도 안정 | 느림, 엣지 부적합 | ❌ 실시간 X |

**수치 근거:** [SF-DETR](https://pmc.ncbi.nlm.nih.gov/articles/PMC11991380/)는 VisDrone2019에서 mAP95 **51.0%**로 YOLOv9m·RTDETR-r18 대비 +6.2%/+4.0%. [UAV-DETR](https://pmc.ncbi.nlm.nih.gov/articles/PMC12349633/)는 mAP@0.5 **51.6%**로 YOLOv8m 대비 +8.4%.
→ **정확도 천장은 DETR 계열이 높지만**, 트랜스포머는 "초소형·밀집 객체에서 연산량 크고 성능 suboptimal"([survey](https://pmc.ncbi.nlm.nih.gov/articles/PMC12349633/)). **Jetson + 점 크기 표적**이면 YOLO가 현실적.

---

## 2. 소형객체 탐지 기법 (모델 무관, 끼워넣는 부품)

아래는 백본/헤드와 **독립적으로 조합** 가능 — AI#1은 베이스 모델에 이것들을 더해 10m~500m를 커버.

- **SAHI (Slicing-Aided Hyper Inference)** — 고해상 입력을 640/832 타일로 쪼개 추론 후 병합, overlap≈0.2. 원거리 점-표적에 효과 큼. [learnopencv](https://learnopencv.com/slicing-aided-hyper-inference/) · [roboflow](https://roboflow.com/how-to-use-sahi/yolo-nas) · [평가논문](https://arxiv.org/pdf/2203.04799)
- **P2 탐지 헤드 (stride 4, 160×160)** — 기본 P3/P4/P5에 고해상 P2 추가 → **4×4 px** 객체까지 커버. [YOLO11-4K](https://arxiv.org/pdf/2512.16493) · [ultralytics P2/P6 논의](https://github.com/orgs/ultralytics/discussions/8227)
- **고해상 입력** — 입력 px↑ = 작은 드론 픽셀↑ (단, 연산량 trade-off)
- **특징융합/어텐션** — BiFPN, attention-gated 백본, context-aware fusion. [예](https://www.nature.com/articles/s41598-025-32074-y)
- **손실/증강** — Wise-IoU, copy-paste, mosaic. [LAF-YOLOv10](https://arxiv.org/pdf/2602.13378)

> ⚠️ 트레이드오프: SAHI/P2/고해상은 정확도↑지만 **추론 비용↑** → Jetson FPS와 직결. 경량화 섹션과 같이 잡을 것.

---

## 3. 시계열 활용 (본 과제 USP — 새/오탐 잡는 핵심)

단일 프레임으론 점-표적이 새인지 드론인지 구분 불가. **궤적·속도 일관성**으로 거른다.

| 접근 | 내용 | 효과(근거) |
|---|---|---|
| **Tracking-by-detection** | 탐지 후 ByteTrack/OC-SORT로 프레임간 연결, 궤적 점수화 | 짧은 오탐(깜빡임) 제거 |
| **Multi-frame motion** | YOLO + 다중프레임 모션 분석 | [원거리 소형 UAV 실시간](https://arxiv.org/html/2411.02582v1) |
| **Spatiotemporal NN** | CNN(공간)+GRU/TCN(시간)+모션 어텐션 (STBRNN) | **오탐 약 85%↓** vs 단일스트림 CNN [nature](https://www.nature.com/articles/s41598-025-99951-4) |
| **시퀀스 분류로 새 구분** | 다중프레임 궤적으로 bird vs drone | 새 분류 **F1 +73%** [nature](https://www.nature.com/articles/s41598-025-99951-4) |
| **Drone-vs-Bird 데이터** | "비-드론" 클래스/contrastive로 학습에 포함 | 새 오경보↓ (recall 유지) [Grand Challenge](https://mdpi.com/1424-8220/21/8/2824/htm) |

**권장 구조:** 프레임 탐지기(YOLO) → 트래커(ByteTrack) → 궤적 기반 후처리/경량 시계열 헤드. 탐지기와 시계열을 **분리**하면 모델 선택이 자유롭고 학습이 단순.

---

## 4. 경량화 / 엣지(Jetson) — 실증 제약

| 모델 | 파라미터/성능 | 비고 |
|---|---|---|
| [YOLOv9 on Jetson Nano](https://doi.org/10.3390/drones8110680) | mAP **95.7%**, v8 대비 +4.6% | 드론 탐지 전용 |
| [DRBD-YOLOv8](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11598377/) | **3.25M** (v8n의 ~절반) | 경량 안티-UAV |
| [LAF-YOLOv10](https://arxiv.org/pdf/2602.13378) | TensorRT FP16: Orin Nano **24.3 FPS** / AGX Orin **65.4 FPS** | P2헤드+PConv |
| [LEAF-YOLO](https://www.sciencedirect.com/science/article/pii/S2667305325000109) | <20M, **>30 FPS** (AGX Xavier, TensorRT) | 엣지 소형 |

**필수 처리:** ① nano/small 변형 선택 ② **TensorRT FP16(또는 INT8)** 변환 ③ 채널 프루닝 고려 ④ 입력해상도↔FPS 균형. 일반적으로 20~30 GFLOPs급이 Xavier NX에서 TensorRT로 30~50 FPS.

---

## 5. 평가 벤치마크 / 데이터셋 (실데이터 검증용)

- **[Anti-UAV Challenge](https://anti-uav.github.io/)** — 실드론 RGB/IR 영상, 다중스케일·다배경. 본 과제 mAP≥80% 기준셋. 지표 IoU·mAP.
- **DUT Anti-UAV** — 실드론 탐지/추적.
- **VisDrone2019** — 드론-뷰 일반 객체(소형객체 SOTA 비교 표준).
- **Drone-vs-Bird** — 새 오탐 학습/평가용.
- **Det-Fly / MAV-VID** — 공중-공중, 영상 시퀀스.

평가: mAP@IoU + **스케일별 AP(small/med/large)** 로 10m~500m 커버리지 입증.

---

## 6. 결론 — 권장 출발 스택 (AI#1용)

근거 종합 시 **Jetson 탑재 + 점-표적 + 시계열** 제약이 지배적이라, 다음을 베이스로 추천:

```
[베이스]   YOLOv11(또는 v10) small  ── Jetson 친화·소형변형 생태계
  + P2 헤드               ── 원거리(수 px) 드론 커버
  + SAHI(원거리 모드)      ── 500m급 타일 추론 (필요 구간만)
  + Wise-IoU / copy-paste ── 소형·불균형 보강
[시계열]   ByteTrack 후처리 + 궤적 기반 새/오탐 필터 (탐지기와 분리)
[엣지]     TensorRT FP16 변환, 입력해상도↔FPS 튜닝, 목표 ≥30 FPS
[평가]     Anti-UAV/DUT 실셋에서 mAP + 스케일별 AP
```

**대안:** 정확도 상한 검증이 필요하면 **UAV-DETR/SF-DETR**을 비-엣지(서버) 레퍼런스로 병행 측정 → YOLO 스택의 목표치 설정용. (엣지 배포는 비현실적이므로 최종 탑재는 YOLO 계열.)

**선택 시 의사결정 순서:** ① 엣지 FPS 예산 확정 → ② 그 안에서 최대 mAP 백본 → ③ 소형객체 부품(P2/SAHI) 추가 → ④ 시계열 후처리 → ⑤ 실셋 검증.

---

### 출처 (전체)
- 아키텍처: [Drone-DETR](https://link.springer.com/article/10.1007/s11227-025-08048-2) · [SF-DETR](https://pmc.ncbi.nlm.nih.gov/articles/PMC11991380/) · [UAV-DETR](https://pmc.ncbi.nlm.nih.gov/articles/PMC12349633/) · [RFAG-YOLO](https://pmc.ncbi.nlm.nih.gov/articles/PMC11991089/)
- 소형객체: [SAHI/learnopencv](https://learnopencv.com/slicing-aided-hyper-inference/) · [YOLO11-4K P2](https://arxiv.org/pdf/2512.16493) · [LAF-YOLOv10](https://arxiv.org/pdf/2602.13378) · [Sliced inference 평가](https://arxiv.org/pdf/2203.04799)
- 시계열: [STBRNN bird/drone](https://www.nature.com/articles/s41598-025-99951-4) · [YOLO+multi-frame](https://arxiv.org/html/2411.02582v1) · [Drone-vs-Bird Challenge](https://mdpi.com/1424-8220/21/8/2824/htm) · [Anti-UAV review](https://www.mdpi.com/2504-446X/9/1/58)
- 엣지: [YOLOv9 Jetson Nano](https://doi.org/10.3390/drones8110680) · [DRBD-YOLOv8](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11598377/) · [LEAF-YOLO](https://www.sciencedirect.com/science/article/pii/S2667305325000109)
- 벤치마크: [Anti-UAV](https://anti-uav.github.io/) · [SynDroneVision(합성)](https://arxiv.org/html/2411.05633v1)
