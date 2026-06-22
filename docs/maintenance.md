# 기술 문서 / 유지보수 가이드

## 아키텍처 한눈에

```
공공데이터(OSM/V-World)
  └ main.py → gumi.usda (빌딩/도로/마킹/신호등 + 텍스처 + Isaac 후처리)
       └ sensor_drive.py (단일 엔진, env var 파라미터화)
            ├ 센서: 카메라4(Replicator) + LiDAR/Radar/초음파/근접(PhysX raycast)
            ├ 라벨: Replicator(bbox2d/3d·seg·depth) + 자체(pcd·csv·궤적)
            ├ 동적객체: 실차량(assets/vehicles) + 보행자 + 배경밀도
            └ 폐루프: ego 주행·신호·충돌·V2X
       └ scenarios/*.py (env var 조합으로 sensor_drive 구동)
       └ pipeline/*.py (캘리브·궤적·검증·패키징)
       └ web/ (FastAPI 카탈로그 + 포털 + 지도 + VDS)
```

## 핵심 함정 (반드시 숙지)

1. **RTX 센서가 gumi 지오메트리를 못 맞힘** — RTX LiDAR/Radar는 non-return만 나옴.
   → LiDAR/Radar/초음파/근접 전부 **PhysX raycast**로 구현(`get_lidar_pts` 등).
   카메라(rasterize)는 정상.
2. **Isaac Sim 동시 2개 실행 금지** — GPU 14GB 한계 초과 → ACPI `gpe17` 인터럽트
   폭주 → kworker 수백개 D-state → 시스템 행. 렌더는 항상 하나씩.
   (응급: `echo disable | sudo tee /sys/firmware/acpi/interrupts/gpe17`)
3. **Replicator 라벨엔 `add_update_semantics` 필수** — 커스텀 attr는 무시됨.
   bbox 데이터는 numpy 구조화배열(`bb["x_min"]`, `.get()` 아님).
4. **차량 에셋 좌표축이 소스마다 다름** — Kenney=Y-up(Rx90 보정), Poly=Z-up(Rx0).
   `_VEH_CFG`에 종류별 scale·rx·rz. 이동 객체는 actor에 rx/rz_off 저장→유지.
5. **yaml 직렬화** — numpy float은 `clean()` 재귀 변환 후 dump.

## 실행/디버그

```bash
# 단일 센서 수집
cd ~/isaacsim && ENV_WEATHER=fog ACTOR_MODE=vru NUM_FRAMES=10 OUTPUT_SUBDIR=t \
  ./_build/linux-x86_64/release/python.sh ~/OSMtoUSD/sensor_drive.py
# Isaac stdout이 segfault 시 유실 → output/<subdir>/run.log 파일로그 확인
# 센서 자가진단
./_build/linux-x86_64/release/python.sh ~/OSMtoUSD/sensor_debug.py  # → output/debug_report.json
```

## 차량 에셋 추가 (GLB→USD)

```bash
# 1) CC0/CC-BY GLB를 assets/vehicles/glb/ 에
# 2) 변환
~/isaacsim/_build/.../python.sh convert_vehicles.py   # glb/*.glb → usd/*.usd
# 3) 치수 확인 후 sensor_drive _VEH_CFG에 scale·rx·rz 등록 (소량 렌더로 직립/스케일 검증)
# 4) 외부참조 텍스처(예: colormap.png)는 usd 옆 textures/ 에 복사
```

## 데이터 흐름/포맷

`pipeline/schema.py`가 ZIP 구조·파일명·클래스 단일출처. 변경 시 여기부터.
캘리브/궤적은 `pipeline/gen_*.py`로 후생성 → 패키저가 zip에 포함.

## 확장 포인트 (실데이터/실모델 연동 시 교체할 곳)

- 실 VDS 교통량: `web/backend/traffic.py`의 `simulate_volume`/`simulate_link_volume`
- 실 LiDAR 모델: `sensor_drive.get_lidar_pts` (현재 raycast)
- 골격 Pose: sensor_drive에 UsdSkel 관절 쿼리 추가 → 키포인트 라벨
- DB 백엔드: `web/backend/main.py`의 zip-scan을 SQLAlchemy로 교체
