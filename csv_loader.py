import csv
from pyproj import Transformer


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
