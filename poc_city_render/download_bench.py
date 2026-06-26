"""Roboflow Universe 라벨 실드론 벤치 다운 (drone-a7lpy/drones-yolo11-a).
키는 .env에서. YOLO포맷 → benchmarks/drones_yolo11_a/"""
import os
key = None
for ln in open("/home/karma/OSMtoUSD/.env"):
    if ln.startswith("ROBOFLOW_API_KEY="):
        key = ln.strip().split("=", 1)[1]
from roboflow import Roboflow
rf = Roboflow(api_key=key)
proj = rf.workspace("drone-a7lpy").project("drones-yolo11-a")
vers = proj.versions()
nums = sorted([int(v.version) for v in vers]) if vers else []
print("versions:", nums, flush=True)
vnum = nums[-1]
print("downloading version", vnum, flush=True)
v = proj.version(vnum)
ds = v.download("yolov11", location="/home/karma/OSMtoUSD/poc_city_render/benchmarks/drones_yolo11_a", overwrite=True)
print("DOWNLOAD_DONE", ds.location, flush=True)
