# 핸드오프 — 다음 작업자(AI/사람)용 빠른 인수인계

> 이 프로젝트를 처음 이어받는다면 **이 문서 → `docs/maintenance.md` → `TODO.md`** 순으로 읽으세요.
> 시간 낭비를 막는 함정 위주로 정리했습니다.

---

## 0. 이게 뭐냐 (1분 요약)

**넥스트폼 → 국립금오공대 용역**: 구미 1산단 디지털트윈 기반 **자율주행 합성데이터
생성 플랫폼** (NVIDIA Isaac Sim). OSM/V-World 공공데이터 → USD 디지털트윈 →
멀티센서 5종 시나리오 수집 → 표준 패키징 → 웹 포털 제공. **엔드투엔드 완성됨.**

산출물: 14 데이터셋·140프레임(소량 검증), 웹포털(`localhost:8000`).

---

## 1. 가장 먼저 알아야 할 함정 (이거 모르면 몇 시간 날림)

1. **Isaac 실행은 `python3` 아님** →
   `cd ~/isaacsim && ./_build/linux-x86_64/release/python.sh <script>`
2. **Isaac Sim 동시 2개 절대 금지** — 이 머신 GPU 14GB 한계 초과 →
   ACPI `gpe17` 인터럽트 폭주 → kworker 수백개 D-state → **시스템 행(load 100+)**.
   렌더는 항상 하나씩. (응급복구: `echo disable | sudo tee /sys/firmware/acpi/interrupts/gpe17`)
3. **RTX 센서가 gumi 지오메트리를 못 맞힘** → LiDAR/Radar/초음파/근접 전부
   **PhysX raycast로 구현**(`get_lidar_pts` 등). 카메라(rasterize)만 정상. RTX로
   되돌리지 말 것 — non-return만 나옴.
4. **Replicator 라벨엔 `add_update_semantics` 필수**(커스텀 attr 무시).
   bbox는 numpy 구조화배열(`bb["x_min"]`, `.get()` 아님).
5. **차량 에셋 좌표축이 소스마다 다름** — Kenney=Y-up(Rx90), Poly=Z-up(Rx0).
   `sensor_drive._VEH_CFG`에 종류별 scale·rx·rz. 새 에셋 추가 시 소량 렌더로 직립 검증.
6. **머신 부하**: 무거운 렌더 전 **재부팅 권장**(현재 멈춘 kworker 잔재로 load 높음,
   실자원은 비어있음).

---

## 2. 핵심 파일 지도

| 파일 | 역할 |
|---|---|
| **`sensor_drive.py`** | ★ 단일 센서수집 엔진(~1200줄). env var로 전부 파라미터화. 여기가 중심. |
| `scenarios/scenario_0[1-5]_*.py` | env var 조합으로 sensor_drive 구동(얇은 오케스트레이터) |
| `environment/{weather,lighting}.py` | 기상6종·조명4종 프리셋 |
| `sensors/sensor_config.py` | 센서 리그 설정(순수데이터, 캘리브 출처) |
| `pipeline/*.py` | 캘리브·궤적·검증·패키징·조합생성·스키마 |
| `web/backend/main.py` | FastAPI 카탈로그·교차로·VDS·도로혼잡 API |
| `web/frontend/{index,map,vds}.html` | 정적 SPA 포털 |
| `assets/vehicles/usd/` | 실제 차량 USD(Kenney CC0·Poly CC-BY) |
| `gumi.usda` | 베이스 디지털트윈(main.py가 생성) |

### sensor_drive 주요 env var
`ENV_LIGHTING`(dawn/day/dusk/night) `ENV_WEATHER`(clear/cloudy/fog/rain/snow/night_storm)
`ACTOR_MODE`(static/vru/collision/traffic/amr) `SPEED_KPH` `NUM_FRAMES`
`EGO_REACT`(0=무반응 사고) `EGO_MODEL`(가시 ego 모델) `AMBIENT_VEH`/`AMBIENT_PED`(밀도)
`OUTPUT_SUBDIR`.

---

## 3. 자주 쓰는 명령

```bash
# 단일 수집
cd ~/isaacsim && ENV_WEATHER=snow ACTOR_MODE=traffic NUM_FRAMES=20 OUTPUT_SUBDIR=t \
  ./_build/linux-x86_64/release/python.sh ~/OSMtoUSD/sensor_drive.py
# 전체 재생성 + 후처리 (순차, Isaac 하나씩)
python3 scenarios/scenario_01_weather.py   # ... 02~05
python3 pipeline/gen_calibration.py --datasets && python3 pipeline/gen_trajectories.py
python3 pipeline/packager.py && python3 pipeline/validate_labels.py && python3 pipeline/validate_zip.py
# 대량생성(1만 프레임 확장)
python3 pipeline/run_scenario.py --grid full --frames 700
# 웹포털
python3 -m uvicorn web.backend.main:app --port 8000   # localhost:8000
# 자가점검(캘리브↔리그 드리프트)
python3 pipeline/selfcheck.py
```

---

