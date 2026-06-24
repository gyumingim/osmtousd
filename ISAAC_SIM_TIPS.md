# Isaac Sim 실전 팁 — kmit(구미 디지털트윈) 프로젝트에서 얻은 교훈

> 다음 Isaac Sim 프로젝트를 위한 이월 지식. 이전 프로젝트(`kmit/`, OSM/V-World
> 기반 자율주행 합성데이터 플랫폼) 진행 중 며칠씩 날린 함정들을 정리.
> 상세 맥락은 `kmit/HANDOFF.md`, `kmit/docs/maintenance.md` 참고.

---

## 0. 실행 기본

```bash
# python3 아님! Isaac 번들 파이썬으로 실행
cd ~/isaacsim && ./_build/linux-x86_64/release/python.sh <script.py>

# env var로 파라미터화하면 한 스크립트로 다양한 조합 수집 가능
ENV_WEATHER=fog NUM_FRAMES=10 ./_build/.../python.sh script.py
```

- `from isaacsim import SimulationApp` → `app = SimulationApp({"headless": True})`
  를 **다른 모든 omni/pxr import보다 먼저**. 안 그러면 import 에러.
- Headless 렌더는 `omni.replicator.core`로. 뷰포트 없이 카메라/주석 가능.

---

## 1. ⚠️ GPU가 먹통이 된다 (가장 큰 시간낭비)

- **증상**: `CUDA error 999: cudaErrorUnknown`, "Failed to query CUDA device
  count", "HydraEngine rtx failed", 렌더가 `_resize_data_for_overscan: NoneType`
  같은 엉뚱한 곳에서 죽음. `nvidia-smi`는 메모리 비어있다고 멀쩡하게 나옴(함정).
- **원인**: 한 세션에서 무거운 렌더를 연속 다수 돌리면 누적 스트레스로 CUDA
  컨텍스트가 깨짐. cuInit이 999 반환.
- **확인**: `python3 -c "import ctypes;print(ctypes.CDLL('libcuda.so.1').cuInit(0))"`
  → 0이면 정상, 999면 wedge.
- **복구**: **재부팅만이 답**. Xorg/원격세션(parsecd)이 GPU를 잡고 있어 드라이버
  리로드 불가. `nvidia-smi`가 멀쩡해 보여도 렌더는 안 됨.
- **예방**: 대량 렌더는 한 번에 몰아 돌리되 중간중간 GPU 상태 확인. 렌더 전
  `cuInit` 체크를 자동화하면 헛돈 시간 절약.

## 2. ⚠️ Isaac Sim 동시 2개 실행 절대 금지

- 이 머신 GPU(8~14GB)에선 2개 동시 → 메모리 초과 → ACPI `gpe17` 인터럽트 폭주
  → kworker 수백 개 D-state → **시스템 행(load 100+)**.
- 렌더는 **항상 하나씩**. 런처 스크립트에 락/프로세스 체크 넣을 것.
- 응급복구: `echo disable | sudo tee /sys/firmware/acpi/interrupts/gpe17`
- 프로세스 체크는 `ps -eo comm | grep -ciE '^kit'` + `nvidia-smi` compute-apps로.
  `grep python.sh`는 자기 자신 명령줄을 잡는 **false positive** 주의.

## 3. ⚠️ RTX 센서가 커스텀 지오메트리를 못 맞힌다

- 직접 만든 USD 메시(빌딩/도로 등)에 RTX LiDAR/Radar는 **non-return만** 나옴.
- 해결: LiDAR/Radar/초음파/근접 전부 **PhysX raycast**로 직접 구현
  (`scene_query.raycast_closest` 등). 카메라(rasterize)는 정상.
- RTX로 되돌리지 말 것 — 빌트인 에셋엔 되지만 커스텀 씬엔 안 됨.

## 4. Replicator 자동 라벨

- 시맨틱 라벨엔 **`add_update_semantics(prim, "class")` 필수**. 커스텀 USD attr는
  Replicator가 무시함.
- bbox 데이터는 **numpy 구조화 배열** → `bb["x_min"]`로 접근(`.get()` 아님).
- annotator: `rgb`, `bounding_box_2d_tight`, `bounding_box_3d`,
  `semantic_segmentation`, `instance_segmentation_fast`, `distance_to_camera`.
- `render_product` 생성 후 `annotator.attach([rp])`, `rep.orchestrator.step()`
  또는 `sim_ctx.step(render=True)` 후 `annotator.get_data()`.
- bbox3d `transform`은 4x4 월드 포즈. 2D 투영은 핀홀: `px = K·(extrinsic⁻¹·P)`.

## 5. 외부 에셋(GLB/FBX) → USD

- `omni.kit.asset_converter`:
  `get_instance().create_converter_task(in, out, cb, ctx)` +
  `await task.wait_until_finished()`.
