"""안티드론 합성데이터 v1 생성기 (env RUN별 1시점=카메라 고정, 동결 회피).
GT: 위치(2D박스) + 거리(distance_m) + 자세(keypoints=3D박스 8모서리 투영, 카메라상대) + 기종(model).
기종 2종(쿼드 cf2x / 헬기 ingenuity) RUN별 교대. 모션블러(드론만) + 원거리 tiny + 네거티브 + 시계열.
RUN당 16프레임(동결 임계 아래). run_v1_all.sh가 RUN 0~9 순차. RUN=0만 초기화."""
from isaacsim import SimulationApp
# 속도최적화(NVIDIA Performance Handbook): 헤드리스 뷰포트 끔 + CPU스레드 제한
app = SimulationApp({"headless": True, "width": 1280, "height": 720,
                     "disable_viewport_updates": True, "limit_cpu_threads": 8})

import os, math, json, random
import numpy as np
import cv2
import carb
from pxr import UsdGeom, UsdLux, Usd, Gf, Vt
import omni.usd
import omni.replicator.core as rep
from isaacsim.storage.native import get_assets_root_path

CITY = "/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.usd"
HDRI_DIR = "/home/karma/OSMtoUSD/assets/hdri"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
DS = os.path.join(OUT, "dataset_v1")
RUN = int(os.environ.get("RUN", "0"))
RAW = os.environ.get("RAW", "0") == "1"   # RAW=1: sensor_fx·글레어 후처리 끄고 순수 RTX 렌더 저장
if os.environ.get("SEED"): random.seed(int(os.environ["SEED"]))   # 검증용 재현성(같은 장면 A/B)
W, H, HAP = 1280, 720, 36.0
N_SEQ, SEQ_LEN, NEG_RATIO = int(os.environ.get("N_SEQ", "80")), 2, 0.15   # 프레임=N_SEQ*2. freeze는 SEQ_LEN=2로 우회
random.seed(100 + RUN*13)
def focal_of(h): return (HAP/2)/math.tan(math.radians(h)/2)

for d in ("images", "labels", "sequences"):
    os.makedirs(os.path.join(DS, d), exist_ok=True)
    if RUN == 0:
        for fpath in os.listdir(os.path.join(DS, d)): os.remove(os.path.join(DS, d, fpath))
_lf = open(os.path.join(OUT, f"run_v1_{RUN}.log"), "w")
def log(m): print(m, flush=True); _lf.write(str(m)+"\n"); _lf.flush()

s = carb.settings.get_settings(); s.set("/rtx/rendermode", "RaytracedLighting")
# 드론 기종 다양화(진단: 합성-only FN=다양 실드론. 우리 2종은 비대표적). 실드론 메쉬(PX4/gazebo, 풀메쉬 검증) 4종 추가.
MODELS = {"quad": "/Isaac/Robots/Bitcraze/Crazyflie/cf2x.usd",
          "heli": "/Isaac/Robots/NASA/Ingenuity/ingenuity.usd",
          "iris": "/home/karma/OSMtoUSD/assets/drones/iris_quad.usd",
          "px4vision": "/home/karma/OSMtoUSD/assets/drones/px4vision_quad.usd",
          "tailsitter": "/home/karma/OSMtoUSD/assets/drones/tailsitter_vtol.usd",
          "techpod": "/home/karma/OSMtoUSD/assets/drones/techpod_plane.usd",
          "phantom": "/home/karma/OSMtoUSD/assets/drones/phantom.usd"}   # ★실 DJI Phantom(115k, 사실적)
_mkeys = list(MODELS.keys())
model_name = _mkeys[RUN % len(_mkeys)]                         # RUN별 6종 순환
_mp = MODELS[model_name]
MODEL_USD = _mp if _mp.startswith("/home") else get_assets_root_path() + _mp   # 로컬 USD vs Isaac 에셋서버

