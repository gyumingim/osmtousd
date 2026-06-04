# TODO — 자율 비자율 혼합상황 지원플랫폼 기반조성

## 현재 진행도 요약

| 과업 | 상태 | 비고 |
|------|------|------|
| OSM/Vworld → USD 파이프라인 | ✅ 완료 | `main.py`, `gumi.usda` 생성 |
| 건물 메시 (박스빌딩 자동 배치) | ✅ 완료 | `building_generator.py` |
| 도로 메시 + 노면 마킹 | ✅ 완료 | `geo_to_mesh.py` |
| 신호등 + 횡단보도 CSV 배치 | ✅ 완료 | `csv_loader.py`, `props_generator.py` |
| 텍스처 생성 + 적용 | ✅ 완료 | `texture_gen.py`, `apply_textures.py` |
| Polyscope 뷰어 | ✅ 완료 | `viewer.py` |
| Isaac Sim Physics/Semantics/RoadGraph 후처리 | ✅ 완료 | `isaac_setup.py` |
| Omniverse/Isaac Sim 실제 연동 | ❌ 미착수 | |
| Replicator 합성 데이터 생성 | ❌ 미착수 | |
| 5종 시나리오 구현 | ❌ 미착수 | |
| 슈퍼컴 배치 렌더링 파이프라인 | ❌ 미착수 | |
| 웹 플랫폼 (FastAPI + React) | ❌ 미착수 | |

---

## 과업 1 — 디지털 트윈 기반 데이터 서비스 모델 5종

### 1-A. 기반 구축 (1~2개월차)

- [x] OSM/Vworld 데이터 수집 (`vworld_fetcher.py`, `osm_fetcher.py`)
- [x] OSM → USD 자동 변환 파이프라인 (`main.py`)
- [x] 박스 빌딩 자동 배치 + 텍스처 프리셋 (`building_generator.py`, `texture_gen.py`)
- [x] 도로망 + 교차로 + 신호등 + 횡단보도 에셋
- [x] 노면 마킹 (중앙선, 차선, 횡단보도) 생성
- [x] Isaac Sim용 Physics/Semantics/RoadGraph 후처리 (`isaac_setup.py`)
- [ ] **NVIDIA Omniverse Kit / IsaacSim 로컬 설치 및 환경 검증**
  - Isaac Sim 4.x 설치 (RTX GPU 필요)
  - `gumi.usda`를 Isaac Sim에서 열고 씬 정상 확인
  - Python omni.isaac.core API 테스트
- [ ] **Replicator 기초 테스트**
  - 카메라 센서 배치 + 한 장 렌더링
  - 자동 라벨(바운딩박스) 출력 확인

### 1-B. 센서 시스템 구축

- [ ] **Camera 센서**
  - 전방/후방/좌우측 다중 시점 RGB 카메라 설정
  - 해상도·FOV 파라미터화 (`camera_config.py`)
- [ ] **LiDAR 센서**
  - 3D 포인트 클라우드 생성
  - 채널 수·회전 속도·거리 파라미터 설정
- [ ] **Radar 센서**
  - 객체 거리·속도 정보 합성 신호 생성
- [ ] **Ultrasonic 센서**
  - 근거리 거리 센서 시뮬레이션
- [ ] 센서 간 시간 동기화 및 캘리브레이션 자동 생성
- [ ] 파일: `sensors/sensor_config.py`, `sensors/sensor_rig.py`

### 1-C. 환경 요소 구축

- [ ] **기상 시스템** (`environment/weather.py`)
  - 프리셋: 맑음 / 흐림 / 비 / 눈 / 안개 / 야간 호우
  - Replicator `randomizer` 연동
- [ ] **조명 시스템** (`environment/lighting.py`)
  - 시간대별: 새벽 / 주간 / 황혼 / 야간
- [ ] **동적 객체 에셋** (`environment/actors.py`)
  - 타 차량 (승용차, 트럭, 버스)
  - 보행자 (다양한 외형·속도)
  - 이륜차 (오토바이, 자전거)

### 1-D. 자동 라벨 생성 시스템

- [ ] 2D/3D 바운딩박스 자동 생성
- [ ] 시맨틱 세그멘테이션 (픽셀 단위 클래스)
- [ ] 인스턴스 세그멘테이션
- [ ] 깊이맵 (depth map)
- [ ] 메타데이터 자동 기록 (시나리오·파라미터·환경 조건)
- [ ] 파일: `labeling/auto_label.py`

### 1-E. 시나리오 ① — 극한 기상 조건 자율주행

**난이도: 저** | 목표: 10,000+ 프레임

- [ ] 구미 1산단 주요 도로 구간 차량 경로 설정
- [ ] Replicator 기상·조명 파라미터 변주 스크립트
  - 동일 경로에 대해 기상 조건별 페어 데이터 생성
- [ ] 악천후 센서 성능 저하 패턴 재현 (비 → LiDAR 노이즈)
- [ ] 파일: `scenarios/scenario_01_weather.py`

