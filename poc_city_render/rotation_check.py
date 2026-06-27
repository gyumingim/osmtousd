"""PnP 회전 복원 검증 (사용자 요청: 회전오차).
시퀀스 내 카메라 고정 → R_cam->world = R_solvePnP · R_drone_world⁻¹ 가 모든 프레임 동일해야 함.
그 흩어짐(도) = 회전 복원 오차. (GT keypoint 기준 = 이상적 상한; 검출기 오차는 pnp_e2e.py)
주의: USD RotateXYZOp = scipy 'xyz'(extrinsic). 'XYZ'(intrinsic) 쓰면 41° 오판."""
import json, glob, numpy as np, cv2
from scipy.spatial.transform import Rotation as Rsc

W, H = 1280, 720
cx, cy = W/2, H/2
ASP = {"quad": (0.78, 0.31), "heli": (0.78, 0.47), "iris": (0.78, 0.31),
       "px4vision": (0.78, 0.31), "tailsitter": (0.78, 0.47), "techpod": (0.78, 0.47)}
CONV = "xyz"   # USD RotateXYZOp = extrinsic xyz (규약확인: 이게 2°, 나머지 21~44°)

def objp(b, c):
    o = [[sx, sy*b, sz*c] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    o.append([0, 0, 0]); return np.array(o, np.float32)

def ang(A, B):
    R = A.T @ B
    return float(np.degrees(np.arccos(np.clip((np.trace(R)-1)/2, -1, 1))))

spreads, reproj = [], []
for jf in glob.glob("dataset_v1/sequences/*.json"):
    d = json.load(open(jf)); fx = d.get("fx_px"); mdl = d.get("model", "quad")
    if not fx: continue
    K = np.array([[fx, 0, cx], [0, fx, cy], [0, 0, 1]], np.float32)
    b, c = ASP.get(mdl, (0.78, 0.4)); ob = objp(b, c)
    cw = []
    for fr in d["frames"]:
        if not (fr.get("keypoints") and fr.get("pose_valid")): continue
        kp = np.array([[k[0], k[1]] for k in fr["keypoints"]], np.float32)
        vis = np.array([k[2] for k in fr["keypoints"]]) >= 1
        if vis.sum() < 6: continue
        ok, rv, tv = cv2.solvePnP(ob[vis], kp[vis], K, None, flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok: continue
        rp, _ = cv2.projectPoints(ob[vis], rv, tv, K, None)
        reproj.append(np.linalg.norm(rp.reshape(-1, 2) - kp[vis], axis=1).mean())
        Rcam, _ = cv2.Rodrigues(rv)
        Rw = Rsc.from_euler(CONV, fr["pose_euler"], degrees=True).as_matrix()
        cw.append(Rcam @ Rw.T)
    if len(cw) >= 2:
        spreads += [ang(cw[0], x) for x in cw[1:]]
spreads = np.array(spreads); reproj = np.array(reproj)
print(f"PnP 6-DoF 복원 검증 (GT keypoint, {len(reproj)}프레임):")
print(f"  위치(재투영): 평균 {reproj.mean():.2f}px 중앙 {np.median(reproj):.2f}px")
print(f"  회전:         평균 {spreads.mean():.2f}° 중앙 {np.median(spreads):.2f}°")