## 4. 무엇이 "진짜"고 무엇이 "시뮬/한계"인가 (정직하게)

**진짜 작동(검증됨)**: 카메라4·LiDAR·Radar·초음파(raycast) / 2D·3D bbox·세그·깊이·
궤적·캘리브 / ego 폐루프 주행(신호·앞차·VRU·충돌 반응) / V2X 링크통신 / 실제 충돌
이벤트 / 실차량(승용차·트럭·버스·자전거) / 기상6종 / 웹포털·지도·VDS.

**시뮬/placeholder(코드밖 의존)**:
- 교통량·혼잡도·VDS = **시뮬**(실 ITS/VDS API키 필요). 노드/도로/신호등 **위치는 V-World 실데이터**.
  교체점: `web/backend/traffic.py`.
- 골격 Pose 라벨 **완료**(UsdSkel 101관절 3D 월드 + 카메라별 2D 픽셀 투영,
  `get_poses`). 보행자 frame당 `labels/frame_NNNN_pose.json`.
- 보행자 **걷기 애니 작동**(omni.anim.people, 기본 ON). Pose Hip이 10프레임
  1.8m 전진·다리 stride 확인. ⚠️ **주의**: actor GT 위치 동기 버그를 4a328b4에서
  수정(get_poses가 골반좌표로 동기) — 이 수정 이후 렌더는 정확, **그 전 생성된
  현재 14셋은 걷기 보행자 actor x,y가 stale**(단 bbox·seg·Pose는 정확). 재부팅 후
  재생성하면 해소.
- **도메인 랜덤화** 추가(프레임별 조명, meta `domain_rand`) + **시네마틱 체이스캠**
  (`cinematic/frame_view_NNNN.png`, 포털 🎬토글).
- 오토바이만 박스 프록시(**최종**: CC-BY 후보 ~10개 렌더했으나 off-origin/저품질).
  나머지 이륜차=자전거 실모델.
- 카탈로그 DB는 **SQLite**(`web/backend/db.py`, 의존성0). PostgreSQL 전환은
  `db.connect()`만 psycopg로 교체(스키마 호환). React는 스캐폴드만, 실제는 정적 SPA.
- 1만 프레임 미달(현재 140) — `run_scenario.py`로 실행만 하면 됨.
- ⚠️ **GPU CUDA wedge 주의**: 연속 다수 렌더 시 CUDA 999로 먹통(cuInit 999,
  메모리는 빔). nvidia-smi 멀쩡해도 렌더 불가 → **재부팅만이 복구**.

---

## 5. 남은 작업 (우선순위순, 전부 가능)

| 작업 | 방법 | 난이도 |
|---|---|---|
| 재부팅 후 재생성 | GPU 복구 + 걷기 GT동기 수정(4a328b4) 반영해 14셋 재생성 | 실행만 |
| 1만 프레임 생성 | `run_scenario.py --grid full --frames 700` (시간·머신주의) | 실행만 |
| PostgreSQL | `main.py` zip스캔 → SQLAlchemy(SQLite로 시작 가능) | 중 |
| 실 VDS | `traffic.py`에 ITS OpenAPI 어댑터(API키 필요) | 외부의존 |
| 기업 PoC | 외부 사업활동(코드밖) | 외부 |
| 베이스맵 실지오메트리 | V-World 3D건물 확보 후 박스 extrude 교체(파이프라인 재작성) | 대 |

> 걷기 애니·골격 Pose(3D+2D)·도메인랜덤화·시네마틱·DB·실차량은 **완료**.
> 오토바이 실모델은 **보류 확정**(쓸만한 CC-BY 모델 없음 → 박스 프록시 유지).

---

## 6. 데이터 포맷 (자세히는 `docs/user_manual.md`)

ZIP: `data/`(합성PNG) `labels/`(JSON·세그·깊이·pcd·csv·궤적) `meta/`(metadata·calibration).
프레임 JSON 키·캘리브 K행렬·좌표규약은 user_manual 참조. 표준 단일출처=`pipeline/schema.py`.

---

## 7. 작업 습관 (이 프로젝트 사용자 선호)

- **최소 코드·최소 복잡도**, 디버깅하며 순차적으로.
- **가짜/얕은 구현 금지** — 안 되면 정직하게 "안 됨"이라 하고 한계 명시.
- 단계마다 **커밋**(한글 메시지, 무엇을·왜).
- yes/no 과도하게 묻지 말고 합리적 기본값으로 진행.
- 검증은 **실제 데이터/렌더로** 확인(주장만 X).

---

## 8. 현재 상태 한 줄

기능 거의 완성·검증, 14 데이터셋 생성·패키징·웹반영 완료. 걷기애니·골격Pose(3D+2D)·
도메인랜덤화·시네마틱·DB·실차량·지도(시뮬지점 마커 상호작용)까지 완료. 미달은
①대량생성(1만, 실행만) ②외부의존(실VDS·PoC·PostgreSQL) ③베이스맵 실지오메트리(대형).
오토바이=프록시 확정. 현재 14셋은 걷기 GT위치 stale(4a328b4 수정 후 재생성 시 해소).
