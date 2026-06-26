"""dataset_v1(시퀀스 JSON + 이미지) → YOLO11-pose 학습셋(dataset_pose/).
라벨: `cls cx cy w h  kx1 ky1 v1 ... kx9 ky9 v9` (전부 0~1 정규화, kpt_shape=[9,3]).
- cls: 기종 (quad=0, heli=1)  / 네거티브·드론없음 = 빈 라벨(배경)
- keypoint: 3D박스 8모서리+중심(우리 generator 순서). pose_valid(=박스 min변≥20px) 일 때만 supervision,
  아니면 9점 전부 v=0(박스만 학습). 화면 밖 모서리도 v=0.
- 분할: 시퀀스 단위 80/20 (같은 track이 train/val 양쪽에 가지 않게 = 시간누수 방지).
solvePnP용 3D 큐보이드(objectPoints, 같은 모서리 순서)는 dataset_pose/cuboid_objpoints.json + README에.
"""
import os, json, glob, shutil, hashlib

SRC = "/home/karma/OSMtoUSD/poc_city_render/dataset_v1"
DST = "/home/karma/OSMtoUSD/poc_city_render/dataset_pose"
W, H = 1280, 720
CLS = {"quad": 0, "heli": 1}
VAL_FRAC = 0.20

for sub in ("images/train", "images/val", "labels/train", "labels/val"):
    d = os.path.join(DST, sub)
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        os.remove(os.path.join(d, f))

seqs = sorted(glob.glob(os.path.join(SRC, "sequences", "*.json")))
# 시퀀스 단위 결정적 분할: 파일명 해시로 val 선택
def is_val(name):
    h = int(hashlib.md5(name.encode()).hexdigest(), 16)
    return (h % 100) < int(VAL_FRAC * 100)

n_frame = {"train": 0, "val": 0}
n_pos = {"train": 0, "val": 0}
n_poseval = {"train": 0, "val": 0}
cls_count = {}

def kp_line(fr):
    """positive 프레임 → YOLO-pose 라벨 한 줄. 드론 없으면 None."""
    box = fr.get("bbox_xywh_norm")
    if not box:
        return None
    cls = CLS.get(fr.get("model"), 0)
    cls_count[fr.get("model")] = cls_count.get(fr.get("model"), 0) + 1
    cx, cy, bw, bh = box
    parts = [str(cls), f"{cx:.6f}", f"{cy:.6f}", f"{bw:.6f}", f"{bh:.6f}"]
    kps = fr.get("keypoints") or []
    pv = bool(fr.get("pose_valid"))
    for i in range(9):
        if pv and i < len(kps):
            px, py, vf = kps[i]
            nx, ny = px / W, py / H
            if vf == 2 and 0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0:
                parts += [f"{nx:.6f}", f"{ny:.6f}", "2"]
                continue
        parts += ["0.000000", "0.000000", "0"]   # 화면밖/작은드론 → 무시(v=0)
    return " ".join(parts), pv

for sj in seqs:
    s = json.load(open(sj))
    split = "val" if is_val(os.path.basename(sj)) else "train"
    for fr in s["frames"]:
        fid = fr["file"]                       # e.g. r0s1f3.png
        src_img = os.path.join(SRC, "images", fid)
        if not os.path.exists(src_img):
            continue
        shutil.copy(src_img, os.path.join(DST, "images", split, fid))
        lab_path = os.path.join(DST, "labels", split, fid.replace(".png", ".txt"))
        res = kp_line(fr)
        with open(lab_path, "w") as lf:
            if res:
                line, pv = res
                lf.write(line + "\n")
                n_pos[split] += 1
                if pv:
                    n_poseval[split] += 1
            # res None → 빈 파일 = 배경(네거티브)
        n_frame[split] += 1

# data.yaml (kpt_shape, flip_idx, 클래스)
yaml = f"""# YOLO11-pose 드론 자세 데이터셋 (auto-generated from dataset_v1)
path: {DST}
train: images/train
val: images/val

kpt_shape: [9, 3]   # 3D박스 8모서리 + 중심, (x,y,visible)
# flip_idx=identity: 3D 자세는 좌우반전 시 모서리 대응이 일정치 않음 → 학습 때 fliplr=0.0 권장!
flip_idx: [0, 1, 2, 3, 4, 5, 6, 7, 8]

names:
  0: quad
  1: heli
"""
open(os.path.join(DST, "data.yaml"), "w").write(yaml)

# solvePnP용 3D 큐보이드(단위큐브 ±0.5, generator와 동일한 sx,sy,sz 순서) + 중심
obj = []
for sx in (-0.5, 0.5):
    for sy in (-0.5, 0.5):
        for sz in (-0.5, 0.5):
            obj.append([sx, sy, sz])
obj.append([0.0, 0.0, 0.0])
json.dump({"order": "for sx in(-,+): for sy in(-,+): for sz in(-,+) + center",
           "unit_cuboid_xyz": obj,
           "note": "PnP objectPoints. 회전은 스케일무관, 미터거리는 기종별 실측치수로 스케일(기종→크기). "
                   "cameraMatrix는 시퀀스별로 다름(FOV 변주): 시퀀스 JSON의 fx_px 사용 → fx=fy=fx_px, cx=W/2=640, cy=H/2=360."},
          open(os.path.join(DST, "cuboid_objpoints.json"), "w"), indent=2)

readme = f"""# dataset_pose — YOLO11-pose 학습셋

## 학습 (AI-1)
```
yolo pose train model=yolo11n-pose.pt data={DST}/data.yaml imgsz=1280 fliplr=0.0
```
- ⚠️ **fliplr=0.0 필수** (3D 자세 좌우반전 시 keypoint 대응 깨짐, flip_idx는 identity).
- imgsz=1280 권장(원거리 tiny 때문).

## 라벨 포맷
`cls cx cy w h  kx1 ky1 v1 ... kx9 ky9 v9` (전부 0~1 정규화)
- cls: quad=0, heli=1
- keypoint 9 = 3D박스 8모서리 + 중심. v: 2=보임, 0=무시(화면밖/작은드론)
- **pose_valid**(박스 최소변≥20px)일 때만 keypoint supervision. 작은 드론은 박스만(v=0).
- 빈 라벨 = 배경(네거티브).

## 추론 시 6DoF
모델이 9 keypoint 예측 → `cv2.solvePnP(objectPoints, imagePoints, cameraMatrix)`.
- objectPoints: cuboid_objpoints.json (같은 모서리 순서). 회전은 그대로, 미터거리는 기종 실측치수로 스케일.
- cameraMatrix: **시퀀스별 fx_px** 사용(FOV 변주됨). 이미지 r{{RUN}}s{{sq}}f{{fr}} → ../dataset_v1/sequences/r{{RUN}}s{{sq}}.json 의 fx_px. fx=fy=fx_px, cx=640, cy=360.

## 통계
train {n_frame['train']}프레임(pos {n_pos['train']}, pose_valid {n_poseval['train']}) /
val {n_frame['val']}프레임(pos {n_pos['val']}, pose_valid {n_poseval['val']})
기종: {cls_count}
"""
open(os.path.join(DST, "README.md"), "w").write(readme)

print(f"train: {n_frame['train']}f (pos {n_pos['train']}, pose_valid {n_poseval['train']})")
print(f"val  : {n_frame['val']}f (pos {n_pos['val']}, pose_valid {n_poseval['val']})")
print(f"기종 분포: {cls_count}")
print(f"→ {DST} (data.yaml, cuboid_objpoints.json, README.md)")
