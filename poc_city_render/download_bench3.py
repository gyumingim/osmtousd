"""3번째 벤치 — drone-vs-bird (작은 원거리 드론 = 과제 본질 안티드론 regime)."""
import os, glob, cv2, numpy as np
key=None
for ln in open("/home/karma/OSMtoUSD/.env"):
    if ln.startswith("ROBOFLOW_API_KEY="): key=ln.strip().split("=",1)[1]
from roboflow import Roboflow
rf=Roboflow(api_key=key)
for WS,PJ in [("dam-tpuul","drone-vs-bird-lanzg")]:
    try:
        proj=rf.workspace(WS).project(PJ)
        nums=sorted([int(v.version) for v in proj.versions()])
        print(f"{WS}/{PJ} versions:",nums,flush=True)
        v=proj.version(nums[-1])
        ds=v.download("yolov11",location="/home/karma/OSMtoUSD/poc_city_render/benchmarks/dvb",overwrite=True)
        loc=ds.location
        print("names:",[l for l in open(loc+"/data.yaml") if l.startswith(("names","nc"))])
        # 박스크기 분포
        sizes=[]
        for lf in glob.glob(loc+"/*/labels/*.txt")[:3000]:
            ip=lf.replace("/labels/","/images/").rsplit(".",1)[0]
            ips=[ip+e for e in (".jpg",".png",".jpeg") if os.path.exists(ip+e)]
            if not ips: continue
            im=cv2.imread(ips[0]);
            if im is None: continue
            H,W=im.shape[:2]
            for l in open(lf):
                p=l.split()
                if len(p)>=5: sizes.append(max(float(p[3])*W,float(p[4])*H))
        s=np.array(sizes)
        for sp in ["train","valid","test"]:
            print(f"  {sp}: {len(glob.glob(loc+'/'+sp+'/images/*'))}장")
        if len(s): print(f"  박스 px: 중앙{np.median(s):.0f} | tiny<20 {100*(s<20).mean():.0f}% small<50 {100*(s<50).mean():.0f}%")
    except Exception as e:
        print("FAIL:",type(e).__name__,str(e)[:150],flush=True)
