# 5종 시나리오 스펙 시트

공통 산출물(프레임당): 합성 PNG(카메라4+LiDAR+Radar+초음파+세그+깊이) ·
`frame_XXXX.json`(ego 실측속도·행동·bbox2d/3d(world transform)·actors·proximity·
radar/ultrasonic·ttc·collision_event·환경) · `labels/`(seg/inst/depth PNG·
.pcd(intensity)·.csv) · 데이터셋당 `calibration.json`·`trajectories.json`.
공통 동적객체: 실제 차량(승용차·트럭=Kenney CC0, 버스·자전거=Poly CC-BY) + 보행자 +
배경 밀도(`AMBIENT_VEH`/`AMBIENT_PED` 주변 차량·보행자 자동 배치).
공통 환경변수: `ENV_LIGHTING` `ENV_WEATHER` `SPEED_KPH` `NUM_FRAMES`
`ACTOR_MODE` `EGO_REACT` `EGO_MODEL` `AMBIENT_VEH`/`AMBIENT_PED` `OUTPUT_SUBDIR`.

---

## ① 극한 기상 자율주행 (`scenario_01_weather.py`) — 난이도 저

- **목적**: 동일 경로를 기상·조명 조합별로 수집한 페어 데이터
- **파라미터**: 6조합 — `day/clear`·`day/rain`·`dusk/fog`·`night/rain`·
  `day/snow`·`night/night_storm` (기상 6종 전부 커버)
- **특징**: 악천후 LiDAR 성능 저하 — rain 25%·fog 50%·snow 45%·night_storm 55% 드롭+노이즈
- **출력**: `output/scenario_01/<조명>_<기상>/`
- **라벨 강조**: 환경 메타(lighting/weather), 동일 경로 비교군

## ② 산단 AMR 물류 (`scenario_02_amr.py`) — 난이도 저

- **목적**: 실제 AMR(Idealworks iw.hub) 시점 저속 물류 주행 + 작업자·지게차 상호작용
- **파라미터**: `SPEED_KPH=8`·`ACTOR_MODE=amr`·`EGO_MODEL=iw.hub`, 3조합 —
  `day/clear`, `day/cloudy`, `night/clear`
- **특징**: ego에 실제 AMR 가시모델, **이동** 작업자 2명(걷기)+주행 지게차 1대(동적),
  도심 밀집 구간 자동 선정
- **출력**: `output/scenario_02/`

## ③ 보행자·이륜차 VRU (`scenario_03_vru.py`) — 난이도 중

- **목적**: 움직이는 보행자·이륜차 상호작용 + 행동·궤적 라벨
- **파라미터**: `ACTOR_MODE=vru`, `SPEED_KPH=20`, 2조합 — `day/clear`, `dusk/clear`
- **행동 스크립팅**: `normal_cross`(정상횡단) · `jaywalk`(무단횡단) · `cutin`(오토바이 끼어들기)
- **ego 반응**: 차로 정면 VRU에 실제 제동(20→0km/h, 4m 앞 정지) — 폐루프
- **라벨**: `actors[]` 프레임별 위치·heading·behavior + `trajectories.json` 트랙
- **출력**: `output/scenario_03/`

## ④ V2X 협력주행 (`scenario_04_v2x.py`) — 난이도 중

- **목적**: 폐루프 협력주행 — 기능형 신호등 + 줄서는 주행차량 + 통신이 거동에 반영
- **파라미터**: `SPEED_KPH=25`·`ACTOR_MODE=traffic`, 단일 run
- **거동**: 적색신호에 ego·차량 정지(V2I), 앞차 간격 유지(V2V) → 폐루프
- **메시지**(`v2x_log.json`, J2735 유사) — 링크별 송수신 모델:
  - **BSM**: 차량별 위치·속도·방향 방송 (매 프레임)
  - **V2V**: 근접 차량쌍 전방충돌 경고
  - **V2I/SPaT**: 실제 신호 위상(green/yellow/red)·잔여시간
  - 링크별 거리·RSSI(경로손실)·패킷손실·지연(`delivered` 플래그)
- **출력**: `output/scenario_04/run/` (+ v2x_log.json)

## ⑤ 사고·충돌 (`scenario_05_collision.py`) — 난이도 고

- **목적**: 실제 접촉 이벤트(임팩트속도) vs 회피 대비 + TTC 라벨
- **파라미터**: `ACTOR_MODE=collision`, 2케이스 —
  `imminent`(60km/h·`EGO_REACT=0` 무반응 돌진), `avoidance`(25km/h·`EGO_REACT=1` 제동)
- **구성**: 차로 위 고장차(arc-length 10m) + 측면 교차 진입차량, ego 접근
- **거동**: 사고=접근→접촉(`collision_event`: 프레임·임팩트km/h·대상)→정지,
  회피=제동으로 정지(접촉 없음)
- **TTC 라벨**(`ttc` 필드): `ttc_s` · `min_range_m` · `phase`(clear/approaching/warning/imminent/collision)
- **출력**: `output/scenario_05/<케이스>/`

---

## 대량 생성
각 시나리오 목표 10,000+ 프레임. `NUM_FRAMES` 환경변수로 확장:
```bash
NUM_FRAMES=10000 python3 scenarios/scenario_01_weather.py
```
슈퍼컴 배치: `sbatch --array=1-5 supercomp/job_submit.sh`.
