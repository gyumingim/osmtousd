"""카탈로그 DB 계층 (제안서 3-A) — sqlite3 stdlib, 의존성 0.

데이터 흐름: packages/*.zip(meta) → ingest → SQLite(datasets 테이블) → API.
PostgreSQL 전환: connect()를 psycopg로 바꾸고 동일 SQL 사용(스키마 호환).
스키마: 데이터 출처(Real/Synthetic)·시나리오 유형·생성 파라미터·프레임수·용량·센서.

Usage(독립 적재):
    python3 web/backend/ingest.py
"""
import os
import json
import glob
import zipfile
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.environ.get("CATALOG_DB", os.path.join(ROOT, "catalog.db"))
PKG_DIR = os.path.join(ROOT, "packages")

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id            TEXT PRIMARY KEY,
    source        TEXT,      -- Real / Synthetic
    scenario      TEXT,
    scenario_name TEXT,
    variant       TEXT,
    frame_count   INTEGER,
    size_bytes    INTEGER,
    environment   TEXT,      -- json (기상·시간대 등 생성 파라미터)
    sensors       TEXT,      -- json
    labels        TEXT,      -- json
    classes       TEXT,      -- json (class_distribution)
    path          TEXT
);
"""


def connect():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with connect() as c:
        c.executescript(SCHEMA)


def _source_kind(meta):
    s = (meta.get("source") or "").lower()
    return "Real" if "real" in s and "synthetic" not in s else "Synthetic"


def ingest_packages(pkg_dir=PKG_DIR):
    """packages/*.zip 의 meta/metadata.json → datasets 테이블 upsert. 반환: 적재수."""
    init()
    rows = []
    for zp in sorted(glob.glob(os.path.join(pkg_dir, "*.zip"))):
        ds_id = os.path.basename(zp)[:-4]
        try:
            with zipfile.ZipFile(zp) as z:
                m = json.loads(z.read("meta/metadata.json"))
                n_png = sum(1 for n in z.namelist()
                            if n.startswith("data/") and n.endswith(".png"))
        except Exception:
            continue
        rows.append((
            ds_id, _source_kind(m), m.get("scenario"),
            m.get("scenario_name"), m.get("variant"),
            m.get("frame_count", n_png), os.path.getsize(zp),
            json.dumps(m.get("environment", {}), ensure_ascii=False),
            json.dumps(m.get("sensors", []), ensure_ascii=False),
            json.dumps(m.get("labels", []), ensure_ascii=False),
            json.dumps(m.get("class_distribution", {}), ensure_ascii=False),
            zp,
        ))
    with connect() as c:
        c.execute("DELETE FROM datasets")
        c.executemany(
            "INSERT INTO datasets (id,source,scenario,scenario_name,variant,"
            "frame_count,size_bytes,environment,sensors,labels,classes,path) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def _row_meta(r):
    """DB row → API meta dict (기존 zip-scan과 동일 형태)."""
    return {
        "id": r["id"], "source": r["source"], "scenario": r["scenario"],
        "scenario_name": r["scenario_name"], "variant": r["variant"],
        "frame_count": r["frame_count"], "size_bytes": r["size_bytes"],
        "environment": json.loads(r["environment"] or "{}"),
        "sensors": json.loads(r["sensors"] or "[]"),
        "labels": json.loads(r["labels"] or "[]"),
        "class_distribution": json.loads(r["classes"] or "{}"),
    }


def load_catalog():
    """{id: {meta, path}} — main.py CATALOG 형태로 반환."""
    if not os.path.exists(DB_PATH):
        return {}
    out = {}
    with connect() as c:
        for r in c.execute("SELECT * FROM datasets ORDER BY id"):
            out[r["id"]] = {"meta": _row_meta(r), "path": r["path"]}
    return out
