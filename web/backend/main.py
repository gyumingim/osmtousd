"""
데이터 포털 백엔드 (TODO 3-A) — FastAPI 카탈로그 API

packages/*.zip 의 meta/metadata.json 을 읽어 합성 데이터셋 카탈로그로 노출.
(별도 DB 없이 패키지 메타를 직접 읽음 — 최소 복잡도)

실행:
    python3 -m uvicorn web.backend.main:app --reload --port 8000
"""
import os
import json
import zipfile
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from . import db

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG_DIR = os.path.join(ROOT, "packages")
FRONTEND = os.path.join(ROOT, "web", "frontend")

app = FastAPI(title="구미 디지털트윈 합성데이터 포털", version="1.0")


def _scan_packages():
    """packages/*.zip → DB 적재(제안서 3-A) → {id: {meta, path}} 카탈로그."""
    db.ingest_packages(PKG_DIR)            # zip → SQLite(datasets)
    return db.load_catalog()               # DB → 카탈로그


# 시작 시 DB 적재 후 로드 (재생성 시 /api/refresh로 재적재)
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


# MOCT node_type → 라벨 (101=일반, 그 외=교차로/특수)
_NODE_TYPES = {
    "101": "일반노드", "102": "교차로", "103": "입체교차로",
    "104": "회전/IC", "106": "연결로", "107": "특수노드",
}
_VWORLD = os.path.join(ROOT, "vworld_data")


def _load_geojson(name):
    p = os.path.join(_VWORLD, name)
    if not os.path.exists(p):
        return []
    return json.load(open(p, encoding="utf-8")).get("features", [])


@app.get("/api/intersections")
def intersections(junction_only: bool = True):
    """구미 도로 노드/교차로 (WGS84). junction_only=True면 교차로·특수노드만."""
    out = []
    for f in _load_geojson("lt_p_moctnode.geojson"):
        p = f.get("properties", {})
        nt = str(p.get("node_type"))
        if junction_only and nt == "101":
            continue
        c = f["geometry"]["coordinates"]
        out.append({"id": p.get("node_id"), "name": p.get("node_name"),
                    "type": nt, "type_name": _NODE_TYPES.get(nt, nt),
                    "lon": c[0], "lat": c[1]})
    return {"count": len(out), "intersections": out}


@app.get("/api/intersections/heatmap")
def heatmap(hour: int = None):
    """교차로 혼잡도 히트맵 (시간대별 교통량 시뮬 + Z-score 이상치)."""
    from . import traffic
    return traffic.simulate_volume(hour)


@app.get("/api/links/congestion")
def links_congestion(hour: int = None):
    """도로링크별 혼잡도 (도로선 그라데이션용) — 차로수·시간대 + Z-score."""
    from . import traffic
    return traffic.simulate_link_volume(hour)


@app.get("/api/vds/live")
def vds_live(hour: int = None):
    """VDS 검지기 15분 단위 실시간(시뮬) — 이상상황 알림 포함."""
    from . import traffic
    sim = traffic.simulate_volume(hour)
    alerts = [{"id": n["id"], "name": n["name"],
               "volume_15min": n["volume_15min"], "zscore": n["zscore"]}
              for n in sim["nodes"] if n["outlier"]]
    return {"hour": sim["hour"], "interval_min": 15,
            "total_nodes": sim["count"], "alerts": alerts,
            "alert_count": len(alerts)}


@app.post("/api/routes/optimize-with-traffic")
@app.get("/api/routes/optimize-with-traffic")
def optimize_route(start_id: str, end_id: str, hour: int = None,
                   avoid_outliers: bool = True):
    """교통량 기반 경로 최적화 (혼잡·이상치 교차로 회피 옵션)."""
    from . import traffic
    return traffic.optimize_route(start_id, end_id, hour, avoid_outliers)


@app.get("/api/traffic_signals")
def traffic_signals():
    """신호등 위치 (WGS84)."""
    out = []
    for f in _load_geojson("lt_p_c1trafficlight.geojson"):
        c = f["geometry"]["coordinates"]
        out.append({"id": f["properties"].get("id"),
                    "lon": c[0], "lat": c[1]})
    return {"count": len(out), "signals": out}


@app.post("/api/refresh")
def refresh():
    global CATALOG
    CATALOG = _scan_packages()
    return {"count": len(CATALOG)}


def _serve(name, fallback):
    p = os.path.join(FRONTEND, name)
    if os.path.exists(p):
        return HTMLResponse(open(p, encoding="utf-8").read())
    return HTMLResponse(fallback)


@app.get("/", response_class=HTMLResponse)
def index():
    return _serve("index.html",
                  "<h1>포털 백엔드 작동 중</h1><p>/api/datasets</p>")


@app.get("/map", response_class=HTMLResponse)
def map_page():
    return _serve("map.html", "<h1>map.html 없음</h1>")


@app.get("/vds", response_class=HTMLResponse)
def vds_page():
    return _serve("vds.html", "<h1>vds.html 없음</h1>")


if os.path.isdir(FRONTEND):
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