### 1-F. 시나리오 ② — 산업단지 AMR 물류

**난이도: 저** | 목표: 10,000+ 프레임

- [ ] Omniverse Warehouse 샘플 활용 + 구미 1산단 환경 접목
- [ ] AMR 주행 경로 스크립팅 (공장 간 이송, 로딩 독 진출입)
- [ ] 동적 객체 배치: 작업자·지게차 상호작용
- [ ] AMR 시점 멀티센서 데이터 획득
- [ ] 파일: `scenarios/scenario_02_amr.py`

### 1-G. 시나리오 ③ — 보행자·이륜차 상호작용 (VRU)

**난이도: 중** | 목표: 10,000+ 프레임

- [ ] 보행자·이륜차 3D 에셋 + 애니메이션 통합
- [ ] 행동 스크립팅: 정상 횡단 / 무단횡단 / 이륜차 끼어들기
- [ ] 보행자 궤적·자세(Pose) 라벨 자동 생성
- [ ] 교차로·횡단보도·산단 진출입로 중심 배치
- [ ] 파일: `scenarios/scenario_03_vru.py`

### 1-H. 시나리오 ④ — V2X 통신 기반 협력주행

**난이도: 중** | 목표: 10,000+ 프레임

- [ ] 주요 교차로별 V2X 에이전트 배치
- [ ] 구미시 교차로 메타데이터를 에이전트 행동 파라미터로 주입
- [ ] V2I / V2V 메시지 송수신 로그 생성 (`.json`)
- [ ] 협력주행 차량 궤적 데이터 확보
- [ ] 파일: `scenarios/scenario_04_v2x.py`

### 1-I. 시나리오 ⑤ — 사고·충돌 극한 상황

**난이도: 고** | 목표: 10,000+ 프레임

- [ ] PhysX 물리엔진 기반 충돌 시뮬레이션
- [ ] Z-score 상위 이상치 교차로 우선 적용 (인동광장네거리 등)
- [ ] TTC(Time-to-Collision) 라벨 자동 계산
- [ ] 사고 직전 / 사고 순간 / 사고 회피 시나리오 파라미터화
- [ ] 파일: `scenarios/scenario_05_collision.py`

---

## 과업 2 — 슈퍼컴퓨팅 연계 데이터 처리 및 기업 PoC

### 2-A. 슈퍼컴퓨팅센터 연계

- [ ] GPU 노드 접근 계정 확보 및 SSH 환경 구성
- [ ] 잡 제출 절차 수립 (SLURM/PBS 스크립트)
- [ ] Omniverse headless 렌더링 환경 구성
- [ ] 파일: `supercomp/job_submit.sh`, `supercomp/env_setup.sh`

### 2-B. 배치 렌더링 파이프라인

- [ ] 시나리오·파라미터 조합 배치 큐잉 스크립트
- [ ] Replicator 분산 렌더링 활용
- [ ] 렌더링 진행 상태 로그 관리
- [ ] 장애 발생 시 자동 재시도 + 실패 리포트
- [ ] 파일: `pipeline/batch_render.py`

### 2-C. 후처리 자동화

- [ ] 렌더링 결과물 포맷 변환 (Omniverse 원본 → `.png` / `.pcd` / `.json`)
- [ ] 자동 라벨 검증 스크립트 (바운딩박스 경계·라벨 일관성)
- [ ] 시나리오 단위 ZIP 패키징
- [ ] README·메타데이터 파일 자동 생성
- [ ] 썸네일용 대표 이미지 추출
- [ ] 파일: `pipeline/postprocess.py`, `pipeline/packager.py`

### 2-D. 데이터 품질 관리

- [ ] 프레임별 무결성 검증 (이미지 손상·라벨 누락)
- [ ] 시나리오 단위 통계 리포트 (프레임 수·용량·클래스 분포)
- [ ] 샘플 수동 검수 체계 운영
- [ ] 파일: `pipeline/quality_check.py`

### 2-E. 기업 PoC

- [ ] 지역 기업 대상 PoC 수행 계획 수립
- [ ] 합성 데이터 실무 활용 가능성 검증
- [ ] PoC 결과 보고서 작성

---

## 과업 3 — 웹 플랫폼 (포털)

### 3-A. 백엔드 (FastAPI + PostgreSQL)

- [ ] **프로젝트 초기화**
  - `web/backend/` 디렉터리 구성
  - FastAPI 0.104.1 + Uvicorn + PostgreSQL 14+ 셋업
  - 2차 연도 스키마 기반 DB 확장 (합성 데이터 메타데이터 항목 추가)

- [ ] **데이터베이스 스키마**
  - 데이터 출처 구분 필드: `Real` / `Synthetic`
  - 시나리오 유형 (5종)
  - 생성 파라미터 (기상·시간대·교통량 등)
  - 프레임 수·용량·센서 유형