# ★시부야 도시 복원(#4 배경문제: 하늘만 X → 지면·건물 보이게). open_stage + bbox 실측으로 씬스케일
omni.usd.get_context().open_stage(CITY)
for _ in range(15): app.update()
stage = omni.usd.get_context().get_stage()
up = UsdGeom.GetStageUpAxis(stage)
ui = 1 if up == 'Y' else 2; g1, g2 = ([0, 2] if up == 'Y' else [0, 1])
_wup = Gf.Vec3d(0, 1, 0) if up == 'Y' else Gf.Vec3d(0, 0, 1)
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange(); mn, mx = rng.GetMin(), rng.GetMax()
c1 = (mn[g1]+mx[g1])/2; c2 = (mn[g2]+mx[g2])/2; top = mx[ui]; ground = mn[ui]
gd = ((mx[g1]-mn[g1])**2+(mx[g2]-mn[g2])**2)**0.5

# 배경/조명(#3): puresky HDRI가 배경+조명 모두 담당(별도 DistantLight 제거 → 이중태양 불일치 해소).
# 표준 IBL: 돔 회전으로 태양 방위 변주, 강도만 랜덤. 지면없는 HDRI라 도시와 안 충돌.
HDRIS = sorted(f for f in os.listdir(HDRI_DIR) if f.endswith(".hdr"))
# ★모든 하늘 순환(사용자요청: 현실 하늘색 랜덤): 파랑·부분흐림·흐림·들판·노을·황혼 다양
hdri_name = HDRIS[RUN % len(HDRIS)]
HDRI = os.path.join(HDRI_DIR, hdri_name)
warm = any(k in hdri_name for k in ("sunset", "dawn", "dusk", "evening"))
dome = UsdLux.DomeLight.Define(stage, "/PoC_Sky")
dome.CreateIntensityAttr(float(os.environ.get("DOME_I", random.uniform(380, 700)))); dome.CreateTextureFileAttr(HDRI)  # ★순수 IBL, 밝기 다양(380~700, 사용자: 650선호). HDRI=태양+하늘 조명(보이는태양=비추는태양=방향 일치)
UsdGeom.Xformable(dome.GetPrim()).AddRotateYOp().Set(random.uniform(0, 360))   # 돔 회전=태양 방위 변주(조명·배경 같이 돌아 일관)

# 드론 참조 + 중심정렬/스케일
drone = UsdGeom.Xform.Define(stage, "/Drone"); dpos = UsdGeom.Xformable(drone).AddTranslateOp()
rs = UsdGeom.Xform.Define(stage, "/Drone/rs"); rsx = UsdGeom.Xformable(rs); sop = rsx.AddScaleOp(); rop = rsx.AddRotateXYZOp()
cen = UsdGeom.Xform.Define(stage, "/Drone/rs/centered"); cop = UsdGeom.Xformable(cen).AddTranslateOp()
cen.GetPrim().GetReferences().AddReference(MODEL_USD)
for _ in range(120): app.update()
mb = cache.ComputeWorldBound(stage.GetPrimAtPath("/Drone/rs/centered")).ComputeAlignedRange()
mmn, mmx = mb.GetMin(), mb.GetMax(); mc = [(mmn[i]+mmx[i])/2 for i in range(3)]; mext = max(mmx[i]-mmn[i] for i in range(3))
cop.Set(Gf.Vec3d(-mc[0], -mc[1], -mc[2])); S_world = gd*0.03; sop.Set(Gf.Vec3f(S_world/mext, S_world/mext, S_world/mext))
hv = [(mmx[i]-mmn[i])/2 for i in range(3)]   # 모델-중심 로컬 반치수(스케일 전; 스케일은 월드행렬에 포함)
from isaacsim.core.utils.semantics import add_update_semantics
add_update_semantics(stage.GetPrimAtPath("/Drone"), "drone")
UPX = -90.0 if up == 'Y' else 0.0

