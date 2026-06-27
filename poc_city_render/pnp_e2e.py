"""PnP end-to-end + 오차 추출 (사용자 요청: 실제 PnP 오차 뽑아 개선).
① YOLO11-pose가 9 keypoint 예측 → ② cv2.solvePnP → 6-DoF 포즈
오차: (a) keypoint 2D px오차(검출 정확도) (b) PnP 재투영오차 (c) 회전오차(deg, pred vs GT keypoint기반 PnP)
GT keypoint는 sequences에 있음. 모델별 큐보이드 비율로 objectPoints."""
import json, glob, os, numpy as np, cv2
from ultralytics import YOLO

W, H = 1280, 720
cx, cy = W/2, H/2
ASPECT = {"quad": (0.78, 0.31), "heli": (0.78, 0.47),
          "iris": (0.78, 0.31), "px4vision": (0.78, 0.31),
          "tailsitter": (0.78, 0.47), "techpod": (0.78, 0.47)}  # pnp_demo 추정값(기본)

def objp(b, c):
    o = [[sx, sy*b, sz*c] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    o.append([0, 0, 0]); return np.array(o, np.float32)

def rot_err_deg(r1, r2):
    R1, _ = cv2.Rodrigues(r1); R2, _ = cv2.Rodrigues(r2)
    Rr = R1.T @ R2
    return float(np.degrees(np.arccos(np.clip((np.trace(Rr)-1)/2, -1, 1))))

MODEL = "runs/pose1/weights/best.pt"
m = YOLO(MODEL)
# GT keypoint 룩업 (file→ kp, fx, model)
gt = {}
for jf in glob.glob("dataset_v1/sequences/*.json"):
    d = json.load(open(jf)); fx = d.get("fx_px"); mdl = d.get("model", "quad")
    if not fx: continue
    for fr in d["frames"]:
        if fr.get("keypoints") and fr.get("pose_valid"):
            gt[fr["file"]] = (np.array([[k[0], k[1]] for k in fr["keypoints"]], np.float32),
                              np.array([k[2] for k in fr["keypoints"]]) >= 1, fx, mdl)

kp_errs, reproj_errs, rot_errs = [], [], []
val_imgs = glob.glob("dataset_pose/images/val/*")
for img in val_imgs:
    fn = os.path.basename(img)
    if fn not in gt: continue
    gkp, gvis, fx, mdl = gt[fn]
    K = np.array([[fx, 0, cx], [0, fx, cy], [0, 0, 1]], np.float32)
    b, c = ASPECT.get(mdl, (0.78, 0.4)); ob = objp(b, c)
    r = m.predict(img, imgsz=1280, verbose=False)[0]
    if r.keypoints is None or len(r.keypoints) == 0: continue
    pk = r.keypoints.data[0].cpu().numpy()      # (9,3) x,y,conf
    pkp = pk[:, :2].astype(np.float32)
    # (a) keypoint px 오차 (가시 GT 기준)
    kp_errs.append(float(np.linalg.norm(pkp[gvis] - gkp[gvis], axis=1).mean()))
    # PnP: 예측 keypoint, GT keypoint
    okp, rvp, tvp = cv2.solvePnP(ob[gvis], pkp[gvis], K, None, flags=cv2.SOLVEPNP_ITERATIVE)
    okg, rvg, tvg = cv2.solvePnP(ob[gvis], gkp[gvis], K, None, flags=cv2.SOLVEPNP_ITERATIVE)
    if not (okp and okg): continue
    rp, _ = cv2.projectPoints(ob[gvis], rvp, tvp, K, None)
    reproj_errs.append(float(np.linalg.norm(rp.reshape(-1, 2) - gkp[gvis], axis=1).mean()))
    rot_errs.append(rot_err_deg(rvp, rvg))

def stat(a, u):
    a = np.array(a)
    return f"평균 {a.mean():.2f}{u} 중앙 {np.median(a):.2f}{u}" if len(a) else "N/A"

print(f"PnP end-to-end 오차 ({len(kp_errs)} val 프레임):", flush=True)
print(f"  (a) keypoint 검출 2D오차: {stat(kp_errs,'px')}")
print(f"  (b) PnP 재투영오차:       {stat(reproj_errs,'px')}")
print(f"  (c) 회전오차(pred vs GT): {stat(rot_errs,'deg')}")
print(f"SUMMARY kp={np.median(kp_errs):.1f}px reproj={np.median(reproj_errs):.1f}px rot={np.median(rot_errs):.1f}deg" if kp_errs else "no data")
