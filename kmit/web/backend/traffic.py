"""
교통량 시뮬레이션 + 경로 최적화 (제안서 2.4.2 미완 과제)

실제 VDS 피드가 없으므로 노드별 15분 교통량을 시간대 패턴+Z-score 이상치로
시뮬레이션. 실제 VDS 연동 시 simulate_volume()만 교체하면 됨.

- 교차로 혼잡도 히트맵: 노드별 혼잡도(0~1) + Z-score
- 교통량 기반 경로 최적화: KNN 그래프 + Dijkstra(거리×혼잡 가중)
- VDS 15분 실시간: 시뮬 스냅샷
"""
import os
import json
import math
import random
import heapq

_VWORLD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "vworld_data")

# 시간대별 상대 교통량 계수 (0~23시) — 출퇴근 피크
_HOURLY = [0.2, 0.15, 0.1, 0.1, 0.15, 0.3, 0.55, 0.85, 1.0, 0.8, 0.65, 0.7,
           0.75, 0.7, 0.65, 0.7, 0.8, 0.95, 1.0, 0.85, 0.6, 0.45, 0.35, 0.25]


def _all_node_congestion(hour=None, seed=42):
    """모든 노드(101 일반노드 포함)에 공유 스케일 혼잡도 부여 → (전체list, {id:rec}).
    노드혼잡·도로혼잡이 같은 출처를 쓰도록 단일 소스. 실 VDS 연동 시 이것만 교체."""
    import datetime
    if hour is None:
        hour = datetime.datetime.now().hour
    p = os.path.join(_VWORLD, "lt_p_moctnode.geojson")
    if not os.path.exists(p):
        return [], {}
    feats = json.load(open(p, encoding="utf-8")).get("features", [])
    nodes = []
    for f in feats:
        pr = f.get("properties", {})
        c = f["geometry"]["coordinates"]
        nodes.append({"id": str(pr.get("node_id")), "name": pr.get("node_name"),
                      "type": str(pr.get("node_type")), "lon": c[0], "lat": c[1]})
    if not nodes:
        return [], {}
    rng = random.Random(seed + hour)
    base = _HOURLY[hour % 24]
    outliers = set(rng.sample(range(len(nodes)), max(1, len(nodes) // 12)))
    vols = []
    for i in range(len(nodes)):
        v = base * rng.uniform(120, 380)
        if i in outliers:
            v *= rng.uniform(1.8, 2.6)            # 이상치 노드
        vols.append(v)
    mu = sum(vols) / len(vols)
    sd = (sum((a - mu) ** 2 for a in vols) / len(vols)) ** 0.5 or 1.0
    vmax = max(vols) or 1.0                       # 공유 정규화 스케일
    for n, v in zip(nodes, vols):
        n["volume_15min"] = round(v, 1)
        n["congestion"] = round(v / vmax, 3)      # 0~1 (노드·링크 공통 스케일)
        n["zscore"] = round((v - mu) / sd, 2)
        n["outlier"] = (v - mu) / sd >= 1.5
    return nodes, {n["id"]: n for n in nodes}


def simulate_volume(hour=None, seed=42):
    """교차로/특수노드(≠101) 혼잡도 — 노드혼잡 히트맵용."""
    if hour is None:
        import datetime
        hour = datetime.datetime.now().hour
    nodes, _ = _all_node_congestion(hour, seed)
    js = [n for n in nodes if n["type"] != "101"]
    arr = [n["volume_15min"] for n in nodes] or [0]
    mu = sum(arr) / len(arr)
    return {"hour": hour, "count": len(js), "mean": round(mu, 1), "nodes": js}


def _links():
    """도로링크 → [{name, lanes, f, t, parts:[[[lat,lon],...]]}]."""
    p = os.path.join(_VWORLD, "lt_l_moctlink.geojson")
    if not os.path.exists(p):
        return []
    feats = json.load(open(p, encoding="utf-8")).get("features", [])
    out = []
    for f in feats:
        g = f["geometry"]
        pr = f.get("properties", {})
        coords = g["coordinates"]
        if g["type"] == "LineString":
            coords = [coords]
        parts = [[[c[1], c[0]] for c in part] for part in coords if part]
        if not parts:
            continue
        try:
            lanes = float(pr.get("lanes") or 1)
        except (TypeError, ValueError):
            lanes = 1.0
        out.append({"name": pr.get("road_name") or "", "lanes": lanes,
                    "f": str(pr.get("f_node")), "t": str(pr.get("t_node")),
                    "parts": parts})
    return out


def simulate_link_volume(hour=None, seed=42):
    """도로링크 혼잡도 = 양끝 노드 혼잡의 평균 → 노드혼잡과 일관.
    한 교차로가 혼잡하면 거기 물린 도로도 혼잡하게 색이 맞는다."""
    if hour is None:
        import datetime
        hour = datetime.datetime.now().hour
    _, by_id = _all_node_congestion(hour, seed)
    links = _links()
    if not links or not by_id:
        return {"hour": hour, "count": 0, "links": []}
    res = []
    for lk in links:
        ends = [by_id[i] for i in (lk["f"], lk["t"]) if i in by_id]
        if ends:
            cong = sum(e["congestion"] for e in ends) / len(ends)
            z = max(e["zscore"] for e in ends)
            vol = round(sum(e["volume_15min"] for e in ends) / len(ends), 1)
        else:
            cong, z, vol = 0.1, 0.0, 0.0          # 노드 미상 링크
        res.append({"name": lk["name"], "parts": lk["parts"],
                    "volume_15min": vol, "congestion": round(cong, 3),
                    "zscore": round(z, 2), "outlier": z >= 1.5})
    return {"hour": hour, "count": len(res), "links": res}


def _haversine(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat = p2 - p1
    dlon = math.radians(b["lon"] - a["lon"])
    h = (math.sin(dlat / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def optimize_route(start_id, end_id, hour=None, avoid_outliers=True, k=6):
    """KNN 그래프 + Dijkstra. 거리 × (1 + 혼잡가중)으로 최적 경로."""
    sim = simulate_volume(hour)
    nodes = {n["id"]: n for n in sim["nodes"]}
    if start_id not in nodes or end_id not in nodes:
        return {"error": "노드 ID 없음", "valid_ids_sample":
                list(nodes)[:5]}
    ids = list(nodes)
    # KNN 인접 그래프
    adj = {i: [] for i in ids}
    for i in ids:
        d = sorted(((_haversine(nodes[i], nodes[j]), j)
                    for j in ids if j != i), key=lambda t: t[0])[:k]
        for dist, j in d:
            cong = nodes[j]["congestion"]
            pen = 3.0 if (avoid_outliers and nodes[j]["outlier"]) else 1.0
            w = dist * (1 + cong) * pen
            adj[i].append((j, w, dist))
    # Dijkstra
    INF = float("inf")
    best = {i: INF for i in ids}
    best[start_id] = 0
    prev = {}
    pq = [(0, start_id)]
    while pq:
        cost, u = heapq.heappop(pq)
        if u == end_id:
            break
        if cost > best[u]:
            continue
        for v, w, _ in adj[u]:
            nc = cost + w
            if nc < best[v]:
                best[v] = nc
                prev[v] = u
                heapq.heappush(pq, (nc, v))
    if best[end_id] == INF:
        return {"error": "경로 없음"}
    # 경로 복원
    path, cur = [], end_id
    while cur != start_id:
        path.append(cur)
        cur = prev[cur]
    path.append(start_id)
    path.reverse()
    total_m = sum(_haversine(nodes[path[i]], nodes[path[i + 1]])
                  for i in range(len(path) - 1))
    return {"hour": sim["hour"], "avoid_outliers": avoid_outliers,
            "path": [{"id": p, "lat": nodes[p]["lat"], "lon": nodes[p]["lon"],
                      "congestion": nodes[p]["congestion"]} for p in path],
            "hops": len(path), "distance_m": round(total_m, 1)}
