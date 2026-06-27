"""2번째 실벤치 다운(일반화 검증). 다른 출처 UAV."""
import os, glob
key = None
for ln in open("/home/karma/OSMtoUSD/.env"):
    if ln.startswith("ROBOFLOW_API_KEY="): key = ln.strip().split("=", 1)[1]
from roboflow import Roboflow
rf = Roboflow(api_key=key)
WS, PJ = "istanbul-technical-university", "uav-detecting"
try:
    proj = rf.workspace(WS).project(PJ)
    nums = sorted([int(v.version) for v in proj.versions()])
    print("versions:", nums, flush=True)
    v = proj.version(nums[-1])
    ds = v.download("yolov11", location="/home/karma/OSMtoUSD/poc_city_render/benchmarks/uav_itu", overwrite=True)
    loc = ds.location
    print("DOWNLOAD_DONE", loc, flush=True)
    yml = open(os.path.join(loc, "data.yaml")).read()
    import re
    print("names:", [l for l in yml.splitlines() if l.startswith("names") or l.startswith("nc")])
    for sp in ["train", "valid", "test"]:
        n = len(glob.glob(os.path.join(loc, sp, "images", "*")))
        print(f"  {sp}: {n}장")
except Exception as e:
    print("FAIL:", type(e).__name__, str(e)[:200], flush=True)
