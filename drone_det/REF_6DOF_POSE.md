# REF — 사진에서 드론 6DoF 추출 (사례·방법·상업 라이브러리)

> "단안 RGB → 드론 6DoF(위치+자세)" 구현 레퍼런스. 웹검색 + 실제 논문/LICENSE 확인.
> 결론: **검증된 분야이고, 정석 = 키포인트→PnP + 합성데이터 + CAD + Kalman.**

---

## 1. 유사 사례 (선례 = 우리 계획 검증됨)

### ⭐ DroneKey (2025, arXiv 2508.17746) — 가장 직결
- 파이프라인: **2D 키포인트(트랜스포머) → PnP → 6DoF**
- 키포인트 = **프로펠러 4개**, 기종별 **CAD 3D좌표 알고 사용**
- 데이터: **전부 합성**(3D 렌더 + 실사 배경). 자작 데이터셋 2DroneKey(10K)·3DronePose(6DoF GT)
- 자작 이유: "실드론 키포인트/6DoF GT 확보 어려움" → **합성 필요성 입증**
- 시계열: **Kalman 필터로 6DoF 평활**(가벼움, LSTM 아님)
- 성능: 회전오차 **10.62°**, 위치 RMSE 0.221m, **44 FPS**, 키포인트 AP 99.68%
- 대상: DJI Air2S·Mini2 (쿼드, 프로펠러 4점)

### 기타 선례 (전부 같은 레시피로 수렴)
| 프로젝트 | 핵심 | 우리에 주는 것 |
|---|---|---|
| Sim-to-Real 6DoF UAV (합성 RGB-D), Springer 2025 | 합성→실전 6DoF | 방법론 직결 |
| Distance-Aware Keypoint Heatmaps, Nature SciRep 2025 | **거리별 키포인트 sigma 적응** | ⭐ 우리 500m 문제 해법 |
| Drone Pose + Relational Graph, MDPI 2019 | 키포인트+그래프+PnP, CAD의존↓ | 키포인트 관계 |
| TNN-MO (함상 UAV), arXiv 2406.09260 | 트랜스포머 단안 6DoF, 합성 | 트랜스포머 대안 |
| 우주선 6DoF(SPEED 등) | 동일 문제군(원거리 소형) | 검증된 분야 |

## 2. 정석 레시피 (선례 공통)
```
탐지 → ROI → 키포인트 검출(CAD로 3D좌표 알고있음) → PnP(2D-3D) → 6DoF → Kalman 평활
                         └ 합성데이터로 학습 (공개 데이터 부족 → 다들 자작)
```
- 거리 문제: **거리별 적응 sigma**(가까울수록 좁은 히트맵) — Nature 2025
- 원거리(몇 픽셀): 6DoF 정밀 불가 → 위치+궤적heading만 (물리적 한계)

## 3. 상업용 라이브러리 & 라이선스 (실제 LICENSE 확인)
| 라이브러리 | 용도 | 라이선스 | 상업 |
|---|---|---|---|
| **OpenCV `solvePnP`** | 키포인트→6DoF (정석 핵심) | Apache 2.0 | ✅ |
| **MegaPose** | render&compare 6DoF (CAD) | Apache 2.0 | ✅ |
| **HappyPose** | MegaPose+CosyPose 통합 | BSD 2-Clause | ✅ |
| FoundationPose | SOTA 6DoF | **NVIDIA Source Code License** | ❌ 비상업 |

### ⚠️ 탐지기 라이선스 경고 (중요)
- **Ultralytics YOLO(v5/v8/11/26) = AGPL-3.0** → 상업 제품 시 **전체 소스공개 or 엔터프라이즈 구매**. (현재 우리 베이스라인이 이것!)
- 상업 대체: **YOLOX**(Apache)·**RF-DETR**(Apache)·**MMDetection RT-DETR**(Apache)·PP-YOLO(Apache)
- 주의: RT-DETR도 **Ultralytics 래퍼는 AGPL** → standalone Apache판 사용

## 4. 우리 프로젝트 권장 구현
```
[상업·Jetson 1순위] YOLOX/RF-DETR(Apache) 탐지 → 키포인트 → OpenCV solvePnP(Apache) → 6DoF → Kalman
[정확도 우선/오프라인] HappyPose/MegaPose(Apache/BSD) render&compare
[피할 것] FoundationPose(비상업) · Ultralytics(AGPL)
```
**우리 엣지**: 선례는 DJI 쿼드(프로펠러 4점)지만, 우리는
- **니나노 테일시터 실CAD** → 키포인트만 새로 정의(방법 동일)
- **sim 파이프라인(AI-2)** → 키포인트·6DoF·거리 GT 무한 생성
- **실비행 검증(니나노)** → Sim-to-Real 고리 완비
→ 선례보다 데이터·검증 인프라가 앞섬.

## 5. 미해결/확인
- 테일시터 키포인트 정의(프로펠러/동체 몇 점?) — 형상 보고 결정
- 거리별 정밀도 목표(근거리 6DoF / 원거리 위치+heading) 분리
- 탐지기 Apache 교체 시점(상업화 전 필수)

## Sources
- DroneKey: https://arxiv.org/html/2508.17746v1
- Distance-Aware Keypoint Heatmaps: https://www.nature.com/articles/s41598-025-31572-3
- Sim-to-Real 6DoF UAV: https://link.springer.com/chapter/10.1007/978-3-032-08049-3_6
- Drone Pose Relational Graph: https://www.mdpi.com/1424-8220/19/6/1479
- MegaPose(Apache): https://github.com/megapose6d/megapose6d
- HappyPose(BSD): https://github.com/agimus-project/happypose
- FoundationPose(비상업): https://github.com/NVlabs/FoundationPose/blob/main/LICENSE
- Ultralytics 라이선스: https://www.ultralytics.com/license
