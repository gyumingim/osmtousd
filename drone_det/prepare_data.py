"""prepare_data.py — HF pathikg/drone-detection-dataset → YOLO 포맷 소량 추출.

COCO bbox [x,y,w,h](절대) → YOLO [xc,yc,w,h](정규화):
  xc=(x+w/2)/W, yc=(y+h/2)/H, wn=w/W, hn=h/H, class=0(drone)
스트리밍으로 train N개·test M개만 받아 data/{images,labels}/{train,val}에 저장.
"""
import os
from datasets import load_dataset

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
N_TRAIN = int(os.environ.get("N_TRAIN", "2000"))
N_VAL = int(os.environ.get("N_VAL", "400"))


def coco_to_yolo(bbox, W, H):
    """COCO [x,y,w,h] 절대 → YOLO [xc,yc,wn,hn] 정규화."""
    x, y, w, h = bbox
    return [(x + w / 2) / W, (y + h / 2) / H, w / W, h / H]


def dump(split_src, split_dst, n):
    img_dir = os.path.join(DATA, "images", split_dst)
    lbl_dir = os.path.join(DATA, "labels", split_dst)
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(lbl_dir, exist_ok=True)
    ds = load_dataset("pathikg/drone-detection-dataset", split=split_src,
                      streaming=True)
    cnt = boxes = empty = 0
    for ex in ds.take(n):
        W, H = ex["width"], ex["height"]
        name = f"{split_dst}_{cnt:05d}"
        try:
            ex["image"].convert("RGB").save(
                os.path.join(img_dir, name + ".jpg"))
        except Exception as e:
            print(f"  이미지 저장 실패 {name}: {e}", flush=True)
            continue
        lines = []
        for bbox, cat in zip(ex["objects"]["bbox"], ex["objects"]["category"]):
            xc, yc, wn, hn = coco_to_yolo(bbox, W, H)
            if wn <= 0 or hn <= 0:            # 비정상 박스 스킵
                continue
            lines.append(f"0 {xc:.6f} {yc:.6f} {wn:.6f} {hn:.6f}")
        # 라벨 파일(빈 파일=배경 이미지, YOLO가 false-positive 억제에 활용)
        with open(os.path.join(lbl_dir, name + ".txt"), "w") as f:
            f.write("\n".join(lines))
        boxes += len(lines)
        empty += (len(lines) == 0)
        cnt += 1
        if cnt % 500 == 0:
            print(f"  {split_dst}: {cnt}/{n}", flush=True)
    print(f"{split_dst} 완료: 이미지 {cnt} · 박스 {boxes} · 배경(드론0) {empty}",
          flush=True)
    return cnt


def main():
    nt = dump("train", "train", N_TRAIN)
    nv = dump("test", "val", N_VAL)
    yaml_path = os.path.join(DATA, "data.yaml")
    with open(yaml_path, "w") as f:
        f.write(f"path: {DATA}\ntrain: images/train\nval: images/val\n"
                f"nc: 1\nnames: [drone]\n")
    print(f"data.yaml 작성: train {nt} · val {nv} → {yaml_path}", flush=True)


if __name__ == "__main__":
    main()
    # HF 스트리밍 이터레이터 finalize 시 PyGILState 크래시 방지 → 즉시 클린 종료
    os._exit(0)
