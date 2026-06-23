# 사용자 매뉴얼 — 합성 데이터셋 다운로드·활용 가이드

구미 1산단 디지털트윈 기반 자율주행 합성 데이터셋의 구조·포맷·활용법.

## 1. 데이터셋 받기

웹 포털(`http://localhost:8000`)에서:
1. 카탈로그에서 시나리오/환경으로 필터
2. 카드 클릭 → 프레임 재생·메타 확인
3. **ZIP 다운로드**

또는 직접: `packages/<scenario>_<variant>.zip`.

## 2. ZIP 구조

```
data/    frame_NNNN.png          멀티센서 합성뷰(카메라4+LiDAR+근접+세그+깊이)
labels/  frame_NNNN.json|yaml    프레임 라벨(아래 3절)
         frame_NNNN_seg.png      시맨틱 세그(클래스별 색)
         frame_NNNN_inst.png     인스턴스 세그
         frame_NNNN_depth.png    깊이맵(jet, 가까움=빨강)
         frame_NNNN_lidar.pcd    LiDAR 점구름(ASCII, x y z intensity)
         frame_NNNN_radar.csv    Radar 검지(beam,azimuth,range,velocity,rcs,snr)
         frame_NNNN_ultrasonic.csv  초음파(sensor,distance,detected)
         trajectories.json       객체·ego 궤적 트랙
         frame_NNNN_pose.json    (보행자 있을 때) 골격 관절 키포인트(자세)
         v2x_log.json            (V2X) 링크별 통신 로그
meta/    metadata.json           스펙·통계
         calibration.json        센서 내·외부 파라미터
README.md
```

## 3. 프레임 라벨(`frame_NNNN.json`)

| 키 | 내용 |
|----|------|
| `ego` | ego 위치 x,y,z·yaw_deg (월드 좌표, m) |
| `speed_kph`·`ego_action` | 실측 속도·거동(cruise/signal/lead/collided) |
| `bbox2d` | 카메라별(front/back/left/right) 2D 박스: label·x_min..y_max(px) |
| `bbox3d` | 3D 박스: extent(x/y/z min·max) + `transform`(4x4 월드 포즈) |
| `actors` | 씬 객체 GT: label·behavior·x·y·yaw |
| `ttc` | ttc_s·min_range_m·phase(clear→collision) |
| `collision_event` | (사고) 프레임·impact_kph·대상 |
| `signal` | (V2X) phase·time_to_change |
| `proximity_m`·`radar_detections`·`ultrasonic_detections` | 근접/레이더/초음파 |
| `labels` | seg/inst/depth/pcd/csv 상대경로 |

클래스: building, road, road_marking, crosswalk, sidewalk, traffic_sign,
traffic_light, car, truck, bus, motorcycle, bicycle, pedestrian.

## 4. 캘리브레이션(`meta/calibration.json`)

- **좌표계**: ego 로컬 (x=전방, y=좌, z=상), 미터.
- **카메라**: `intrinsics_K`(3x3, fx≈549.7·cx320·cy180) · `resolution`[640,360] ·
  `extrinsic_to_ego`(4x4, 센서→ego). 3D점→픽셀: `px = K · (extrinsic⁻¹ · P_ego)`.
- **LiDAR/Radar/초음파**: `extrinsic_translation`(ego 기준 장착 위치) + 사양.
- **동기**: 전 센서 10Hz 동일 스텝 → 타임스탬프 = frame / 10.

## 5. 좌표·단위 규약

- 길이 m, 각도 deg, 속도 m/s(또는 표기된 km/h).
- 월드 좌표는 gumi.usda 로컬 평면(원점=구미 1산단 기준). 위경도 변환은
  `vworld_data` 노드/링크의 WGS84와 대응(지도 페이지 참조).

## 6. 더 생성하기

```bash
# 단일 조합
ENV_LIGHTING=day ENV_WEATHER=snow ACTOR_MODE=traffic SPEED_KPH=25 NUM_FRAMES=50 \
  OUTPUT_SUBDIR=custom/my_run \
  ~/isaacsim/_build/linux-x86_64/release/python.sh sensor_drive.py

# 파라미터 조합 대량 생성
python3 pipeline/run_scenario.py --grid full --frames 100

# 후처리(캘리브·궤적·검증·패키징)
python3 pipeline/gen_calibration.py --datasets
python3 pipeline/gen_trajectories.py
python3 pipeline/packager.py && python3 pipeline/validate_zip.py
```

> ⚠️ Isaac Sim은 한 번에 하나만 실행(GPU 메모리 한계).

## 7. 라이선스

- 합성 데이터: 본 용역 산출물.
- 차량 에셋: Kenney Car Kit(CC0), Poly Pizza 버스·자전거(CC-BY) —
  `assets/vehicles/*_License*.txt`·`POLY_PIZZA_ATTRIBUTION.txt` 표기 준수.
- 지도 노드/도로/신호등: V-World(국토교통부) 공간정보.
