"""
데이터 포털 백엔드 (TODO 3-A) — FastAPI 카탈로그 API

packages/*.zip 의 meta/metadata.json 을 읽어 합성 데이터셋 카탈로그로 노출.
(별도 DB 없이 패키지 메타를 직접 읽음 — 최소 복잡도)

실행:
    python3 -m uvicorn web.backend.main:app --reload --port 8000
"""
import os
import io
import json
import zipfile
import glob
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG_DIR = os.path.join(ROOT, "packages")
FRONTEND = os.path.join(ROOT, "web", "frontend")

app = FastAPI(title="구미 디지털트윈 합성데이터 포털", version="1.0")


def _scan_packages():
    """packages/*.zip → {id: {meta, path, bytes}}."""
    cat = {}
    for zp in sorted(glob.glob(os.path.join(PKG_DIR, "*.zip"))):
        ds_id = os.path.basename(zp)[:-4]
        try:
            with zipfile.ZipFile(zp) as z:
                meta = json.loads(z.read("meta/metadata.json"))
                n_data = sum(1 for n in z.namelist()
                             if n.startswith("data/") and n.endswith(".png"))
        except Exception:
            continue
        meta["id"] = ds_id
        meta["size_bytes"] = os.path.getsize(zp)
        meta["preview_count"] = n_data
        cat[ds_id] = {"meta": meta, "path": zp}
    return cat


# 시작 시 1회 스캔 (재생성 시 /api/refresh)
CATALOG = _scan_packages()


@app.get("/api/datasets")
def list_datasets(type: str = Query(None), scenario: str = Query(None)):
    """카탈로그 조회 (필터: type=Synthetic, scenario=scenario_01..05)."""
    items = []
    for ds in CATALOG.values():
        m = ds["meta"]
        if scenario and m.get("scenario") != scenario:
            continue
        if type and type.lower() not in m.get("source", "").lower():
            continue
        items.append({
            "id": m["id"], "scenario": m["scenario"],
            "scenario_name": m.get("scenario_name"),
            "variant": m.get("variant"), "environment": m.get("environment"),
            "frame_count": m.get("frame_count"),
            "size_bytes": m["size_bytes"],
            "classes": m.get("class_distribution", {}),
        })
    return {"count": len(items), "datasets": items}


@app.get("/api/datasets/{ds_id}")
def get_dataset(ds_id: str):
    if ds_id not in CATALOG:
        raise HTTPException(404, "데이터셋 없음")
    return CATALOG[ds_id]["meta"]


@app.get("/api/datasets/{ds_id}/download")
def download(ds_id: str):
    if ds_id not in CATALOG:
        raise HTTPException(404, "데이터셋 없음")
    return FileResponse(CATALOG[ds_id]["path"],
                        media_type="application/zip",
                        filename=f"{ds_id}.zip")


@app.get("/api/datasets/{ds_id}/preview")
def preview(ds_id: str, frame: int = 0):
    """데이터셋 첫 프레임 합성 PNG 미리보기."""
    if ds_id not in CATALOG:
        raise HTTPException(404, "데이터셋 없음")
    with zipfile.ZipFile(CATALOG[ds_id]["path"]) as z:
        name = f"data/frame_{frame:04d}.png"
        if name not in z.namelist():
            raise HTTPException(404, "프레임 없음")
        from fastapi.responses import Response
        return Response(z.read(name), media_type="image/png")


@app.get("/api/stats/scenarios")
def stats_scenarios():
    """시나리오별 통계 (데이터셋 수·프레임·용량·클래스)."""
    by = {}
    for ds in CATALOG.values():
        m = ds["meta"]
        s = m["scenario"]
        e = by.setdefault(s, {"scenario": s, "name": m.get("scenario_name"),
                              "datasets": 0, "frames": 0, "bytes": 0,
                              "classes": {}})
        e["datasets"] += 1
        e["frames"] += m.get("frame_count", 0)
        e["bytes"] += m["size_bytes"]
        for k, v in m.get("class_distribution", {}).items():
            e["classes"][k] = e["classes"].get(k, 0) + v
    return {"scenarios": list(by.values())}


@app.post("/api/refresh")
def refresh():
    global CATALOG
    CATALOG = _scan_packages()
    return {"count": len(CATALOG)}


@app.get("/", response_class=HTMLResponse)
def index():
    idx = os.path.join(FRONTEND, "index.html")
    if os.path.exists(idx):
        return HTMLResponse(open(idx, encoding="utf-8").read())
    return HTMLResponse("<h1>포털 백엔드 작동 중</h1><p>/api/datasets</p>")


if os.path.isdir(FRONTEND):
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
