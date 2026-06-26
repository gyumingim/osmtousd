# STATUS — 안티드론 합성데이터 파이프라인

> 독립 과제(kmit 무관). 시뮬(Isaac Sim 5.1) 기반 드론 탐지 학습데이터 자동생성.
> 과제: `26년도 2인3각_조금원_교수님_v1.0.pdf` (금오공대×넥스트폼×니나노, 마감 2026-03-31)

## 전체 목표 (PDF 평가표 p8/p9 기준 — 출처 확인 완료)
- 합성데이터셋 **1만+ 프레임**(헤드라인 p4엔 "10만+"이나 정량 평가목표는 1만 이상) · 비중25%
- 드론탐지 **mAP≥80%**(sim-to-real, 공개벤치 Anti-UAV/DUT 절대기준) · 비중30%
- 어노테이션 **100% 자동화** · 비중20%
- **드론 3종/환경 3종+** 커버리지 · 비중15%
- **10m~500m+ 멀티스케일**(탐지거리) · 비중10%
- ⚠️ 속도/실시간 FPS는 평가지표 **아님**. 단 산출물에 **"Jetson 엣지 경량화 추론 모듈"**(p8/p10) 명시 → 경량/엣지 배포가 제약(FPS 목표치는 없음).
- **자동어노테이션 6항목(p7)**: 2D Box·3D Position·Class·Flight State·Seg Mask·**Keypoint 자세/포즈(6DoF)** + 추출물 "6D coordinate files". p11: "Pose 정보 포함 데이터셋"으로 확장 명시 → **pose/keypoint는 PDF 스펙 그 자체**.
**시점: 지상 센서가 하늘의 드론을 올려다봄**(공중 시점 아님). 배경=하늘/빌딩.

