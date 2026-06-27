"""안티드론 합성데이터 v1 생성기 (env RUN별 1시점=카메라 고정, 동결 회피).
GT: 위치(2D박스) + 거리(distance_m) + 자세(keypoints=3D박스 8모서리 투영, 카메라상대) + 기종(model).
기종 2종(쿼드 cf2x / 헬기 ingenuity) RUN별 교대. 모션블러(드론만) + 원거리 tiny + 네거티브 + 시계열.
RUN당 16프레임(동결 임계 아래). run_v1_all.sh가 RUN 0~9 순차. RUN=0만 초기화."""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1280, "height": 720})

import os, math, json, random
import numpy as np
import cv2
import carb
from PIL import Image
from pxr import UsdGeom, UsdLux, Usd, Gf, Vt
import omni.usd
import omni.replicator.core as rep
from isaacsim.storage.native import get_assets_root_path

CITY = "/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.usd"
HDRI_DIR = "/home/karma/OSMtoUSD/assets/hdri"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
DS = os.path.join(OUT, "dataset_v1")
RUN = int(os.environ.get("RUN", "0"))
W, H, HAP = 1280, 720, 36.0
N_SEQ, SEQ_LEN, NEG_RATIO = 8, 2, 0.15   # 다양성↑: 런당 distinct 셋업(거리·색·자세) 2→8개(4배), 같은 16프레임(freeze write수 동일)
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
          "techpod": "/home/karma/OSMtoUSD/assets/drones/techpod_plane.usd"}
_mkeys = list(MODELS.keys())
model_name = _mkeys[RUN % len(_mkeys)]                         # RUN별 6종 순환
_mp = MODELS[model_name]
MODEL_USD = _mp if _mp.startswith("/home") else get_assets_root_path() + _mp   # 로컬 USD vs Isaac 에셋서버

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
# 진단: 벤치=쨍한 파란 주광. 파란 HDRI(kloofendal clear/partly)만 70%, 나머지 다양성 30%.
_blue = [h for h in HDRIS if any(k in h for k in ("43d_clear", "38d_partl", "48d_partl"))]
_other = [h for h in HDRIS if not any(k in h for k in ("sunset", "dawn", "dusk", "evening", "overcast"))]
if _blue and random.random() < 0.7:
    hdri_name = _blue[(RUN*3 + 1) % len(_blue)]
elif _other:
    hdri_name = _other[(RUN*5 + 3) % len(_other)]
else:
    hdri_name = HDRIS[(RUN*5 + 3) % len(HDRIS)]
HDRI = os.path.join(HDRI_DIR, hdri_name)
warm = any(k in hdri_name for k in ("sunset", "dawn", "dusk", "evening"))
dome = UsdLux.DomeLight.Define(stage, "/PoC_Sky")
dome.CreateIntensityAttr(random.uniform(400, 750)); dome.CreateTextureFileAttr(HDRI)  # 과노출 방지(쨍한 파란하늘)
UsdGeom.Xformable(dome.GetPrim()).AddRotateYOp().Set(random.uniform(0, 360))

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
ep = [0, 0, 0]; Rr = gd*0.85
ep[g1] = c1+Rr*math.cos(ang); ep[g2] = c2+Rr*math.sin(ang); ep[ui] = max(ground, 0)+top*random.uniform(0.15, 0.35)
eye = Gf.Vec3d(*ep)
# sky: 훨씬 위로 봐서 프레임 대부분 깨끗한 하늘(벤치 매칭, 도시 화면밖). building: 도시+지평선 일부 유지.
Lp = [0, 0, 0]; Lp[g1] = c1; Lp[g2] = c2; Lp[ui] = top*(random.uniform(1.0, 1.5) if bg == "building" else random.uniform(1.7, 2.8))
cam = rep.create.camera(position=tuple(eye), look_at=tuple(Lp), focal_length=focal_of(hfov), horizontal_aperture=HAP, clipping_range=(0.05, 1e8))
rp = rep.create.render_product(cam, (W, H))
rgb_a = rep.AnnotatorRegistry.get_annotator("rgb")
box_a = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
seg_a = rep.AnnotatorRegistry.get_annotator("semantic_segmentation", init_params={"colorize": False})
for a in (rgb_a, box_a, seg_a): a.attach([rp])
f = (Gf.Vec3d(*Lp)-eye); f = f/f.GetLength(); r = Gf.Cross(f, _wup); r = r/r.GetLength(); u = Gf.Cross(r, f)
log(f"RUN={RUN} model={model_name} bg={bg} gd={gd:.0f} hdri={hdri_name} hfov={hfov:.0f} warm={warm}")

