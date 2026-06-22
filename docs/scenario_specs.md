# 5종 시나리오 스펙 시트

공통 산출물(프레임당): 합성 PNG(카메라4+LiDAR+근접+세그+깊이) · `frame_XXXX.json`(ego·bbox2d/3d·actors·proximity·환경) · `labels/`(seg/inst/depth PNG).
공통 환경변수: `ENV_LIGHTING` `ENV_WEATHER` `SPEED_KPH` `NUM_FRAMES` `OUTPUT_SUBDIR`.

---

## ① 극한 기상 자율주행 (`scenario_01_weather.py`) — 난이도 저

- **목적**: 동일 경로를 기상·조명 조합별로 수집한 페어 데이터
- **파라미터**: 4조합 — `day/clear`, `day/rain`, `dusk/fog`, `night/rain`
- **특징**: 악천후 센서 성능 저하 — rain LiDAR 25% 드롭+노이즈, fog 50% 드롭
- **출력**: `output/scenario_01/<조명>_<기상>/`
- **라벨 강조**: 환경 메타(lighting/weather), 동일 경로 비교군

## ② 산단 AMR 물류 (`scenario_02_amr.py`) — 난이도 저

- **목적**: AMR(자율이동로봇) 시점 저속 물류 주행 + 작업자·지게차 상호작용
- **파라미터**: `SPEED_KPH=8`(AMR 페이스), 3조합 — `day/clear`, `day/cloudy`, `night/clear`
- **특징**: 정적 차량(지게차)·보행자(작업자) 배치, 도심 밀집 구간 자동 선정
- **출력**: `output/scenario_02/`

## ③ 보행자·이륜차 VRU (`scenario_03_vru.py`) — 난이도 중

- **목적**: 움직이는 보행자·이륜차 상호작용 + 행동·궤적 라벨
- **파라미터**: `ACTOR_MODE=vru`, `SPEED_KPH=20`, 2조합 — `day/clear`, `dusk/clear`
- **행동 스크립팅**: `normal_cross`(정상횡단) · `jaywalk`(무단횡단) · `cutin`(이륜차 끼어들기)
- **라벨**: `actors[]` 프레임별 위치·heading·behavior (궤적/Pose)
- **출력**: `output/scenario_03/`

## ④ V2X 협력주행 (`scenario_04_v2x.py`) — 난이도 중

- **목적**: 차량 간/인프라 간 통신 메시지 로그 (협력주행)
- **파라미터**: `SPEED_KPH=40`, 단일 run
- **메시지**(`v2x_log.json`, J2735 유사):
  - **BSM**: 차량별 위치·속도·방향 방송 (매 프레임)
  - **V2V**: 근접 차량쌍(≤30m) 전방충돌 경고
  - **V2I/SPaT**: 교차로 신호 위상(green/yellow/red)·잔여시간
- **출력**: `output/scenario_04/run/` (+ v2x_log.json)

## ⑤ 사고·충돌 (`scenario_05_collision.py`) — 난이도 고

- **목적**: 충돌 코스 + TTC(Time-to-Collision) 라벨
- **파라미터**: `ACTOR_MODE=collision`, 2케이스 — `imminent`(60km/h), `avoidance`(25km/h)
- **구성**: 경로 옆 고장차(갓길) + 측면 교차 진입차량
- **TTC 라벨**(`ttc` 필드): `ttc_s` · `min_range_m` · `phase`(clear/approaching/warning/imminent/collision)
- **출력**: `output/scenario_05/<케이스>/`
- **확장**: Z-score 상위 이상치 교차로(인동광장네거리 등) 좌표를 시작점으로 주입 가능

---

## 대량 생성
각 시나리오 목표 10,000+ 프레임. `NUM_FRAMES` 환경변수로 확장:
```bash
NUM_FRAMES=10000 python3 scenarios/scenario_01_weather.py
```
슈퍼컴 배치: `sbatch --array=1-5 supercomp/job_submit.sh`.