- **좌표축이 소스마다 다름**: Kenney=Y-up(Rx90 보정 필요), Poly Pizza=Z-up(Rx0).
  새 에셋은 **소량 렌더로 직립/스케일 직접 검증** 후 등록.
- **off-origin/stray 지오메트리 함정**: bbox 중심이 실제 메시에서 멀면(스트레이
  버텍스) 1/max_dim 스케일 시 진짜 모델이 미세해져 안 보임. bbox 기반 자동
  스케일/센터링이 무효 → 그런 모델은 버리고 다른 거 찾는 게 빠름.
- 외부참조 텍스처(colormap.png 등)는 usd 옆 `textures/`에 복사.

## 6. 보행자 걷기 애니 (omni.anim.people)

- **확장을 Replicator import 前에 enable** 必 (SimulationApp 직후). 안 하면
  OmniGraph 스케줄러 충돌로 크래시.
  ```python
  app = SimulationApp({"headless": True, "enable_motion_bvh": True})
  # 여기서 omni.anim.graph.core / .bundle / omni.anim.navigation.core /
  #   omni.kit.scripting / omni.anim.people / isaacsim.replicator.agent.core enable
  for _ in range(10): app.update()
  # 그 다음에 import omni.replicator.core
  ```
- 흐름: `CharacterUtil.load_default_biped_to_stage()` →
  `load_character_usd_to_stage()` → `setup_animation_graph_to_character()` →
  `setup_python_scripts_to_character()` + command 파일(`<name> GoTo x y 0 _`) +
  `/exts/omni.anim.people/command_settings/command_file_path` 설정.
- `navmesh_enabled=False`면 직선 보행. `sim_ctx.step`이 behavior on_update 구동.
- **⚠️ 위치 동기 함정**: `CharacterUtil.get_character_pos`(=캐릭터 root xform)는
  걷는 동안 spawn에 **고정(stale)**. 실제 걸은 위치는 **스켈레톤(UsdSkel) Pelvis/
  Hip 월드좌표**로 얻어야 함. GT 라벨/궤적/충돌판정에 root xform 쓰면 틀림.

## 7. 골격 Pose 라벨 (UsdSkel)

- `UsdSkel.Cache().GetSkelQuery(skeleton)` →
  `ComputeJointWorldTransforms(XformCache)` → 관절 월드 변환(예: 101 joints).
- SkelRoot는 `Usd.PrimRange(prim, TraverseInstanceProxies())`로 찾기.
- 2D 키포인트는 카메라 핀홀 투영(`fx=focal/aperture*width`). bbox와 대조해 검증.

## 8. 에셋 서버(S3) 네트워크 의존

- `get_assets_root_path()`는 S3(omniverse-content-production)에서 받음. 네트워크
  끊기면 `RuntimeError: Could not find assets root folder`로 렌더 실패.
- People 캐릭터/Biped_Setup 등도 S3 의존 → 대량 렌더 중 네트워크 드롭이 일부
  데이터셋만 실패시킬 수 있음. 실패 시 **재실행으로 복구**(코드 버그 아님).
- 패키징은 **빈 폴더(렌더 실패) 스킵**하게 가드를 둘 것 — 빈 결과가 좋은 걸
  덮어쓰지 않도록.

## 9. 디버깅/운영 잡팁

- **Isaac stdout은 segfault 시 유실** → 항상 **파일 로그**(run.log) 병행. 프레임별
  진행/카운트를 찍어두면 어디서 죽었는지 바로 보임.
- yaml 직렬화: numpy float은 재귀 `clean()`으로 python float 변환 후 dump.
- 좌표 투영: WGS84↔로컬은 pyproj UTM(한국 동부 `EPSG:32652`). 로컬=UTM(점)-
  UTM(원점). **역변환 가능** → 시뮬 로컬좌표를 실제 지도(WGS84)에 표시 가능.
- 웹 포털(FastAPI) 코드 수정은 **서버 재시작 필요**(--reload 없으면 미반영).
  `/api/refresh`는 데이터 카탈로그만 갱신, 코드는 안 바뀜. 옛 코드가 도는데
  결과가 이상하면 서버 나이부터 의심.
- 도메인 랜덤화는 `/World/SunLight`·`/World/DomeLight` 회전/세기를 프레임별
  시드로 흔들면 충분(데이터 다양성). 시네마틱 뷰는 ego 추적 체이스캠 별도 렌더.

---

## 한 줄 요약

**렌더 죽으면 90%는 GPU wedge(재부팅) 아니면 네트워크(재실행).** 코드 의심 전에
`cuInit`·`nvidia-smi`·네트워크부터 확인하면 시간 안 날린다. 센서는 raycast,
라벨은 add_update_semantics, 에셋은 축 검증, 걷기는 스켈레톤 위치.
