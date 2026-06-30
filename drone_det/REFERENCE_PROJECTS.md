# 유사 프로젝트 조사 + 우리 프로젝트 이식/수정 포인트

> 시뮬레이션 합성데이터로 객체탐지(특히 드론) 하는 프로젝트들 조사. 우리 = Isaac Sim + 시부야 + 드론/새 + 지상→하늘 + RGB + pretrain→FT, dvb 벤치, 목표 mAP50 0.80.
> 조사일 2026-06-30.

---

## A. 조사한 프로젝트 요약

### ⭐ 드론 탐지 합성데이터 (우리와 거의 동일)

**[SimD3 (2026)](https://arxiv.org/html/2601.14742)** — 우리와 가장 유사 (드론 + 새 distractor)
- 엔진: **Unreal Engine 5 + AirSim**, 모델은 Blender + Meshy AI
- 드론 **15종**(쿼드/헥사/옥토), 그중 8종은 **페이로드(박스/가방/무기형) 부착**, 7종 무탑재. 재질·색 랜덤화
- **새 8종** distractor: 개별 새는 라벨링, **Niagara 군집(flock) VFX는 무라벨**(배경 클러터로)
- 환경 7종(도심/교외/다리), 시간대·태양, **날씨(안개/눈) 파라메트릭(2~55% 강도)**, 6카메라 360° 파노라마, 원형/나선 비행궤적
- **178,639장**. YOLOv5m / YOLOv5m+CBAM. SimD3 단독 mAP@0.5 **0.961~0.975**
- 핵심: **실데이터 섞으면 DUT-AntiUAV에서 0.645→0.823** (하이브리드 효과 큼). 단 cross-dataset 도메인갭은 잔존

**[SynDroneVision (2024)](https://arxiv.org/html/2411.05633v1)** — RGB 드론 탐지 합성셋, 다양 배경·조명·드론모델. YOLO 학습 정확도 향상 입증. 우리 "현실성↑→mAP↑" 가설과 동일 구조

**[SynthAirDrone (2025)](https://www.mdpi.com/2504-446X/10/4/306)** — 공항 활주로 UAV, **6,500장 640×640 YOLO포맷**, scene-aware 배치 + 다기준 품질평가 자동화

**[Sim2Air (2021)](https://ar5iv.labs.arxiv.org/html/2110.05145)** — 합성 항공 UAV. 결론: **텍스처 랜덤화가 sim-to-real 핵심**

### ⭐ 도메인 랜덤화 / sim-to-real (기법 직접 참고)

**[Synthetic-to-Real with YOLOv11 + Domain Randomization (2024)](https://arxiv.org/html/2509.15045v1)** — ★우리와 같은 모델(yolo11l), 합성-only 챌린지
- COCO 가중치 → 합성만 fine-tune. 합성 2,106장(1,368 객체 + **738 빈 이미지**), 실 테스트 159장
- 증강: HSV·기하·**Mosaic·Mixup**·perspective. **최고 = yolo11l + 전체증강 + 다양성확장 = 실 mAP@50 0.910**
- ★핵심 발견들:
  1. **"다양성 확장 > 증강기법"** — 데이터 다양성이 어떤 증강보다 영향 큼
  2. **원거리/distant 시점이 오히려 일반화 도움** (처음엔 해로울 줄 알았으나 반대)
  3. **빈 이미지(negative) + Mosaic/Mixup = 클러터 강건성**
  4. **합성 val mAP(0.99~1.0)는 실성능 지표 아님 — 실 데이터 수동검증 필수**
  5. 더 큰 모델(l)이 도메인갭 더 잘 메움. 긴 학습·작은 lr 안정적

**[Domain Randomization for Manufacturing (2025)](https://arxiv.org/html/2506.07539v1)** — 합성-only YOLOv8로 **mAP 94~99%**. 중요요소: **재질·렌더링·후처리·distractor**

**[Sim-to-Real Fruit Detection w/ Isaac Sim (2026)](https://arxiv.org/pdf/2603.28670)** — 우리와 같은 Isaac Sim. 합성→실 정량평가 + 임베디드 배포 (평가 프로토콜 참고)

### 🛠️ 합성데이터 생성 도구 (대안/비교)
- [Isaac Sim Replicator (object_based_sdg)](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/replicator_tutorials/tutorial_replicator_object_based_sdg.html) — 우리가 쓰는 도구의 공식 YAML 파이프라인(RGB+2D/3D박스+세그 자동)
- [BlenderProc2](https://www.theoj.org/joss-papers/joss.04901/10.21105.joss.04901.pdf) — Blender 레이트레이싱, 물리, 완전한 어노테이션
- [Kubric](https://openaccess.thecvf.com/content/CVPR2022/papers/Greff_Kubric_A_Scalable_Dataset_Generator_CVPR_2022_paper.pdf) — Blender 기반, 대규모 워커 분산
- [Unity Perception](https://arxiv.org/pdf/2107.04259) / [NVISII](https://arxiv.org/pdf/2105.13962) — 게임엔진/스크립터블 경로추적

---

## B. 우리 프로젝트에 ★이식할 부분 (우선순위순)

| # | 이식 아이디어 | 출처 | 근거/효과 |
|---|---|---|---|
| 1 | **★확정: 학습에 `mixup=0.1` 추가** + negative 비중↑ | YOLOv11+DR | mosaic/hsv/flip은 ultralytics **기본 ON(이미 됨)**. **mixup만 기본 OFF → 0.1로 켜기**(클러터 강건). copy_paste는 우리 박스라벨엔 부적용(마스크 필요)이라 제외. NEG_RATIO 0.15→0.2~0.3 검토 |
| 2 | **환경(배경) 다양성 대폭 확장** | YOLOv11+DR, SimD3(7종) | "다양성>증강"이 최대 발견. 우리는 시부야 1개 — **과제도 3+환경 요구**. HDRI 더, 다른 도시/들판 추가 |
| 3 | **원거리/tiny 드론 down-weight 재고** | YOLOv11+DR | "distant 시점이 오히려 도움". 우리 scale_bin tiny=1/8로 억제 중 → 억제 완화 검토(A/B로) |
| 4 | **드론 페이로드(박스/가방) 부착 변형 추가** | SimD3 | 안티드론=보안용. 탑재물 드론은 더 다양·현실적. 메쉬에 박스 자식 prim 부착 |
| 5 | **새 군집(flock) 무라벨 distractor 추가** | SimD3 | 개별새(현재) + 멀리 떠다니는 새떼(무라벨 배경). 하드네거티브 강화 |
| 6 | **날씨(안개/연무) 서브셋 파라메트릭** | SimD3 | 우리 haze 파라미터 있음 → fog 강도별 서브셋으로 명시 분리. 악천후 강건성 |
| 7 | **★확정: 멀티카메라 2~3대 동시 렌더** | SimD3(6cam) | 한 씬서 2~3시점 동시추출. **레이트레이싱(72ms/장 플로어)은 안 줄지만**, 씬셋업 오버헤드(~250ms/장: 카메라재배치·밝기검증·정착대기)가 N장에 분산 → 장당 360ms→150~200ms대 기대. 6대는 상관성 과함→2~3대. 시점 다양성 보너스 |
| 8 | **(고급) CBAM 등 attention 헤드** | SimD3(+C3b) | 소형객체 mAP↑. yolo11 커스텀 필요(여력되면) |

## C. 우리 프로젝트에서 ★수정/보완할 부분

| # | 현재 상태 | 문제 | 수정 방향 |
|---|---|---|---|
| 1 | **환경=시부야 1종** | 과제 "3+환경" 미충족 + 다양성=최대 성능요인인데 부족 | 도시2~3 + 들판/공항 HDRI 추가. 최우선 |
| 2 | tiny 드론 1/8 억제(scale_bin) | "distant가 도움"인데 억제 중일 수 있음 | 억제 완화 버전 학습→dvb A/B 비교 |
| 3 | 드론=무탑재 멀티로터만 | SimD3는 페이로드/기종 더 다양 | 페이로드 변형 + 기종 다양성(현 3종→확대) |
| 4 | 합성 10k | SimD3 178k, 매뉴팩처링도 대량. 10k는 작은 편 | **합성 val 아닌 실 dvb로 크기-mAP ablation**해서 포화점 찾기 (앞 "최적개수" 질문) |
| 5 | 학습 평가가 합성val 위주 위험 | "합성val 0.99여도 실성능 무관" | 반드시 **실 dvb 평가 + 박스 그린 이미지 수동검증** (우리 이미 dvb평가 함=OK, 수동검증 추가) |
| 6 | 증강 설정 미점검 | Mosaic/Mixup/HSV가 sim2real 핵심 | train_win.py에 mosaic/mixup/hsv 명시·튜닝, A/B |

## D. 결론 / 액션 우선순위

1. **(★확정·즉시)** 학습에 `mixup=0.1` 추가 (mosaic/hsv/flip은 이미 기본 ON) + negative 비중↑ — 코드 한 줄
2. **(★확정)** 생성에 **멀티카메라 2~3대** — 씬셋업 오버헤드 분산으로 생성 가속 + 시점 다양성
3. **(과제필수)** 환경 2~3종 추가 (도시+들판/공항 HDRI) — "3+환경" + 다양성=최대 성능요인
4. **(검증)** 크기-mAP ablation + tiny억제 A/B + 실데이터 수동검증 루프
5. **(여력시)** 페이로드 드론, 새떼 VFX, 날씨 서브셋

> 한 줄 요약: 문헌 공통결론은 **"증강기법보다 데이터 다양성(환경·시점·객체)이 sim-to-real을 더 올린다"** + **"합성val 믿지 말고 실벤치로 검증"**. 우리 방향(pretrain→FT, dvb평가, 도메인랜덤화)은 정답이고, **환경 다양성 확장**이 가장 큰 레버.
