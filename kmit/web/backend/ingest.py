"""카탈로그 적재 (제안서 3-A) — packages/*.zip → SQLite.

Usage:
    python3 web/backend/ingest.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from web.backend import db  # noqa: E402


def main():
    n = db.ingest_packages()
    cat = db.load_catalog()
    syn = sum(1 for v in cat.values() if v["meta"]["source"] == "Synthetic")
    real = len(cat) - syn
    print(f"✅ 적재 {n}개 → {db.DB_PATH}")
    print(f"   Synthetic {syn} · Real {real}")


if __name__ == "__main__":
    main()
