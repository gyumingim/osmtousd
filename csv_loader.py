import csv
from pyproj import Transformer


def load_crosswalks_csv(csv_path, target_crs, cx, cy, radius=None):
    """
    횡단보도 CSV → 로컬 좌표 + 치수 리스트.
    Returns: list of dict {x, y, width, length, has_signal, kind}
      width  : 횡단보도폭(m) — 도로 방향 총 폭
      length : 횡단보도연장(m) — 도로 수직 방향 횡단 길이
      has_signal: 보행자신호등 유무 (bool)
      kind   : '01'=일반, '04'=고원식, 기타
    """
    t = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    crosswalks = []
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                lat = float(row["위도"])
                lon = float(row["경도"])
            except (ValueError, KeyError):
                continue
            try:
                width = float(row.get("횡단보도폭") or 4.0)
                length = float(row.get("횡단보도연장") or 8.0)
            except ValueError:
                width, length = 4.0, 8.0
            wx, wy = t.transform(lon, lat)
            lx, ly = wx - cx, wy - cy
            if radius is not None and (lx * lx + ly * ly) > radius * radius:
                continue
            crosswalks.append({
                "x": lx, "y": ly,
                "width": max(width, 1.0),
                "length": max(length, 2.0),
                "has_signal": row.get("보행자신호등유무", "") == "Y",
                "kind": row.get("횡단보도종류", "01"),
            })
    return crosswalks


def load_traffic_signals_csv(csv_path, target_crs, cx, cy, radius=None):
    """
    CSV 신호등 데이터 -> 로컬 좌표 리스트.
    radius: 중심으로부터 최대 거리(m), None이면 전체 로드
    Returns: list of (x, y, signal_type) where type: 1=차량, 2=보행자, 6=황색점멸
    """
    t = Transformer.from_crs("EPSG:4326", target_crs, always_xy=True)
    signals = []
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                lat = float(row["위도"])
                lon = float(row["경도"])
                sig_type = int(row["신호등구분"])
            except (ValueError, KeyError):
                continue
            wx, wy = t.transform(lon, lat)
            lx, ly = wx - cx, wy - cy
            if radius is not None and (lx * lx + ly * ly) > radius * radius:
                continue
            signals.append((lx, ly, sig_type))
    return signals