# --- 하드네거티브 디스트랙터 풀(새·비행기·풍선 모사) ---
# drone semantic 안 붙임 → 자동 GT가 '드론 아님'으로 처리. 위치는 시퀀스당 1회만(동결안전).
# 실제 안티드론 디스트랙터는 대부분 '작고 어두운 새 점'(드론과 닮아 헷갈림). 큰 흰 풍선은 비현실 → 제거.
DSPEC = [
    ("Sphere",  (0.60, 0.50, 0.55), (0.12, 0.11, 0.10), 0.50),  # 작은 어두운 새 점
    ("Capsule", (0.30, 0.30, 1.30), (0.10, 0.10, 0.11), 0.50),  # 작은 검은 새(길쭉)
    ("Cone",    (0.50, 0.50, 0.80), (0.14, 0.13, 0.12), 0.50),  # 새 실루엣
    ("Sphere",  (0.55, 0.45, 0.50), (0.19, 0.16, 0.13), 0.55),  # 갈색 새
    ("Capsule", (0.35, 0.35, 1.90), (0.40, 0.42, 0.46), 0.90),  # 원거리 비행기(작고 회색)
    ("Cube",    (1.70, 0.18, 0.45), (0.44, 0.46, 0.50), 0.80),  # 원거리 비행기 날개(작게)
]
DBEHIND = Gf.Vec3d(eye[0]-f[0]*gd*9, eye[1]-f[1]*gd*9, eye[2]-f[2]*gd*9)  # 카메라 뒤(숨김)
DPOOL = []
for di, (shp, svec, col, sz) in enumerate(DSPEC):
    pp = getattr(UsdGeom, shp).Define(stage, f"/Distractors/d{di}")
    xf = UsdGeom.Xformable(pp); dtop = xf.AddTranslateOp()
    K = S_world*0.5*sz
    xf.AddScaleOp().Set(Gf.Vec3f(svec[0]*K, svec[1]*K, svec[2]*K))
    xf.AddRotateXYZOp().Set(Gf.Vec3f(random.uniform(0, 360), random.uniform(0, 360), random.uniform(0, 360)))
    pp.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*col)]))
    dtop.Set(DBEHIND)
    DPOOL.append(dtop)

def place_distractors(is_neg, D):
    """시퀀스당 1회: 일부 디스트랙터를 시야 안에, 나머지는 카메라 뒤로. 드론라벨 영향 없음(semantic 없음)."""
    n = random.choice([2, 3, 3, 4]) if is_neg else random.choice([0, 1, 1, 2, 2, 3])
    idxs = set(random.sample(range(len(DPOOL)), min(n, len(DPOOL))))
    for j, dtop in enumerate(DPOOL):
        if j in idxs:
            Dd = D*random.uniform(0.7, 2.0); hwd = Dd*thw; hhd = hwd*H/W
            ox = random.uniform(-0.8, 0.8)*hwd; oy = random.uniform(-0.65, 0.65)*hhd
            dtop.Set(Gf.Vec3d(eye[0]+f[0]*Dd+r[0]*ox+u[0]*oy,
                              eye[1]+f[1]*Dd+r[1]*ox+u[1]*oy,
                              eye[2]+f[2]*Dd+r[2]*ox+u[2]*oy))
        else:
            dtop.Set(DBEHIND)
    return len(idxs)

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

def parse(bb, seg):
    recs = bb["data"]; id2 = bb["info"]["idToLabels"]
    def lab(sid):
        v = id2.get(sid, id2.get(str(sid), None)); return v.get("class", str(v)) if isinstance(v, dict) else str(v)
    bx = None
    for rr in recs:
        if "drone" in lab(int(rr["semanticId"])).lower():
            bx = (int(rr["x_min"]), int(rr["y_min"]), int(rr["x_max"]), int(rr["y_max"])); break
    sd = np.asarray(seg["data"]); s2 = seg["info"]["idToLabels"]
    dids = [int(k) for k, v in s2.items() if "drone" in str(v).lower()]
    return bx, int(np.isin(sd, dids).sum()), sd, dids

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
    # 4. 노이즈(sensor): Poisson-Gaussian (signal-dependent + independent)
    o = o + np.random.normal(0, gnoise, o.shape)                    # Gaussian(var~10-50→std 3-7)
    pois = np.random.poisson(np.clip(o, 0, None)).astype(np.float32)
    o = o + (pois - o) * 0.3                                        # signal-dependent
    # 5. 색이동(post): RGBShift
    o[..., 0] += sp["rgb_shift"][0]; o[..., 1] += sp["rgb_shift"][1]; o[..., 2] += sp["rgb_shift"][2]
    if sp["haze"] > 0: o = o*(1-sp["haze"]) + sp["haze_col"]*sp["haze"]
    o = np.clip(o, 0, 255).astype(np.uint8)
    # 6. JPEG 압축(최종 인코딩)
    ok, enc = cv2.imencode(".jpg", o, [cv2.IMWRITE_JPEG_QUALITY, sp["jpegq"]])
    return cv2.imdecode(enc, cv2.IMREAD_COLOR) if ok else o