# 카메라 고정(RUN별 1시점) — FOV도 RUN별 변주(#3), fx_px 기록(solvePnP)
bg = "building" if RUN % 4 == 0 else "sky"   # 진단: 벤치=맑은하늘. 3/4 sky(도시지배 제거)
ang = RUN * 2.39996
hfov = random.uniform(50, 68); thw = math.tan(math.radians(hfov)/2)
FX_PX = (W/2)/thw   # solvePnP cameraMatrix: fx=fy=FX_PX, cx=W/2, cy=H/2
ep = [0, 0, 0]; Rr = gd*random.uniform(0.0, 0.28)   # ★도심 안(중심부근, 빌딩에 둘러싸인 지상센서). 시부야 밖 X
ep[g1] = c1+Rr*math.cos(ang); ep[g2] = c2+Rr*math.sin(ang); ep[ui] = max(ground, 0)+top*random.uniform(0.0, 0.12)  # 지상센서=낮은 높이
eye = Gf.Vec3d(*ep)
# 시선: 위(드론) 올려봄. 수직은 카메라basis 퇴화→pitch 38~68°로 제한, 방위 랜덤. 빌딩이 프레임 둘러쌈
look_az = math.radians(random.uniform(0, 360)); look_pitch = math.radians(random.uniform(8, 42)); _Ld = gd*0.3   # 낮은 pitch=빌딩 파사드/스카이라인 프레임진입, 높은건 하늘. 드론은 oy상단바이어스로 빌딩위 하늘
Lp = [0, 0, 0]
Lp[g1] = ep[g1] + _Ld*math.cos(look_pitch)*math.cos(look_az)
Lp[g2] = ep[g2] + _Ld*math.cos(look_pitch)*math.sin(look_az)
Lp[ui] = ep[ui] + _Ld*math.sin(look_pitch)
# ★USD 카메라 prim(transform 제어 → 빌딩속 검증 재배치 가능). FOV·투영은 rep.create.camera와 동일
camprim = UsdGeom.Camera.Define(stage, "/PoC_Cam")
camprim.CreateFocalLengthAttr(focal_of(hfov)); camprim.CreateHorizontalApertureAttr(HAP)
camprim.CreateClippingRangeAttr(Gf.Vec2f(0.05, 1e8))
_cam_mop = UsdGeom.Xformable(camprim).MakeMatrixXform()
def _basis(_eye, _Lp):
    _f = Gf.Vec3d(*_Lp) - _eye; _f = _f/_f.GetLength()
    _r = Gf.Cross(_f, _wup); _r = _r/_r.GetLength(); _u = Gf.Cross(_r, _f)
    return _f, _r, _u
def _place_cam(_eye, _f, _r, _u):   # 카메라 local: +X=r, +Y=u, +Z=-f(렌즈는 -Z), 위치=eye
    _cam_mop.Set(Gf.Matrix4d(_r[0], _r[1], _r[2], 0, _u[0], _u[1], _u[2], 0,
                             -_f[0], -_f[1], -_f[2], 0, _eye[0], _eye[1], _eye[2], 1))
rp = rep.create.render_product("/PoC_Cam", (W, H))
rgb_a = rep.AnnotatorRegistry.get_annotator("rgb")
box_a = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
for a in (rgb_a, box_a): a.attach([rp])   # 세그멘테이션 제거 → box annotator만
# 검증: 빌딩 속(렌더 near-black)이면 위치 회전·재배치해 밝은 곳 찾기(최대 6회). 셋업단계라 freeze 안전
f, r, u = _basis(eye, Lp)
for _ctry in range(6):
    _place_cam(eye, f, r, u)
    rep.orchestrator.step(rt_subframes=4); app.update()
    _mb = float(np.asarray(rgb_a.get_data()[:, :, :3]).mean())
    if _mb > 18: break                                          # 충분히 밝음 = 빌딩 밖
    ang += 1.7; Rr = gd*random.uniform(0.05, 0.30)              # 빌딩 속 → 위치 변경 후 재시도
    ep[g1] = c1+Rr*math.cos(ang); ep[g2] = c2+Rr*math.sin(ang); eye = Gf.Vec3d(*ep)
    Lp[g1] = ep[g1] + _Ld*math.cos(look_pitch)*math.cos(look_az)
    Lp[g2] = ep[g2] + _Ld*math.cos(look_pitch)*math.sin(look_az)
    Lp[ui] = ep[ui] + _Ld*math.sin(look_pitch)
    f, r, u = _basis(eye, Lp)
