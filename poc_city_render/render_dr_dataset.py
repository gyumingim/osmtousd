"""도메인 랜덤화 데이터셋 양산 — 지상시점 안티드론.
프레임마다 드론 거리(멀티스케일)·위치·자세 + 하늘회전 + 태양각 + 카메라 랜덤.
출력: dataset/images + dataset/labels(YOLO) + contact_sheet.png (한눈에 보기).
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1280, "height": 720})

import os, math, random
import numpy as np
import carb
from PIL import Image, ImageDraw
from pxr import UsdGeom, UsdLux, Usd, Gf
import omni.usd
import omni.replicator.core as rep

USD = "/home/karma/OSMtoUSD/assets/shibuya_large/shibuya_large.usd"
EXPLORA = "/home/karma/OSMtoUSD/assets/explora_src/explora.usd"
HDRI = "/home/karma/OSMtoUSD/assets/hdri/sky.hdr"
OUT = "/home/karma/OSMtoUSD/poc_city_render"
DS = os.path.join(OUT, "dataset")
os.makedirs(os.path.join(DS, "images"), exist_ok=True)
os.makedirs(os.path.join(DS, "labels"), exist_ok=True)
_logf = open(os.path.join(OUT, "run_dr.log"), "w")
def log(m): print(m, flush=True); _logf.write(str(m)+"\n"); _logf.flush()

W, H, N = 1280, 720, 20
random.seed(7)
s = carb.settings.get_settings()
s.set("/rtx/rendermode", "RaytracedLighting")   # 실시간(빠름, 20장)

omni.usd.get_context().open_stage(USD)
for _ in range(15): app.update()
stage = omni.usd.get_context().get_stage()
up = UsdGeom.GetStageUpAxis(stage)

sun = UsdLux.DistantLight.Define(stage, "/PoC_Sun"); sun.CreateIntensityAttr(3500.0); sun.CreateAngleAttr(0.53)
sun_rot = UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp()
dome = UsdLux.DomeLight.Define(stage, "/PoC_Sky"); dome.CreateIntensityAttr(1000.0); dome.CreateTextureFileAttr(HDRI)
dome_rot = UsdGeom.Xformable(dome.GetPrim()).AddRotateYOp()

cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
tp = stage.GetDefaultPrim() or next(iter(stage.GetPseudoRoot().GetChildren()))
rng = cache.ComputeWorldBound(tp).ComputeAlignedRange()
mn, mx = rng.GetMin(), rng.GetMax()
ui = 1 if up == 'Y' else 2
g1, g2 = ([0, 2] if up == 'Y' else [0, 1])
def W3(a, b, u):
    p = [0.0, 0.0, 0.0]; p[g1] = a; p[g2] = b; p[ui] = u; return p
c1 = (mn[g1]+mx[g1])/2; c2 = (mn[g2]+mx[g2])/2; top = mx[ui]; ground = mn[ui]
gd = ((mx[g1]-mn[g1])**2 + (mx[g2]-mn[g2])**2) ** 0.5

# eXplora 참조 + 중심정렬 + 스케일(고정)
drone = UsdGeom.Xform.Define(stage, "/Drone")
dpos = UsdGeom.Xformable(drone).AddTranslateOp()
rs = UsdGeom.Xform.Define(stage, "/Drone/rs"); rsx = UsdGeom.Xformable(rs)
sop = rsx.AddScaleOp(); rop = rsx.AddRotateXYZOp()
centered = UsdGeom.Xform.Define(stage, "/Drone/rs/centered")
cop = UsdGeom.Xformable(centered).AddTranslateOp()
centered.GetPrim().GetReferences().AddReference(EXPLORA)
for _ in range(25): app.update()
mb = cache.ComputeWorldBound(stage.GetPrimAtPath("/Drone/rs/centered")).ComputeAlignedRange()
mmn, mmx = mb.GetMin(), mb.GetMax()
mc = [(mmn[i]+mmx[i])/2 for i in range(3)]
mext = max(mmx[i]-mmn[i] for i in range(3))
cop.Set(Gf.Vec3d(-mc[0], -mc[1], -mc[2]))
base = gd * 0.03
sop.Set(Gf.Vec3f(base/mext, base/mext, base/mext))
from isaacsim.core.utils.semantics import add_update_semantics
add_update_semantics(stage.GetPrimAtPath("/Drone"), "drone")
log(f"eXplora 배치: mext={mext:.0f} base={base:.1f}")

def parse(bb, seg):
    recs = bb["data"]; id2 = bb["info"]["idToLabels"]
    def lab(sid):
        v = id2.get(sid, id2.get(str(sid), None))
        return v.get("class", str(v)) if isinstance(v, dict) else str(v)
    box = None
    for r in recs:
        if "drone" in lab(int(r["semanticId"])).lower():
            box = (int(r["x_min"]), int(r["y_min"]), int(r["x_max"]), int(r["y_max"])); break
    sd = np.asarray(seg["data"]); s2 = seg["info"]["idToLabels"]
    dids = [int(k) for k, v in s2.items() if "drone" in str(v).lower()]
    npx = int(np.isin(sd, dids).sum())
    return box, npx

saved = 0; att = 0; thumbs = []
while saved < N and att < N*2:
    att += 1
    # 지상 카메라: 도시 둘레 임의 방위, 저고도
    ang = random.uniform(0, 2*math.pi); R = gd*0.55
    Cg1 = c1 + R*math.cos(ang); Cg2 = c2 + R*math.sin(ang); Ch = ground + top*random.uniform(0.10, 0.35)
    hx, hz = c1 - Cg1, c2 - Cg2; hn = math.hypot(hx, hz); hx, hz = hx/hn, hz/hn
    el = math.radians(random.uniform(35, 72))         # 올려다보는 각
    dd = gd * random.uniform(0.30, 1.5)               # 거리(멀티스케일)
    Dp = [0.0, 0.0, 0.0]
    Dp[g1] = Cg1 + hx*math.cos(el)*dd; Dp[g2] = Cg2 + hz*math.cos(el)*dd; Dp[ui] = Ch + math.sin(el)*dd
    dpos.Set(Gf.Vec3d(*Dp))
    rop.Set(Gf.Vec3f(random.uniform(-40,40), random.uniform(0,360), random.uniform(-40,40)))
    dome_rot.Set(random.uniform(0,360))
    sun_rot.Set(Gf.Vec3f(random.uniform(-70,-25), 0, random.uniform(0,360)))
    # 카메라: 드론을 약간 빗나가게(중앙 고정 방지)
    look = list(Dp); look[g1] += random.uniform(-1,1)*dd*0.08; look[ui] += random.uniform(-1,1)*dd*0.08
    cam = rep.create.camera(position=W3(Cg1, Cg2, Ch), look_at=tuple(look), focal_length=random.uniform(28, 55))
    rp = rep.create.render_product(cam, (W, H))
    rgb_a = rep.AnnotatorRegistry.get_annotator("rgb")
    box_a = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
    seg_a = rep.AnnotatorRegistry.get_annotator("semantic_segmentation", init_params={"colorize": False})
    for a in (rgb_a, box_a, seg_a): a.attach([rp])
    for _ in range(8): app.update()
    rep.orchestrator.step(rt_subframes=16); app.update()
    box, npx = parse(box_a.get_data(), seg_a.get_data())
    rgb = rgb_a.get_data()
    for a in (rgb_a, box_a, seg_a): a.detach()
    if box is None or npx < 6:
        log(f"att{att}: 드론 안보임(occluded/off) → skip"); continue
    img = Image.fromarray(rgb[:, :, :3]).convert("RGB")
    fid = f"frame_{saved:04d}"
    img.save(os.path.join(DS, "images", fid+".png"))
    cx = (box[0]+box[2])/2/W; cy = (box[1]+box[3])/2/H; bw = (box[2]-box[0])/W; bh = (box[3]-box[1])/H
    open(os.path.join(DS, "labels", fid+".txt"), "w").write(f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")
    ov = img.copy(); d = ImageDraw.Draw(ov); d.rectangle(box, outline=(255,0,0), width=3)
    thumbs.append(ov.resize((320, 180)))
    log(f"att{att}->{fid}: box={box} px={npx} dist={dd:.0f}")
    saved += 1

# 컨택트시트
if thumbs:
    cols = 5; rows = math.ceil(len(thumbs)/cols)
    sheet = Image.new("RGB", (cols*320, rows*180), (30,30,30))
    for i, t in enumerate(thumbs):
        sheet.paste(t, ((i % cols)*320, (i//cols)*180))
    sheet.save(os.path.join(OUT, "dr_contact_sheet.png"))
    log(f"컨택트시트 저장: dr_contact_sheet.png ({len(thumbs)}장)")
log(f"=== 완료: {saved}장 저장 (시도 {att}) ===")
app.close()
