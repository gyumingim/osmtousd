# 시뮬 기반 안티드론 탐지 — 통합 조사/설계 문서

> 출처: 「26년도 2인3각_조금원_교수님_v1.0.pdf」(국립금오공대 RISE 산학공동) + 웹 교차검증.
> 구성: **A.과제 개요** · **B.모델 방법론(AI#1)** · **C.데이터 파이프라인(데이터 레이어)**.
> 모든 수치·기법은 출처 링크로 검증 가능. 작성일 2026-06-24.

---
---

# Part A. 과제 개요

## A-1. 한 줄 & 전체 플로우

**"SIM에서 드론 사진+정답라벨을 자동으로 뽑아, 시계열로 엮어서, 실제 영상에서도 탐지 잘 되는 모델 만들기."**
핵심 차별점 = **시계열 맥락으로 오탐 억제** ("시뮬레이션이 곧 데이터, 시간축이 곧 신뢰도").

```
① 시뮬 환경(Omniverse/Isaac Sim + PX4 SITL + 드론에셋·배경)
      ▼
② 도메인 랜덤화 (조명·날씨·배경·기종·카메라·스케일 자동변주)
      ▼
③ 자동 어노테이션 (2D bbox·3D pos·class·flight-state·seg·keypoint, 시계열 일관성)
      ▼
④ 합성 데이터셋 (1만+ 프레임, 어노 100% 자동)
      ▼
⑤ CNN 드론탐지 + 시계열 Temporal Head
      ▼
⑥ Sim-to-Real (합성 사전학습 + 실데이터 fine-tune → 실영상 mAP≥80%)
      ▼
⑦ Jetson 경량화 → 니나노 테일시터 실기체 탑재 + HIL 검증
```

### 정량 목표 (PDF 9p)
| 항목 | 목표 | 비중 |
|---|---|---|
| 합성 데이터셋 규모 | 1만 프레임+ | 25% |
| 드론탐지 mAP (Sim-to-Real) | ≥80% (공개 벤치마크 대비) | 30% |
| 어노테이션 자동화율 | 100% | 20% |
| 드론 기종/환경 커버리지 | 3종/3종+ | 15% |
| 다중 스케일 탐지 | 10m~500m+ | 10% |

## A-2. 기관 분담 & 3-AI 작업 분담

**기관:** 금오공대(주관·시뮬환경·파이프라인·품질검증) / 넥스트폼(SW·CNN 탐지모델·학습·Sim2Real·Jetson) / 니나노(실증·드론CAD·실비행·HIL).

| AI | 역할 | 대응 문서 |
|---|---|---|
| AI#1 | 객체탐지 모델 선택/설계 | **Part B** |
| AI#2 | Isaac Sim 실환경 구축 | (씬 리얼리즘) |
| **이 작업(나)** | **데이터 레이어**(SIM 씬→시계열 데이터셋) | **Part C** |

**내 레인 근거:** 모델(AI#1)·씬(AI#2)은 임자 있고 그 사이 **②③④**(랜덤화·자동 어노테이션·시계열 패키징)가 비어있음. 정량평가 45%(어노 20%+규모 25%)가 데이터 무게. 일정상 ③(6~8월)이 현재 크리티컬 패스.

## A-3. Sim-to-Real — 평가 & 개선 (개념)

**평가:** SIM 학습 모델을 **학습에 안 쓴 실제 드론 영상(공개 벤치마크)**에서 mAP 측정. 우리끼리 만든 셋 비교는 순환논증이라 금지(PDF 8p). gap = (실데이터 학습 mAP) − (SIM만 학습 mAP). 스케일별 AP로 10m~500m 입증.

**개선 = "SIM 리얼리즘 향상"만이 아님 (중요 오해).** [Tobin 2017](https://lilianweng.github.io/posts/2019-05-05-domain-randomization/): 비현실적 랜덤 텍스처만으로도 실세계 전이 성공 → 리얼리즘 필수 아님.

| 레버 | 내용 | 성격 |
|---|---|---|
| ① 도메인 랜덤화 | 텍스처·조명·pose·배경 막 흔들어 실세계=변종화. **현실감보다 다양성** | 데이터/스크립트 |
| ② 도메인 적응 | CycleGAN sim→real, 실데이터 fine-tune | 모델/학습 |
| ③ 리얼리즘 | 렌더 품질↑. 도움되나 비싸고 수확체감 | 3D/씬 |

핵심: "더 진짜같게" ≠ "더 다양하게". → sim-to-real 개선 절반 이상은 AI#2(리얼리즘)가 아니라 데이터·학습 쪽.

## A-4. "노이즈" 명확화 (PDF 검증)

PDF엔 **"노이즈 넣어라" 없음**(grep 확인). "노이즈"는 8p에 1회 = **"노이즈 라벨"**(수작업 실데이터 라벨 부정확 = 실데이터 단점). 합성=완벽 GT라 우위라는 논리.
- **라벨 노이즈 = 나쁨**(PDF, 유지) — GT는 깨끗하게.
- **입력 이미지 노이즈 = sim-to-real엔 도움**(도메인 랜덤화 일부). 너무 깨끗한 SIM은 실카메라 분포와 달라 과적합. PDF 명시 없음 → 우리 결정사항.

---
---

# Part B. 모델 방법론 (AI#1용)

> 본 과제 제약(다중스케일 10m~500m · 시계열 · Jetson 경량화 · Sim-to-Real)에 맞는 모델/기법 선택용.

## B-0. 탐지가 어려운 이유 (모델 선택을 좌우)

| 제약 | 의미 | 영향 |
|---|---|---|
| 초소형 표적 | 500m 드론 = 수 px | P2 고해상 헤드 / 슬라이싱 필수 |
| 다중 스케일(10m~500m) | 거대~점 동시 처리 | FPN/PAN, scale-aware |
| 복잡 배경 | 구름·건물·산·바다 | 배경 강건성, hard-negative |
| 새/잔해 오탐 | 실루엣·궤적 유사 | **시계열(궤적) 필요** |
| 모션블러·가림 | 고속·부분가림 | 증강, 시계열 보완 |
| Jetson 엣지 | 실기체 탑재 | 경량+TensorRT, FPS≥30 |
| Sim-to-Real | 합성학습→실평가 | 백본 일반화, fine-tune |

## B-1. 아키텍처 후보

| 계열 | 대표 | 장점 | 단점 | 적합도 |
|---|---|---|---|---|
| **YOLO (1-stage)** | v8/v10/v11 | 빠름·Jetson친화·소형변형 풍부 | 초소형 dense 보강필요 | ⭐⭐⭐ **엣지 1순위** |
| **RT-DETR 계열** | [UAV-DETR](https://pmc.ncbi.nlm.nih.gov/articles/PMC12349633/)·[SF-DETR](https://pmc.ncbi.nlm.nih.gov/articles/PMC11991380/)·[Drone-DETR](https://link.springer.com/article/10.1007/s11227-025-08048-2) | mAP 상한↑, NMS-free | 무겁고 초소형·밀집 약함 | ⭐⭐ 상한 검증용 |
| **2-stage** | Faster R-CNN | 정확 안정 | 느림 | ❌ 실시간X |

수치: [SF-DETR](https://pmc.ncbi.nlm.nih.gov/articles/PMC11991380/) VisDrone mAP95 **51.0%**(YOLOv9m·RTDETR-r18 대비 +6.2/+4.0%). [UAV-DETR](https://pmc.ncbi.nlm.nih.gov/articles/PMC12349633/) mAP@0.5 **51.6%**(YOLOv8m +8.4%). → **천장은 DETR이 높지만 Jetson+점표적이면 YOLO가 현실적**.

## B-2. 소형객체 기법 (모델 무관, 끼워넣는 부품)
- **SAHI** — 고해상 입력을 640/832 타일 분할 추론 후 병합(overlap≈0.2). [learnopencv](https://learnopencv.com/slicing-aided-hyper-inference/)·[평가](https://arxiv.org/pdf/2203.04799)
- **P2 헤드(stride 4)** — 4×4px까지 커버. [YOLO11-4K](https://arxiv.org/pdf/2512.16493)·[ultralytics](https://github.com/orgs/ultralytics/discussions/8227)
- **고해상 입력** / **BiFPN·attention 융합**([예](https://www.nature.com/articles/s41598-025-32074-y)) / **Wise-IoU·copy-paste·mosaic**([LAF-YOLOv10](https://arxiv.org/pdf/2602.13378))
> ⚠️ SAHI/P2/고해상은 정확도↑·추론비용↑ → Jetson FPS와 직결.

## B-3. 시계열 활용 (USP — 새/오탐 잡기)
| 접근 | 내용 | 효과 |
|---|---|---|
| Tracking-by-detection | ByteTrack/OC-SORT 궤적 점수화 | 깜빡임 오탐 제거 |
| Multi-frame motion | YOLO+다중프레임 모션 | [원거리 소형UAV](https://arxiv.org/html/2411.02582v1) |
| Spatiotemporal NN | CNN+GRU/TCN+모션어텐션 | **오탐 ~85%↓** [nature](https://www.nature.com/articles/s41598-025-99951-4) |
| 시퀀스 분류 새구분 | 궤적으로 bird vs drone | 새 분류 **F1 +73%** [nature](https://www.nature.com/articles/s41598-025-99951-4) |
| Drone-vs-Bird 데이터 | "비-드론" 클래스/contrastive | 새 오경보↓ [Challenge](https://mdpi.com/1424-8220/21/8/2824/htm) |

**권장:** 프레임 탐지기(YOLO) → 트래커(ByteTrack) → 궤적 후처리/경량 시계열 헤드. **탐지기-시계열 분리**가 단순.

## B-4. 경량화 / 엣지(Jetson)
| 모델 | 성능 | 비고 |
|---|---|---|
| [YOLOv9 Jetson Nano](https://doi.org/10.3390/drones8110680) | mAP 95.7%(v8 +4.6%) | 드론 전용 |
| [DRBD-YOLOv8](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11598377/) | 3.25M(v8n 절반) | 경량 안티-UAV |
| [LAF-YOLOv10](https://arxiv.org/pdf/2602.13378) | Orin Nano 24.3 / AGX 65.4 FPS(TensorRT FP16) | P2+PConv |
| [LEAF-YOLO](https://www.sciencedirect.com/science/article/pii/S2667305325000109) | <20M, >30FPS | 엣지 소형 |

필수: nano/small 선택 → TensorRT FP16(또는 INT8) → 프루닝 → 입력해상도↔FPS 균형.

## B-5. 평가 벤치마크 / 데이터셋 (RGB)
- **[Anti-UAV](https://anti-uav.github.io/)** (단 2nd 이후 IR중심 → RGB-only면 일부만) · **DUT Anti-UAV**(RGB) · **VisDrone**(소형 SOTA 비교) · **Drone-vs-Bird**(새 오탐) · **Det-Fly/MAV-VID**(공중 시퀀스).
- 평가: mAP@IoU + 스케일별 AP.

## B-6. 권장 출발 스택
```
[베이스] YOLOv11(또는 v10) small  + P2 헤드 + SAHI(원거리) + Wise-IoU/copy-paste
[시계열] ByteTrack 후처리 + 궤적 기반 새/오탐 필터 (탐지기와 분리)
[엣지]   TensorRT FP16, 입력해상도↔FPS, 목표 ≥30 FPS
[평가]   DUT Anti-UAV/Drone-vs-Bird 실셋, mAP + 스케일별 AP
```
**대안:** 정확도 상한 검증엔 UAV-DETR/SF-DETR을 서버 레퍼런스로 병행(엣지 배포는 비현실적).
**의사결정 순서:** ① 엣지 FPS 예산 → ② 그 안 최대 mAP 백본 → ③ 소형부품(P2/SAHI) → ④ 시계열 후처리 → ⑤ 실셋 검증.

---
---

# Part C. 데이터 파이프라인 (데이터 레이어 = 내 레인)

## C-0. 확정된 전제 (PDF 모호점 정리)
| # | 항목 | 상태 |
|---|---|---|
| C1 | 합성 프레임 규모 | ✅ 공식 1만+(stretch 10만), **개수보다 다양성** |
| C2 | 영상 모달리티 | ✅ **RGB only**(IR 미사용 → 열 렌더링 불필요) |
| C3 | 카메라 시점 | ✅ **지상→공중 고정**(또는 팬틸트), 배경=하늘, ego-motion≈0 |
| C4 | 평가 벤치마크 | ⏸️ 미정(평가 단계), RGB셋 중 택1 |
| C5/F1 | Jetson·실카메라 스펙 | ⏸️ 미정(니나노 실배치) |

## C-1. (A1) Replicator 라벨 자동추출 — 6종 중 5종 네이티브
| 7p 산출물 | 지원 | 방법 |
|---|---|---|
| 2D bbox | ✅ | `bounding_box_2d_tight`/`_loose` |
| 3D pos/bbox | ✅ | `bounding_box_3d`/`_fast` |
| class | ✅ | `semantic_segmentation` |
| seg mask | ✅ | `semantic_segmentation`+`instance_id_segmentation` |
| keypoint/pose | ✅ 전용Writer | **DOPE/Pose/YCBVideoWriter** — 6-DOF pose + 투영 꼭짓점 keypoint(`CUBOID_KEYPOINTS_ORDER`) |
| flight-state | ❌ | 센서 아님 → **궤적에서 직접 파생** |

**내가 직접 구현할 3개:** ① flight-state 파생(궤적→상태라벨) ② **시계열 track ID 일관성**(프레임간 동일ID·ego-motion, USP) ③ ML-ready 패키징(Writer출력→COCO/YOLO+시계열JSON).
근거: [Replicator Writers API](https://docs.isaacsim.omniverse.nvidia.com/latest/py/source/extensions/isaacsim.replicator.writers/docs/api.html)·[Replicator 개요](https://docs.omniverse.nvidia.com/extensions/latest/ext_replicator.html). ⚠️ 공식 문서 기준 — GitHub MCP 활성화 시 DOPE/Pose Writer 소스로 재확인.

## C-2. (A2) 다중 스케일(10m~500m) 카메라/픽셀
핀홀: **픽셀폭 = (실폭 S / 거리 D) × (가로px W / FOV_rad)**. 탐지문턱 **>10×10px**(인식 ~20×10, 식별 ~30×20).

**0.3m 드론 픽셀폭** (X=탐지불가 <10px):
| 카메라 | 10m | 100m | 300m | 500m |
|---|---|---|---|---|
| 광각 60° @1080p | 55 | 5.5 **X** | 1.8 **X** | 1.1 **X** |
| 광각 60° @4K | 110 | 11 | 3.7 **X** | 2.2 **X** |
| 망원 6° @1080p | 550 | 55 | 18 | 11 |

**결론:**
1. **단일 고정 광각으로 10m~500m 불가** — 광각은 ~50m 넘으면 0.3m 드론 못 봄(500m=1px). 500m엔 HFOV≤6.6°(1080p) 망원 필요하나 횡폭 58m 좁은 콘.
2. **데이터셋은 카메라 구성 여러 개 렌더**(광각+망원). 10m~500m = 센서셋 합집합(PTZ/다중카메라 실배치 매칭).
3. **SIM 구조적 우위 실증** — 실세계선 2px 라벨 못 치지만 SIM은 2px여도 완벽 GT.
4. 🔴 **원거리(<10px)는 시계열 필수** — 외형 없어 단일프레임 불가, 움직이는 점은 모션으로 탐지 → 다중스케일이 시계열 USP를 강제.

근거: [EO/IR C-UAS 설계(픽셀문턱)](https://insideunmannedsystems.com/the-edge-of-visibility-eo-ir-system-design-realities-for-modern-c-uas/)·[88X 줌 PTZ](https://www.infinitioptics.com/video/auto-tracking-cuas-cuav-anti-drone-ptz-camera)

---

## 미해결 / 다음 작업
- **D1**(미조사) — 항공 소형표적 sim→real 정량사례 + 필요 실데이터 fine-tune 비율. [SynDroneVision](https://arxiv.org/html/2411.05633v1).
- **C4** — RGB 벤치마크 택1(평가 단계, E1 조사 후).
- **C5/F1** — 니나노 실카메라/Jetson 스펙 → A2 "광각+망원 2구성"을 실값 교체.
- **GitHub MCP** — 토큰 갱신 완료, **세션 리로드 전 비활성** → DOPE/Pose Writer 소스 직접확인 숙제.