log(f"  cam검증: {_ctry+1}회시도 밝기={_mb:.0f}")
log(f"RUN={RUN} model={model_name} bg={bg} gd={gd:.0f} hdri={hdri_name} hfov={hfov:.0f} warm={warm}")

# --- 실제 메쉬 디스트랙터 (안티드론 혼동물, 웹검색기반: 새·비행기·풍선·나무·전선) ---
# drone semantic 안 붙임 → 자동 GT '드론 아님'. 시퀀스당 1회 배치(동결안전).
DIST_DIR = "/home/karma/OSMtoUSD/assets/distractors"
DBEHIND = Gf.Vec3d(eye[0]-f[0]*gd*9, eye[1]-f[1]*gd*9, eye[2]-f[2]*gd*9)
def dist_slot(usd, name):
    p = UsdGeom.Xform.Define(stage, f"/Dist/{name}")
    xf = UsdGeom.Xformable(p); ops = (xf.AddTranslateOp(), xf.AddScaleOp(), xf.AddRotateXYZOp())
    p.GetPrim().GetReferences().AddReference(usd); ops[0].Set(DBEHIND)
    return ops
_BIRD_USDS = ["gull0", "gull1", "gull2", "goose0", "goose1", "goose2"]   # 사용자제공 갈매기·거위 (색3변형씩)
random.shuffle(_BIRD_USDS)                                                # 런마다 다른 색조합
BIRD_SLOTS = [dist_slot(f"{DIST_DIR}/{_BIRD_USDS[i % 6]}.usd", f"bird{i}") for i in range(5)]   # 최중요 혼동물
ALL_SLOTS = BIRD_SLOTS                                # ★사용자요청: 새만 (나무·비행기·풍선·전선 제거)
_rr = lambda: random.uniform(0, 360)

def _place(ops, sz, Dd, oxf, oyf, rot):
    hwd = Dd*thw; hhd = hwd*H/W
    ops[1].Set(Gf.Vec3f(sz, sz, sz)); ops[2].Set(Gf.Vec3f(*rot))
    ops[0].Set(Gf.Vec3d(eye[0]+f[0]*Dd+r[0]*oxf*hwd+u[0]*oyf*hhd,
                        eye[1]+f[1]*Dd+r[1]*oxf*hwd+u[1]*oyf*hhd,
                        eye[2]+f[2]*Dd+r[2]*oxf*hwd+u[2]*oyf*hhd))

def place_distractors(scenario, D):
    """새만 배치(사용자요청). birds/negative=새 1~4마리, clean=없음."""
    for ops in ALL_SLOTS: ops[0].Set(DBEHIND)
    n = 0
    if scenario in ("birds", "negative"):            # 새 1~4마리(다양 크기·위치)
        for ops in random.sample(BIRD_SLOTS, random.randint(1, 4)):
            _place(ops, S_world*random.uniform(0.5, 1.5), D*random.uniform(0.5, 2.0),   # 드론과 비슷~더 큼(강한 혼동물)
                   random.uniform(-0.85, 0.85), random.uniform(-0.7, 0.7), (_rr(), _rr(), _rr())); n += 1
    return n

def project(P):
    """월드점 → 픽셀 [px,py,vis]. 카메라 고정 basis(f,r,u) 사용."""
    rel = P - eye; fc = rel[0]*f[0]+rel[1]*f[1]+rel[2]*f[2]
    if fc <= 1e-6: return [0.0, 0.0, 0]
    su = (rel[0]*r[0]+rel[1]*r[1]+rel[2]*r[2])/fc/thw
    sv = (rel[0]*u[0]+rel[1]*u[1]+rel[2]*u[2])/fc/(thw*H/W)
    px = (su*0.5+0.5)*W; py = (0.5-sv*0.5)*H
    vis = 2 if (0 <= px < W and 0 <= py < H) else 1
    return [round(px, 1), round(py, 1), vis]

