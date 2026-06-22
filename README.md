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
- 센서: 전/후/좌/우 카메라 4 + RTX LiDAR + 8방향 근접 raycast
- 자동 라벨: 2D/3D bbox · 시맨틱/인스턴스 세그 · 깊이맵 · 메타 JSON
- 환경변수: `ENV_LIGHTING`(dawn/day/dusk/night) `ENV_WEATHER`(clear/cloudy/fog/rain)
  `SPEED_KPH` `NUM_FRAMES` `ACTOR_MODE`(static/vru/collision) `OUTPUT_SUBDIR`
- 자가진단: `sensor_debug.py` → `output/debug_report.json`

## 3. 시나리오 5종 (`scenarios/`)

| # | 시나리오 | 스크립트 | 핵심 |
|---|----------|----------|------|
| ① | 극한 기상 자율주행 | `scenario_01_weather.py` | 기상×조명 변주, 악천후 LiDAR 저하 |
| ② | 산단 AMR 물류 | `scenario_02_amr.py` | 저속 8km/h, 작업자·지게차 |
| ③ | 보행자·이륜차 VRU | `scenario_03_vru.py` | 움직이는 VRU, 횡단/무단/끼어들기 |
| ④ | V2X 협력주행 | `scenario_04_v2x.py` | BSM/V2V/SPaT 메시지 로그 |
| ⑤ | 사고·충돌 | `scenario_05_collision.py` | 충돌 코스 + TTC 라벨 |

각: `python3 scenarios/scenario_0X_*.py` (내부에서 Isaac 세션 구동). 상세는 [docs/scenario_specs.md](docs/scenario_specs.md).

## 4. 후처리 파이프라인 (`pipeline/`)

```bash
python3 pipeline/quality_check.py    # 무결성 + 통계
python3 pipeline/packager.py         # → packages/<scenario>_<combo>.zip (data/labels/meta/README)
python3 pipeline/batch_render.py     # 5종 일괄 렌더→검증→패키징 (SKIP_RENDER=1 후처리만)
```

## 5. 웹 포털 (`web/`)

```bash
python3 -m pip install -r web/backend/requirements.txt
python3 -m uvicorn web.backend.main:app --port 8000     # http://localhost:8000
```
- `/` 데이터셋 카탈로그 (필터·미리보기·다운로드) · `/map` 교차로 지도(Leaflet)
- `/docs` FastAPI Swagger (API 명세 자동)

## 슈퍼컴 (`supercomp/`)
`sbatch supercomp/job_submit.sh` — SLURM 배치 템플릿 (GPU 노드 계정 필요).

## 미해결/한계
- Radar: Isaac Sim 5.1 플러그인 빌드 버그로 스킵 (초음파는 PhysX raycast로 대체)
- 실모델 LiDAR: 에셋서버 config(HESAI/Ouster) 미연동, `Example_Rotary` 사용
- 대량생성: `NUM_FRAMES=10000` 으로 확장 가능 (시간 소요로 소량 검증만)
- VDS 실시간/교통량 히트맵: 실시간 교통 데이터 연동 필요