## 했던 일 (완료)
- 도시 배경: 시부야 FBX→USD (`assets/shibuya_large/shibuya_large.usd`, 텍스처 504장 바인딩)
- 하늘: Poly Haven HDRI CC0 (`assets/hdri/sky.hdr`)
- 자동 GT: `bounding_box_2d_tight`+`semantic_segmentation`(colorize=False)+`add_update_semantics`. RGB+박스+마스크+YOLO 자동.
- 도메인 랜덤화 루프: 지상시점, 거리·위치·자세·하늘·태양·카메라 랜덤.
- 1기종(쿼드) 데이터셋: `poc_city_render/dataset_quad/` (Isaac 기본 cf2x, 완전체 30장 + YOLO).
- **v1 생성기 완성·동결버그 해결**: `gen_v1_dataset.py`(env RUN별 1시점 고정카메라) + `run_v1_all.sh`(RUN 0~9 순차) → `dataset_v1/` images160+labels(YOLO)+sequences(시계열JSON). 궤적시퀀스+track-ID+flight-state+ego-motion+멀티스케일(px기반)+네거티브. **160프레임 85%양성, px중앙값129, 배경 하늘/건물 균형** 검증. 드론=Isaac 기본 Crazyflie 쿼드(eXplora 테일시터는 프린트키트 잡탕이라 폐기).
- 🔴 렌더 동결버그 해결: 무거운씬+orchestrator step 사이 USD transform쓰기→~20프레임후 동결 → 카메라 프로세스당 고정+드론회전 RUN당1회+RUN당≤16프레임.
- **GT 확장(2026-06-25)**: `gen_v1_dataset.py`에 기종 2종(quad/heli 교대)·distance_m(14~495m)·keypoints 9점(3D박스투영=자세)·pose_valid·pose_euler 추가. dataset_v1 160f(양성149). → p7 자동어노 6항목 거의 충족.
- **YOLO11-pose 학습셋 변환**: `to_yolo_pose.py` → `dataset_pose/`(images·labels train/val + data.yaml kpt_shape[9,3] + cuboid_objpoints.json[solvePnP용] + README). 시퀀스단위 분할(시간누수0). 자세추정 스택 = **YOLO11-pose(지금)/자체헤드(상업화) + OpenCV solvePnP + TensorRT(Jetson) + ByteTrack(시계열)**. ⚠️학습 fliplr=0.0 필수.
- **하드네거티브 디스트랙터(2026-06-25)**: `gen_v1_dataset.py`에 `/Distractors` 풀(새·비행기·풍선 모사 도형) 추가. `add_update_semantics` 안 붙여 자동 GT가 '드론 아님' 처리(검증: 2줄이상 라벨 0=오labeled 없음). 위치 시퀀스당1회(동결안전). dataset_v1 160f중 **128f(80%)에 디스트랙터**, 네거티브=빈프레임 아닌 디스트랙터포함. → 새 오탐 억제(sim-to-real #1 레버). 리얼리즘은 도형틱(추후 실메시 개선점).

## 하고 있는 일
- (대기) v1 다음 — sim-to-real 격차 메우기(아래 순서)/3종/스케일업.

## sim-to-real 5대 레버 — ①~④ 완료, ⑤ 하니스완료(학습보류) [2026-06-25]
- ✅ ① 하드네거티브 디스트랙터(새·비행기·풍선, `/Distractors`, 미labeled) — 85%프레임
- ✅ ② 센서효과 `sensor_fx` — **Carlson et al.2018(arXiv:1803.07721)** 5효과 순서(색수차→블러→노출gamma→Poisson-Gaussian노이즈→RGBShift색이동)+JPEG. 범위=albumentations 표준(임의수치 아님). 카메라설정=시퀀스당+노이즈 프레임별. 라벨은 클린지오(Carlson).
- ✅ ③ DR확장: **puresky HDRI 12종**(`assets/hdri/sky_*_ps.hdr`, 맑음/구름/흐림/노을/새벽/황혼) — ⚠️지형 HDRI는 도시와 붕뜸+이중태양이라 삭제, **puresky만+별도태양 제거하고 HDRI 돔 단일조명(IBL)**. FOV 50~68° 변주(fx_px 기록).
- ✅ ④ tiny 우세 스케일: sky 65% 원거리(px≈5~22) → 드론 px 중앙 129→43, tiny<22px 36%
- ✅ ⑤ 검증 하니스: `dataset_pose/VALIDATION.md`(공개벤치 DUT/UESTC/Drone-vs-Bird·거리층화 mAP·오탐율·실패주도 closed-loop·레버 체크리스트). ⚠️학습(YOLO train)은 사용자 지시로 보류 — 데이터/프로토콜만.

## 현실 격차 분석 → 보강 (자율 Cycle A~D) [2026-06-25]
> 우리 데이터 실측(밝기196·대비28·드론면적중앙0.49%) vs 실벤치 특성 비교 → 격차를 파이프라인으로 보강.
- ✅ A. **역광/실루엣(backlit)**: seg마스크로 드론만 노출부족(sil 0.12~0.42) → 밝은하늘 vs 검은드론. 안티드론 최난도. ~30%시퀀스.
- ✅ B. **태양 글레어/블룸**: 상단 하늘에 밝은 가우시안 블룸(드론 씻김 = 실제 최난도). ~28%.
- ✅ C. **디스트랙터 재균형**: 큰 흰 풍선(CG틱) 제거 → **작고 어두운 새 점**(드론 닮은 하드네거티브). Dd 0.7~2.0D(각크기 유사).
- ✅ D. **드론 외형 DR**: seg마스크로 드론 색/밝기 리버리 변주(흰/회/검). **Tremblay**(관심객체 외형 랜덤화). non-backlit 60%.
- 남은 격차(파이프라인 밖): 배경 클러터(나무·전선, 에셋 필요)·드론 본질외형(fine-tune 필요)·비디오 코덱 아티팩트.
- ✅ **드론 각도고정 버그 해결(2026-06-26, min_test6/7로 임계 실측)**: 동결 임계 = 참조모델 회전 ~23스텝 / 카메라패닝 ~11스텝 / 큐브 안남(모델특이적). **우리 16프레임<23 → per-frame 드론 회전 OK**(검증: 자세 yaw/pitch/roll 매프레임 변함). `rop` 프레임루프로 이동, `pose_euler` 프레임별 기록. keypoints 자동 per-frame. ⚠️카메라 패닝은 11<16이라 보류(≤8프레임런/Fabric 필요).
- ⚠️ **데이터 재생성(864→640)**: RUN=0 동결테스트가 dataset 초기화(RUN0=clear)로 864 날림 → per-frame 자세 반영해 RUN 0~39 재생성. **640프레임**(80시퀀스, quad272/heli242, GT 오labeled 0). `dataset_pose` 갱신. 1만+는 RUN 범위만 늘리면 됨(단일 클린 배치, kill 금지).
- 🔴 **머신다운 발생(RUN55 중 크래시)**: 백그라운드 Isaac 배치 kill→자식 Isaac 좀비 잔존→다음 배치와 동시실행→다운. 재부팅으로 좀비정리+데이터 생존(고아 png 7장만 제거). **교훈: 무인 장시간 스케일업 금지, 배치 kill 후 `pkill -f gen_v1_dataset.py` 필수**(메모리 [[isaac-sim-single-instance]] 갱신).

## 🔴 실벤치 검증 결과 (2026-06-26, 자율루프 Cycle0)
- 벤치: Roboflow `drones-yolo11-a`(실이미지 9.9k, 클래스 airplane/bird/drone, BY-NC). `eval_bench.py`로 단일클래스 drone AP.
- **순수 합성학습 모델(yolo11s-pose, synth val 0.625) → 실벤치 test AP50 = 0.0** (심각한 sim-to-real 갭). 모델이 새·비행기(confuser)에 헛박스 + 실드론 미탐. (bench_diag.png)
- 시사점: **합성 단독으론 이 실벤치 전이 실패 → 실데이터 fine-tune이 핵심 레버.** 합성의 가치 = pretrain으로 real-only 대비 향상되는지로 검증.
- 자율루프 방향: ①실벤치 train(6879)로 탐지기 학습=작동 recognizer ②합성 pretrain/믹스가 도움되는지 A/B ③반복.
- **Cycle1 (real-full 6879, yolo11s)**: real **test mAP50=0.944**(drone 0.944, airplane 0.935, bird 0.942), mAP50-95 0.643. = "실데이터 풍족시 천장"(비교 기준). 곡선 results/cycle1_*.
- **Cycle2 (scarce-real A/B, 단일클래스 drone)**: A=실200 vs B=실200+합성359 → 합성이 scarce real 보강하나(=과제 핵심 검증). data cycle2_data/, prep `cycle2_prep.py`.

## 할 일 (다음)
- 1만+ 프레임 스케일업(평가목표) · 3기종 테일시터(니나노 CAD/V-BAT)
- 표준포맷 패키징 → (학습 재개 시) 공개벤치 mAP 검증 + closed-loop
- 보조(나중): PBR/PathTracing 품질, 디스트랙터 실메시(현재 도형틱), GAN/도메인적응(80% 못넘으면)

## 사용 기술
Isaac Sim 5.1(RTX real-time/PathTracing), omni.replicator(annotator), omni.kit.asset_converter(FBX/glb→USD), trimesh(STL 병합), USD(참조/Xform).

## 문제점 및 해결
- eXplora 테일시터: 3D프린트 키트(STL 36조각)라 병합 시 잡탕 → **폐기**. 단일메시 모델 필요.
- Isaac 기본 드론엔 테일시터 없음(쿼드/Ingenuity뿐) → 쿼드 먼저, 테일시터는 V-BAT/니나노.
- 함정(전부 겪음): 변환 USD는 Y-up·cm·스트레이 지오메트리 → 카메라/스케일은 bbox 실측 상대값. USD Xform 이동+회전 같이 넣으면 위치틀어짐 → translate=부모/rotate=자식 분리. 소형 타겟은 카메라 `clipping_range` 작게(근접클립 1m 기본에 잘림). Isaac 동시 2개/학습+Isaac 동시 = 머신다운, `nvidia-smi --query-compute-apps`로 사전확인.