def keypoints_9():
    """드론 3D박스 8모서리 + 중심 → 2D 투영(카메라상대 자세 인코딩)."""
    M = UsdGeom.Xformable(cen.GetPrim()).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    kp = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                Pw = M.Transform(Gf.Vec3d(sx*hv[0], sy*hv[1], sz*hv[2]))
                kp.append(project(Pw))
    kp.append(project(M.Transform(Gf.Vec3d(0, 0, 0))))   # 중심
    return kp

def parse(bb):
    recs = bb["data"]; id2 = bb["info"]["idToLabels"]
    def lab(sid):
        v = id2.get(sid, id2.get(str(sid), None)); return v.get("class", str(v)) if isinstance(v, dict) else str(v)
    bx = None
    for rr in recs:
        if "drone" in lab(int(rr["semanticId"])).lower():
            bx = (int(rr["x_min"]), int(rr["y_min"]), int(rr["x_max"]), int(rr["y_max"])); break
    npx = (bx[2]-bx[0])*(bx[3]-bx[1]) if bx else 0   # 박스 픽셀면적(seg 대체 가시성지표)
    return bx, npx

def motion_blur(img, sd, dids, dx, dy):
    disp = math.hypot(dx, dy); mask = np.isin(sd, dids).astype(np.float32)
    if disp < 3.0 or mask.sum() < 1: return img, None
    L = int(np.clip(disp*0.7, 5, 50)); ang2 = math.atan2(dy, dx); c = L//2
    k = np.zeros((L, L), np.float32)
    for i in range(L):
        x = int(round(c+(i-c)*math.cos(ang2))); y = int(round(c+(i-c)*math.sin(ang2)))
        if 0 <= x < L and 0 <= y < L: k[y, x] = 1.0
    k /= max(k.sum(), 1.0)
    dl = img.astype(np.float32)*mask[..., None]
    bd = cv2.filter2D(dl, -1, k); ba = cv2.filter2D(mask, -1, k)
    A = np.clip(ba, 0, 1)[..., None]; color = bd/np.clip(ba[..., None], 1e-3, None)
    out = np.clip(img.astype(np.float32)*(1-A)+color*A, 0, 255).astype(np.uint8)
    ys, xs = np.where(ba > 0.12)
    return out, ((int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())) if len(xs) else None)

# 센서/촬영 효과(#2) — Carlson et al. 2018 "Modeling Camera Effects"(arXiv 1803.07721) 검증 파이프라인.
# 순서: 색수차→블러→노출→노이즈→색이동 (φ_color(φ_noise(φ_exposure(φ_blur(φ_chrom(I)))))).
# 범위는 albumentations 표준기본값 앵커(임의수치 아님): GaussNoise var10~50, RandomGamma 80~120, RGBShift±20,
#   ImageCompression(JPEG), GaussianBlur blur_limit~3-7, ChromaticAberration.
# ★중요(Carlson): 증강은 픽셀만, 라벨은 원본(클린 지오메트리) 사용 → 흐릿/노이즈 드론도 정확박스 학습.
# 카메라설정=시퀀스당(같은 카메라), Gaussian 노이즈만 프레임별.
def sensor_params():
    w = warm
    return {"ca_scale": random.uniform(1.0, 1.012),                 # 색수차 longitudinal(green scale)
            "ca_shift": random.randint(0, 2),                       # 색수차 lateral(R/B 픽셀이동)
            "blur_sig": (random.uniform(0.4, 1.2) if random.random() < 0.4 else 0.0),  # 디포커스 블러
            "gamma": random.uniform(0.95, 1.15),                    # 노출(과노출 방지로 하한↑)
            "rgb_shift": (random.randint(2, 22) if w else random.randint(-18, 18),     # 색이동(RGBShift±20), 노을=R+/B-
                          random.randint(-12, 12),
                          random.randint(-22, -2) if w else random.randint(-18, 18)),
            "jpegq": random.randint(40, 90),                        # JPEG 압축(ImageCompression)
            "haze": random.uniform(0.0, 0.10),                      # 대기산란(원거리), 약하게
            "haze_col": (np.array([226, 208, 184], np.float32) if w else np.array([212, 218, 228], np.float32))}