pos = 0; tot = 0
for sq in range(N_SEQ):
    is_neg = random.random() < NEG_RATIO
    ftype = random.choice(["hover", "cruise", "maneuver"])
    # 자세: 시퀀스마다 다양화(per-frame rop는 동결 트리거 → seq당 1회)
    pose_euler = (UPX+random.uniform(-25, 25), random.uniform(0, 360), random.uniform(-25, 25))
    rop.Set(Gf.Vec3f(*pose_euler))
    # 스케일분포(진단: 벤치=또렷한 중간드론. tiny만 말고 중간/근접 비중↑). base_px≈gd*33/x(x=D/gd).
    if bg == "building":
        D = gd * (random.uniform(0.7, 2.0) if random.random() < 0.4 else random.uniform(0.18, 0.7))
    else:                                    # sky: 멀티스케일(tiny+중간+근접)
        r0 = random.random()
        if r0 < 0.35:   D = gd * random.uniform(1.5, 7.0)    # 원거리 tiny (px≈5~22) — 원거리 deployment
        elif r0 < 0.75: D = gd * random.uniform(0.3, 1.0)    # 중간 (px≈33~110) — 벤치 매칭
        else:           D = gd * random.uniform(0.15, 0.35)  # 근접 (px≈94~220) — 또렷한 드론
    base_px = S_world*W/(2*D*thw); hw = D*thw; hh = hw*H/W
    o0 = (random.uniform(-0.35, 0.35)*hw, random.uniform(-0.30, 0.30)*hh)
    vel = (random.uniform(-0.07, 0.07)*hw, random.uniform(-0.06, 0.06)*hh)
    nd = place_distractors(is_neg, D)
    sp = sensor_params()
    backlit = random.random() < 0.30          # 역광/실루엣(안티드론 최난도): 밝은하늘 vs 노출부족 드론
    sil = random.uniform(0.12, 0.42)
    dtint = None                              # 드론 외형 DR — A3: 현실적 무채색(진단:실드론=흰/검정/회색, 랜덤색은 비현실적이라 A2서 깎임)
    if not backlit:
        cpick = random.random()                          # ⚠️카메라 basis r과 충돌 금지(전에 r= 썼다 크래시)
        if cpick < 0.45:   b = random.uniform(0.22, 0.5)    # 검정/진회색 (DJI 다수)
        elif cpick < 0.7:  b = random.uniform(1.7, 3.3)     # 흰 (Phantom)
        else:              b = random.uniform(0.6, 1.15)    # 중간 회색
        tiny = random.uniform(0.96, 1.04)               # 미세 색온도만(컬러캐스트 X)
        dtint = np.array([b, b*tiny, b*random.uniform(0.96, 1.04)], np.float32)
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
        for _ in range(6): app.update()
        rep.orchestrator.step(rt_subframes=14); app.update()
        bx, npx, sd, dids = parse(box_a.get_data(), seg_a.get_data())
        rgb = np.array(rgb_a.get_data()[:, :, :3])
        if not is_neg and dids:                                 # 드론 픽셀 외형 조정(라벨=지오메트리라 무관)
            dm = np.isin(sd, dids)
            if dm.any():
                if backlit:                                     # 역광: 노출부족 실루엣
                    rgb[dm] = (rgb[dm].astype(np.float32)*sil).astype(np.uint8)
                elif dtint is not None:                         # 외형 DR: 색/밝기 리버리
                    rgb[dm] = np.clip(rgb[dm].astype(np.float32)*dtint, 0, 255).astype(np.uint8)
        if glare_add is not None:                               # 태양 글레어(전역 가산)
            rgb = np.clip(rgb.astype(np.float32) + glare_add, 0, 255).astype(np.uint8)
        fid = f"r{RUN}s{sq}f{fr}"
        cxy = ((bx[0]+bx[2])/2, (bx[1]+bx[3])/2) if (bx and not is_neg) else None
        if cxy and prevc:
            rgb, nb = motion_blur(rgb, sd, dids, cxy[0]-prevc[0], cxy[1]-prevc[1])
            if nb: bx = nb
        prevc = cxy
        rgb = sensor_fx(rgb, sp, random.uniform(1.0, 5.0))    # #2 센서효과(노이즈 줄임 — 벤치는 깔끔)
        Image.fromarray(rgb).save(os.path.join(DS, "images", fid+".png"))
        vel3 = [0.0, 0.0, 0.0] if prev is None else [d3[i]-prev[i] for i in range(3)]; prev = d3
        dist_m = round((D/gd)*100.0, 1)   # 합성 거리 매핑: D=gd*0.13→13m … gd*5→500m
        rec = {"frame": fr, "file": fid+".png", "model": ("none" if is_neg else model_name),
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
app.close()