- [ ] **API 엔드포인트**
  - `GET /api/datasets` — 공공+합성 통합 카탈로그 조회 (필터: type, scenario)
  - `GET /api/datasets/{id}` — 데이터셋 상세 + 스펙 정보
  - `GET /api/datasets/{id}/download` — ZIP 다운로드
  - `GET /api/stats/scenarios` — 시나리오별 통계
  - `GET /api/intersections` — 교차로 데이터 (81개)
  - `GET /api/intersections/heatmap` — 혼잡도 히트맵 데이터
  - `POST /api/routes/optimize-with-traffic` — 교통량 기반 경로 최적화
  - `GET /api/vds/live` — VDS 검지기 15분 단위 실시간 연동
  - 파일: `web/backend/main.py`, `web/backend/routers/`

### 3-B. 프론트엔드 (React + TypeScript)

- [ ] **프로젝트 초기화**
  - `web/frontend/` 디렉터리 구성
  - React 19 + TypeScript + Vite + Tailwind CSS

- [ ] **데이터셋 목록 페이지**
  - 썸네일·제목·용량·유형 태그 표시
  - Real / Synthetic 필터 토글
  - 시나리오 유형 필터

- [ ] **데이터셋 상세 페이지**
  - 대표 썸네일 이미지 2~5장
  - 시나리오 설명 텍스트
  - 데이터 스펙 표 (프레임 수·센서·라벨·포맷)
  - 생성 파라미터 요약
  - ZIP 다운로드 버튼

- [ ] **교차로 지도 페이지** (Leaflet)
  - 구미시 81개 교차로 마커 표시
  - 시간대별 교통량 기반 히트맵 레이어
  - Z-score 이상치 교차로 강조 표시

- [ ] **VDS 실시간 대시보드**
  - 15분 단위 교통량 업데이트
  - 이상 상황 알림

---

## 공통 인프라

- [ ] **데이터 표준화** (`pipeline/schema.py`)
  - ZIP 패키지 내부 구조 통일: `data/` / `labels/` / `meta/` / `README.md`
  - 파일명 규칙 정의

- [ ] **자동화 스크립트**
  - `pipeline/osm_to_usd.sh` — OSM → USD 원클릭 실행
  - `pipeline/run_scenario.py` — 시나리오 파라미터 조합 생성기
  - `pipeline/full_pipeline.sh` — 렌더 → 후처리 → 패키징 → 웹 등록

- [ ] **검증 도구**
  - `pipeline/validate_labels.py` — 자동 라벨 정확도 검증
  - `pipeline/validate_dataset.py` — 데이터셋 무결성 점검 (이미지 손상·누락)
  - `pipeline/validate_zip.py` — ZIP 패키지 유효성 검사

---

## 문서

- [ ] 사업 종료 보고서
- [ ] 사용자 매뉴얼 (데이터 다운로드·활용 가이드)
- [ ] 기술 문서 및 유지보수 가이드
- [ ] 5종 시나리오 상세 스펙 시트 (파라미터·결과물·검증 결과)
- [ ] API 명세 (FastAPI Swagger 자동 생성)

---

## 월별 마일스톤

| 월 | 목표 |
|----|------|
| 1월 | Isaac Sim 환경 구축, gumi.usda 로드 확인, Replicator 기초 테스트 |
| 2월 | 센서 시스템 구축, 시나리오 ①②(저난도) 구현, 슈퍼컴 연계 |
| 3월 | 시나리오 ①② 대량 생성(각 1만 프레임), 웹 플랫폼 백엔드 착수 |
| 4월 | 시나리오 ③④(중난도) 구현, 웹 플랫폼 프론트엔드 |
| 5월 | 시나리오 ⑤(고난도) 구현, 기업 PoC, 통합 품질 검증 |
| 6월 | 최종 검증, 문서 정리, 산출물 이관 |

---

## 디렉터리 구조 (목표)

```
OSMtoUSD/
├── [완료] main.py, geo_to_mesh.py, usd_writer.py 등  ← OSM→USD 파이프라인
├── [완료] gumi.usda                                  ← 구미시 베이스 씬
├── [완료] isaac_setup.py                             ← Physics/Semantics 후처리
├── scenarios/
│   ├── scenario_01_weather.py
│   ├── scenario_02_amr.py
│   ├── scenario_03_vru.py
│   ├── scenario_04_v2x.py
│   └── scenario_05_collision.py
├── sensors/
│   ├── sensor_config.py
│   └── sensor_rig.py
├── environment/
│   ├── weather.py
│   ├── lighting.py
│   └── actors.py
├── labeling/
│   └── auto_label.py
├── pipeline/
│   ├── batch_render.py
│   ├── postprocess.py
│   ├── packager.py
│   ├── quality_check.py
│   └── schema.py
├── supercomp/
│   ├── job_submit.sh
│   └── env_setup.sh
└── web/
    ├── backend/          ← FastAPI + PostgreSQL
    └── frontend/         ← React + TypeScript
```