def sensor_fx(img, sp, gnoise):
    o = img.astype(np.float32)
    # 1. 색수차(lens): green 채널 스케일(longitudinal) + R/B 횡이동(lateral)
    if sp["ca_scale"] > 1.0:
        s = sp["ca_scale"]; M = np.float32([[s, 0, (W/2)*(1-s)], [0, s, (H/2)*(1-s)]])
        o[..., 1] = cv2.warpAffine(o[..., 1], M, (W, H), borderMode=cv2.BORDER_REFLECT)
    if sp["ca_shift"]:
        o[..., 0] = np.roll(o[..., 0], sp["ca_shift"], axis=1); o[..., 2] = np.roll(o[..., 2], -sp["ca_shift"], axis=1)
    # 2. 디포커스 블러(lens)
    if sp["blur_sig"] > 0: o = cv2.GaussianBlur(o, (0, 0), sp["blur_sig"])
    # 3. 노출(sensor): gamma
    o = 255.0 * np.power(np.clip(o, 0, 255)/255.0, sp["gamma"])
    # 4. 노이즈(sensor): read(가우시안)+shot(신호의존). Poisson(λ)≈N(λ,√λ)라 가우시안근사(poisson~180ms→수ms, 시각동일)
    std = np.sqrt(gnoise*gnoise + 0.09*np.maximum(o, 0.0)).astype(np.float32)  # 0.09=0.3²(원래 shot계수)
    o = o + np.random.standard_normal(o.shape).astype(np.float32) * std
    # 5. 색이동(post): RGBShift
    o[..., 0] += sp["rgb_shift"][0]; o[..., 1] += sp["rgb_shift"][1]; o[..., 2] += sp["rgb_shift"][2]
    if sp["haze"] > 0: o = o*(1-sp["haze"]) + sp["haze_col"]*sp["haze"]
    o = np.clip(o, 0, 255).astype(np.uint8)
    # 6. JPEG 인코딩 → 바이트 직접 반환(디코딩 안 함=속도↑). RGB→BGR 스왑(cv2 JPEG는 BGR 가정 → 뷰어서 정상색)
    ok, enc = cv2.imencode(".jpg", o[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, sp["jpegq"]])
    return enc

