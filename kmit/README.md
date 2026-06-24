# 자율·비자율 혼합상황 지원플랫폼 — 구미 1산단 디지털트윈 합성데이터

OSM/Vworld 공공데이터로 구미 1산단 디지털트윈(USD)을 만들고, Isaac Sim으로
멀티센서 자율주행 합성 데이터셋(자동 라벨 포함)을 5종 시나리오로 생성·패키징하고
웹 포털로 제공하는 엔드투엔드 파이프라인.

## 전체 흐름

```
공공데이터(OSM/Vworld)
  → main.py            USD 생성 + 텍스처 + Isaac 후처리(Physics/Semantic/RoadGraph)
  → scenarios/*.py     Isaac Sim 멀티센서 주행 수집 (5종 시나리오)
  → pipeline/*.py      품질검증 → 표준 ZIP 패키징
  → web/               FastAPI 카탈로그 + 정적 포털 + 교차로 지도
```

원클릭: `bash pipeline/full_pipeline.sh`

## 1. USD 디지털트윈 생성

```bash
python3 vworld_fetcher.py && python3 osm_fetcher.py   # 최초 1회 데이터 수집
python3 main.py                                        # → gumi.usda (텍스처+Isaac 후처리 포함)
```

## 2. 센서 데이터 수집 (Isaac Sim)

엔진: `sensor_drive.py` (환경변수로 파라미터화). 직접 실행:
```bash
cd ~/isaacsim
ENV_LIGHTING=day ENV_WEATHER=clear SPEED_KPH=100 NUM_FRAMES=30 \
  ./_build/linux-x86_64/release/python.sh /home/karma/OSMtoUSD/sensor_drive.py
```
- 센서: 카메라4(전/후/좌/우) + LiDAR(360°×12채널) + Radar(FMCW 15빔) + 초음파8 +
  8방향 근접 — LiDAR/Radar/초음파/근접은 PhysX raycast 기반(RTX센서가 gumi 지오메트리
  미명중 → raycast로 대체, 실거리·intensity·RCS/SNR 산출)
- 자동 라벨: 2D/3D bbox(world transform 포함) · 시맨틱/인스턴스 세그 · 깊이맵 ·
  LiDAR .pcd(intensity) · Radar/초음파 .csv · 궤적 · 센서 캘리브 · 메타 JSON/YAML
- 환경변수: `ENV_LIGHTING`(dawn/day/dusk/night)
  `ENV_WEATHER`(clear/cloudy/fog/rain/snow/night_storm) `SPEED_KPH` `NUM_FRAMES`
  `ACTOR_MODE`(static/vru/collision/traffic/amr) `EGO_REACT` `EGO_MODEL`
  `AMBIENT_VEH`/`AMBIENT_PED`(배경 밀도) `OUTPUT_SUBDIR`
- 동적객체: 실제 차량(승용차·트럭=Kenney CC0, 버스·자전거=Poly CC-BY) + 보행자 +
  배경 밀도(주변 차량·보행자 자동 배치)
- 자가진단: `sensor_debug.py` → `output/debug_report.json`

## 3. 시나리오 5종 (`scenarios/`)

| # | 시나리오 | 스크립트 | 핵심 |
|---|----------|----------|------|
| ① | 극한 기상 자율주행 | `scenario_01_weather.py` | 기상6종×조명 변주, 악천후 LiDAR 저하 |
| ② | 산단 AMR 물류 | `scenario_02_amr.py` | 실제 AMR(iw.hub) 저속, 이동 작업자·지게차 |
| ③ | 보행자·이륜차 VRU | `scenario_03_vru.py` | 움직이는 VRU, ego 제동 반응 |
| ④ | V2X 협력주행 | `scenario_04_v2x.py` | 폐루프 신호+주행차량, 링크별 통신(RSSI/손실) |
| ⑤ | 사고·충돌 | `scenario_05_collision.py` | 실제 접촉 이벤트(임팩트속도) vs 회피, TTC |

각: `python3 scenarios/scenario_0X_*.py` (내부에서 Isaac 세션 구동). 상세는 [docs/scenario_specs.md](docs/scenario_specs.md).

## 4. 후처리 파이프라인 (`pipeline/`)

```bash
python3 pipeline/gen_calibration.py --datasets  # 센서 캘리브(K·외부변환·동기) → 각 셋
python3 pipeline/gen_trajectories.py            # 객체·ego 궤적 트랙
python3 pipeline/quality_check.py               # 무결성 + 통계
python3 pipeline/validate_labels.py             # 라벨 정확도/품질(경계·클래스·3D·커버리지)
python3 pipeline/packager.py                    # → packages/<scenario>_<combo>.zip
python3 pipeline/validate_zip.py                # ZIP 무결성·구조 검사
python3 pipeline/batch_render.py                # 5종 일괄 렌더→검증→패키징
python3 pipeline/run_scenario.py --grid full --frames 50   # 파라미터 조합 대량생성
```
표준 ZIP: `data/`(합성PNG) `labels/`(JSON·세그·깊이·pcd·csv·궤적) `meta/`(metadata·calibration) `README.md`. 스키마 단일출처: `pipeline/schema.py`.

## 5. 웹 포털 (`web/`)

```bash
python3 -m pip install -r web/backend/requirements.txt
python3 -m uvicorn web.backend.main:app --port 8000     # http://localhost:8000
```
- `/` 데이터셋 카탈로그 (필터·프레임재생·다운로드) · `/map` 교차로 지도 +
  도로혼잡 그라데이션(Leaflet) · `/vds` VDS 실시간 대시보드
- `/docs` FastAPI Swagger (API 명세 자동)
- 교차로/신호등/도로망 위치 = V-World(국토부 표준노드) 실데이터, 교통량 = 시뮬

## 슈퍼컴 (`supercomp/`)
`sbatch supercomp/job_submit.sh` — SLURM 배치 템플릿 (GPU 노드 계정 필요).

## 한계 / 남은 격차
- 대량생성: `run_scenario.py`로 1만 프레임 확장 준비됨 — 실행만 필요(시간 소요)
- 골격 Pose(관절 키포인트), 오토바이 실모델, 보행자 걷기 애니(omni.anim.people) 미구현
- 외부·인프라 의존(코드밖): 실 VDS(ITS API키), 기업 PoC, PostgreSQL, 슈퍼컴 실계정
- 센서는 RTX 대신 PhysX raycast 기반(RTX센서가 gumi 지오메트리 미명중 → 의도적 대체)

> ⚠️ 머신 주의: Isaac Sim **동시 2개 실행 금지**(GPU 메모리 한계 → ACPI gpe17
> 인터럽트 폭주로 시스템 행). 렌더는 항상 한 번에 하나씩.
