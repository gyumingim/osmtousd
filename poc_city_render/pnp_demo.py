"""PnP 6-DoF 포즈 추정 데모/검증.
합성 GT 9-keypoint(큐보이드 8모서리+중심) + 3D 큐보이드 + 카메라내부(fx_px)
→ cv2.solvePnP → 카메라상대 6-DoF 포즈(rvec,tvec) 복원.
큐보이드 비율(a:b:c)은 모델(quad/heli)마다 다름 → 데이터에서 재투영오차 최소화로 추정(=캘리브).
검증: 재투영오차(정확투영이라 올바른 비율이면 ~0). 시각화: 3D박스+축 오버레이.
실파이프라인: YOLO11-pose가 9 keypoint 예측 → 동일 solvePnP (여기선 GT keypoint로 PnP 단계 입증)."""
import json, glob, numpy as np, cv2, random
random.seed(1)
W, H = 1280, 720
cx, cy = W/2, H/2
EDGES = [(0,1),(0,2),(0,4),(1,3),(1,5),(2,3),(2,6),(3,7),(4,5),(4,6),(5,7),(6,7)]

def objp(b, c):  # half-dims (1,b,c), keypoints_9 순서 + center
    o = [[sx, sy*b, sz*c] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    o.append([0, 0, 0]); return np.array(o, np.float32)

def pnp(obj, img2d, vis, K):
    ok, rvec, tvec = cv2.solvePnP(obj[vis], img2d[vis], K, None, flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok: return None
    rp, _ = cv2.projectPoints(obj[vis], rvec, tvec, K, None)
    err = float(np.linalg.norm(rp.reshape(-1, 2) - img2d[vis], axis=1).mean())
    return rvec, tvec, err

# 프레임 로드 (모델별)
frames = {}
for jf in glob.glob("dataset_v1/sequences/*.json"):
    d = json.load(open(jf)); fx = d.get("fx_px"); model = d.get("model", "?")
    if not fx: continue
    K = np.array([[fx, 0, cx], [0, fx, cy], [0, 0, 1]], np.float32)
    for fr in d["frames"]:
        kp = fr.get("keypoints")
        if not kp or not fr.get("pose_valid"): continue
        img2d = np.array([[k[0], k[1]] for k in kp], np.float32)
        vis = np.array([k[2] for k in kp]) >= 1
        if vis.sum() < 6: continue
        frames.setdefault(model, []).append((fr["file"], img2d, vis, K, fr.get("distance_m"), fr.get("px", 0)))

# 모델별 큐보이드 비율(b,c) 추정 = 재투영오차 최소화 (coarse→fine grid)
aspect = {}
for model, fl in frames.items():
    samp = random.sample(fl, min(40, len(fl)))
    best = (1, 1, 1e9)
    grid = np.linspace(0.15, 2.2, 14)
    for b in grid:
        for c in grid:
            ob = objp(b, c)
            es = [pnp(ob, i2, v, K) for _, i2, v, K, _, _ in samp]
            es = [e[2] for e in es if e]
            if es:
                me = np.median(es)
                if me < best[2]: best = (b, c, me)
    aspect[model] = (best[0], best[1])
    print(f"model={model}: 큐보이드 비율 a:b:c = 1:{best[0]:.2f}:{best[1]:.2f} | 추정후 재투영오차 중앙 {best[2]:.2f}px", flush=True)

# 전체 검증 + 시각화용 수집 (큰 드론 위주)
errs = []; demos = []
for model, fl in frames.items():
    b, c = aspect[model]; ob = objp(b, c)
    for f, img2d, vis, K, dm, px in fl:
        r = pnp(ob, img2d, vis, K)
        if not r: continue
        rvec, tvec, err = r; errs.append(err)
        if px >= 90 and err < 4:   # 큰 드론 + 잘맞은 것 → 시각화
            demos.append((f, rvec, tvec, K, dm, err, b, c))
errs = np.array(errs)
print(f"\nPnP 검증(비율추정후): {len(errs)}프레임 | 재투영오차 평균 {errs.mean():.2f}px 중앙 {np.median(errs):.2f}px")

def draw(img, rvec, tvec, K, b, c):
    proj, _ = cv2.projectPoints(objp(b, c)[:8], rvec, tvec, K, None)
    p = proj.reshape(-1, 2).astype(int)
    for a2, b2 in EDGES: cv2.line(img, tuple(p[a2]), tuple(p[b2]), (0, 255, 0), 2)
    ax = np.array([[0,0,0],[1.2,0,0],[0,1.2*b,0],[0,0,1.2*c]], np.float32)
    a2, _ = cv2.projectPoints(ax, rvec, tvec, K, None); a2 = a2.reshape(-1,2).astype(int)
    for i, col in [(1,(0,0,255)),(2,(0,255,0)),(3,(255,0,0))]:
        cv2.arrowedLine(img, tuple(a2[0]), tuple(a2[i]), col, 3, tipLength=0.3)

random.shuffle(demos); sel = demos[:8]
T = 330; sh = np.full((2*T+46, 4*T, 3), 26, np.uint8)
cv2.putText(sh, "PnP 6-DoF pose from synthetic keypoints (cv2.solvePnP): 3D box + orientation axes",
            (14, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 255, 120), 2)
for i, (f, rvec, tvec, K, dm, err, b, c) in enumerate(sel):
    img = cv2.imread("dataset_v1/images/" + f)
    if img is None: continue
    # 드론 중심으로 크롭(확대) 후 축 그리기 위해 원본에 그리고 크롭
    draw(img, rvec, tvec, K, b, c)
    proj, _ = cv2.projectPoints(objp(b, c), rvec, tvec, K, None); pc = proj.reshape(-1, 2)
    mx, my = pc[:, 0].mean(), pc[:, 1].mean(); s = 150
    x1 = int(np.clip(mx-s, 0, W-2*s)); y1 = int(np.clip(my-s, 0, H-2*s))
    crop = img[y1:y1+2*s, x1:x1+2*s]
    cv2.putText(crop, f"{dm:.0f}m  err {err:.1f}px" if dm else f"err {err:.1f}px", (6, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 120), 2)
    r, cc = divmod(i, 4); sh[46+r*T:46+r*T+T, cc*T:cc*T+T] = cv2.resize(crop, (T, T))
cv2.imwrite("../results/presentation_pnp_pose.png", sh)
print("저장 results/presentation_pnp_pose.png")