pos = 0; tot = 0
SCENARIOS = ["clean", "birds", "birds", "negative"]   # 새만(사용자요청): birds 비중↑, negative=새만 드론없음
import time as _time
_T = {"render": 0.0, "data": 0.0, "fx": 0.0, "save": 0.0}   # ★측정용(임시)
for sq in range(N_SEQ):
    # ★체계적 커버(랜덤X): 전역 시퀀스 인덱스로 scale_bin·시나리오 격자 순환 → 모든 조합 균등
    gseq = RUN * N_SEQ + sq
    scale_bin = [0, 1, 2, 3, 1, 2, 3, 2][gseq % 8]   # #2: tiny 1/8로↓, near/medium 비중↑(먼것만 문제 해결)
    scenario = SCENARIOS[(gseq // 4) % len(SCENARIOS)]   # clean/birds/birds/negative 순환
    is_neg = (scenario == "negative")             # negative=드론없이 혼동물만
    ftype = random.choice(["hover", "cruise", "maneuver"])
    pose_euler = (UPX+random.uniform(-25, 25), random.uniform(0, 360), random.uniform(-25, 25))
    rop.Set(Gf.Vec3f(*pose_euler))
    # 스케일 = scale_bin 결정(bin 내 랜덤). base_px≈gd*33/x(x=D/gd)
    if scale_bin == 0:   D = gd * random.uniform(1.5, 7.0)    # tiny <20px (원거리)
    elif scale_bin == 1: D = gd * random.uniform(0.6, 1.5)    # small 20~50px
    elif scale_bin == 2: D = gd * random.uniform(0.3, 0.6)    # medium 50~110px (벤치)
    else:                D = gd * random.uniform(0.15, 0.3)   # large >120px (근접)
    base_px = S_world*W/(2*D*thw); hw = D*thw; hh = hw*H/W
    o0 = (random.uniform(-0.75, 0.75)*hw, random.uniform(-0.25, 0.85)*hh)   # oy 상단(하늘) 바이어스: 빌딩가림 회피 + 일부 하단(건물앞 근접드론)
    vel = (random.uniform(-0.07, 0.07)*hw, random.uniform(-0.06, 0.06)*hh)
    nd = place_distractors(scenario, D)
    sp = sensor_params()
    backlit = random.random() < 0.30          # 메타데이터(기록용). 역광 실루엣은 이제 HDRI 자연조명이 처리
    # dtint/sil 제거: seg 마스크 없앰(속도↑). 드론 색·외형은 실드론 메쉬 재질이 담당
    glare = random.random() < 0.28            # 태양 글레어/블룸(드론이 햇빛에 씻김 = 실제 최난도)
    glare_add = None
    if glare:
        gpx = (random.randint(int(W*0.12), int(W*0.88)), random.randint(0, int(H*0.45)))
        gr = random.uniform(70, 220); gi = random.uniform(70, 175)
        _gy, _gx = np.ogrid[0:H, 0:W]
        _gm = gi*np.exp(-(((_gx-gpx[0])**2 + (_gy-gpx[1])**2)/(2*gr**2)))
        glare_add = (_gm[..., None]*np.array([1.0, 0.96, 0.86], np.float32))
    tid = RUN*100 + sq
    seq = {"run": RUN, "seq_id": sq, "track_id": tid, "model": model_name, "background": bg,
           "negative": is_neg, "flight_state": ("none" if is_neg else ftype), "ego_motion": [0.0, 0.0, 0.0],
           "n_distractors": nd, "cam_hfov": round(hfov, 1), "fx_px": round(FX_PX, 1), "hdri": hdri_name,
           "sensor": {"jpegq": sp["jpegq"], "gamma": round(sp["gamma"], 2),
                      "blur_sig": round(sp["blur_sig"], 2), "haze": round(sp["haze"], 2)},
           "backlit": backlit, "glare": glare,
           "pose_euler_world": [round(p, 1) for p in pose_euler], "frames": []}
    prev = None; prevc = None
    for fr in range(SEQ_LEN):
        if ftype == "hover":
            ox = o0[0]+random.uniform(-0.02, 0.02)*hw; oy = o0[1]+random.uniform(-0.02, 0.02)*hh
        elif ftype == "cruise":
            ox = o0[0]+vel[0]*fr; oy = o0[1]+vel[1]*fr
        else:
            ox = o0[0]+0.4*hw*math.sin(0.6*fr); oy = o0[1]+vel[1]*fr
        ox = max(-0.78*hw, min(0.78*hw, ox)); oy = max(-0.78*hh, min(0.78*hh, oy))
        d3 = Gf.Vec3d(eye[0]+f[0]*D+r[0]*ox+u[0]*oy, eye[1]+f[1]*D+r[1]*ox+u[1]*oy, eye[2]+f[2]*D+r[2]*ox+u[2]*oy)
        if is_neg:
            d3 = Gf.Vec3d(eye[0]-f[0]*D*6, eye[1]-f[1]*D*6, eye[2]-f[2]*D*6)
        pf = (pose_euler[0]+12.0*math.sin(fr*0.5), pose_euler[1]+fr*5.0, pose_euler[2]+10.0*math.cos(fr*0.5))
        rop.Set(Gf.Vec3f(*pf))                                  # per-frame 회전(16스텝 동결임계 아래)
        dpos.Set(d3)
        _t0 = _time.perf_counter()
        for _ in range(2): app.update()
        rep.orchestrator.step(rt_subframes=5); app.update()
        _t1 = _time.perf_counter(); _T["render"] += _t1 - _t0
        bx, npx = parse(box_a.get_data())
        rgb = np.array(rgb_a.get_data()[:, :, :3])
        _t2 = _time.perf_counter(); _T["data"] += _t2 - _t1
        # ★dtint/backlit 픽셀조정 제거(seg 마스크 없앰=속도↑): 드론 색·외형은 실드론 메쉬 재질이 담당
        if not RAW and glare_add is not None:                  # 태양 글레어(전역 가산). RAW면 생략
            rgb = np.clip(rgb.astype(np.float32) + glare_add, 0, 255).astype(np.uint8)
        fid = f"r{RUN}s{sq}f{fr}"
        cxy = ((bx[0]+bx[2])/2, (bx[1]+bx[3])/2) if (bx and not is_neg) else None
        prevc = cxy   # ★모션블러(streak) 비활성: 실드론은 줄무늬 블러 없음. '흐림'은 sensor_fx 디포커스 blur가 담당
        _t3 = _time.perf_counter()
        if RAW:                                                # 후처리 없이 순수 RTX 렌더 → JPEG q95
            _ok, jpg = cv2.imencode(".jpg", rgb[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 95])
        else:
            jpg = sensor_fx(rgb, sp, random.uniform(1.0, 5.0))   # 센서효과 → JPEG 바이트
        _t4 = _time.perf_counter(); _T["fx"] += _t4 - _t3
        jpg.tofile(os.path.join(DS, "images", fid+".jpg"))   # ★바이트 직접 write(.jpg, 재인코딩 없음). 실데이터도 jpg라 더 현실적
        _T["save"] += _time.perf_counter() - _t4
        vel3 = [0.0, 0.0, 0.0] if prev is None else [d3[i]-prev[i] for i in range(3)]; prev = d3
        dist_m = round((D/gd)*100.0, 1)   # 합성 거리 매핑: D=gd*0.13→13m … gd*5→500m
        rec = {"frame": fr, "file": fid+".jpg", "model": ("none" if is_neg else model_name),
               "flight_state": ("none" if is_neg else ftype),
               "pose_euler": [round(p, 1) for p in pf],   # per-frame 자세(매프레임 변함, 동결버그 해결)
               "drone_pos3d": [round(d3[i], 2) for i in range(3)], "vel3d": [round(v, 2) for v in vel3]}
        lbl = open(os.path.join(DS, "labels", fid+".txt"), "w")
        if (not is_neg) and bx is not None and npx >= 1:
            cx = (bx[0]+bx[2])/2/W; cy = (bx[1]+bx[3])/2/H; bw = (bx[2]-bx[0])/W; bh = (bx[3]-bx[1])/H
            lbl.write(f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")
            pmin = min(bx[2]-bx[0], bx[3]-bx[1])
            rec["bbox_xywh_norm"] = [round(cx, 5), round(cy, 5), round(bw, 5), round(bh, 5)]
            rec["px"] = bx[2]-bx[0]; rec["bbox_min_px"] = pmin
            rec["distance_m"] = dist_m
            rec["keypoints"] = keypoints_9()           # 카메라상대 자세 (8모서리+중심)
            rec["pose_valid"] = bool(pmin >= 20)       # 너무 작으면 자세 supervision 끔
            pos += 1
        else:
            rec["bbox_xywh_norm"] = None
        lbl.close(); seq["frames"].append(rec); tot += 1
    json.dump(seq, open(os.path.join(DS, "sequences", f"r{RUN}s{sq}.json"), "w"), indent=2)
    log(f"  seq{sq}: model={model_name} ftype={seq['flight_state']} neg={is_neg} dist≈{(D/gd)*100:.0f}m distractors={nd}")
log(f"=== RUN {RUN} 완료: {tot}프레임 {pos}양성 ===")
_n = max(tot, 1)
log(f"★측정/프레임: render={_T['render']/_n*1000:.0f}ms data={_T['data']/_n*1000:.0f}ms "
    f"fx={_T['fx']/_n*1000:.0f}ms save={_T['save']/_n*1000:.0f}ms "
    f"| 합={(_T['render']+_T['data']+_T['fx']+_T['save'])/_n*1000:.0f}ms")
app.close()
