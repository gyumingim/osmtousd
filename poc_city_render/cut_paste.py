"""Cut-Paste 하드네거티브: 실제 confuser(새·비행기) 사진을 하늘배경서 분할 →
우리 렌더 이미지에 합성. 라벨은 그대로(confuser=드론아님) → 오탐 억제 학습.
GPU 0. 논문: Dwibedi et al. 2017 'Cut, Paste and Learn'.
사용: ../drone_det/venv/bin/python cut_paste.py  (데모 montage 생성)"""
import glob, os, random
import numpy as np
import cv2

RAW = "confusers/raw"
CUT = "confusers/cutouts"
os.makedirs(CUT, exist_ok=True)

def segment_sky_object(path):
    """하늘배경(밝고 균일)서 물체(어둡고 다름) 분할 → RGBA 컷아웃. 실패시 None."""
    img = cv2.imread(path)
    if img is None: return None
    h, w = img.shape[:2]
    # 하늘색 추정 = 네 모서리 중앙값
    corners = np.concatenate([img[:h//8, :w//8].reshape(-1, 3), img[:h//8, -w//8:].reshape(-1, 3),
                              img[-h//8:, :w//8].reshape(-1, 3), img[-h//8:, -w//8:].reshape(-1, 3)])
    sky = np.median(corners, axis=0)
    diff = np.linalg.norm(img.astype(np.float32) - sky, axis=2)
    mask = (diff > 45).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n < 2: return None
    big = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    area = stats[big, cv2.CC_STAT_AREA]
    if not (0.002*h*w < area < 0.5*h*w): return None       # 너무 작/크면 분할실패
    om = (lbl == big).astype(np.uint8)
    x, y, ww, hh = stats[big, 0], stats[big, 1], stats[big, 2], stats[big, 3]
    crop = img[y:y+hh, x:x+ww]; ca = (om[y:y+hh, x:x+ww]*255).astype(np.uint8)
    ca = cv2.GaussianBlur(ca, (3, 3), 0)                    # 경계 부드럽게
    return np.dstack([crop, ca])                            # BGRA

# 1) 분할 → 컷아웃 저장
cutouts = []
for p in sorted(glob.glob(RAW+"/*.jpg")):
    r = segment_sky_object(p)
    if r is not None:
        out = CUT+"/"+os.path.basename(p).replace(".jpg", ".png")
        cv2.imwrite(out, r); cutouts.append(out)
        print("컷아웃 OK:", os.path.basename(out), r.shape[:2])
    else:
        print("분할 실패(스킵):", os.path.basename(p))

def paste_negatives(img_bgr, n=None):
    """이미지 하늘부분(상단)에 confuser 1~3개 합성. 작게(드론과 헷갈리게)~중간. 라벨 영향 0."""
    if not cutouts: return img_bgr
    H, W = img_bgr.shape[:2]; out = img_bgr.copy()
    n = n if n is not None else random.choice([1, 1, 2, 3])
    for _ in range(n):
        co = cv2.imread(random.choice(cutouts), cv2.IMREAD_UNCHANGED)
        if co is None or co.shape[2] != 4: continue
        scale = random.uniform(0.02, 0.14)*W / max(co.shape[1], 1)   # 작게~중간
        nw, nh = max(4, int(co.shape[1]*scale)), max(4, int(co.shape[0]*scale))
        co = cv2.resize(co, (nw, nh), interpolation=cv2.INTER_AREA)
        if random.random() < 0.5: co = cv2.flip(co, 1)
        px, py = random.randint(0, W-nw), random.randint(0, int(H*0.6))  # 상단(하늘) 위주
        rgb = co[:, :, :3].astype(np.float32); a = (co[:, :, 3:4].astype(np.float32)/255.0)
        roi = out[py:py+nh, px:px+nw].astype(np.float32)
        out[py:py+nh, px:px+nw] = (roi*(1-a)+rgb*a).astype(np.uint8)
    return out

if __name__ == "__main__":
    print(f"\n쓸 수 있는 컷아웃: {len(cutouts)}개")
    # 데모: 데이터셋 이미지 6장에 합성
    import math
    from PIL import Image
    imgs = sorted(glob.glob("dataset_pose/images/val/*.png"))[:6]
    T = 320; sh = np.full((2*T, 3*T, 3), 20, np.uint8)
    for i, ip in enumerate(imgs):
        comp = paste_negatives(cv2.imread(ip), n=2)
        comp = cv2.resize(comp, (T, T))
        sh[(i//3)*T:(i//3)*T+T, (i % 3)*T:(i % 3)*T+T] = comp
    cv2.imwrite("cutpaste_demo.png", sh)
    print("데모 저장: cutpaste_demo.png (우리 이미지에 실제 새·비행기 합성)")
