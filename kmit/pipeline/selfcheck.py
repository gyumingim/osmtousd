"""구성 일관성 자가점검 — sensor_config(캘리브용) ↔ sensor_drive(실제 리그).

캘리브레이션은 sensors/sensor_config.py 값으로 생성되는데, 실제 센서 배치는
sensor_drive.py에 있다. 둘이 어긋나면 캘리브가 틀린다. 이 스크립트가 두 소스를
AST로 파싱해 카메라 위치·해상도·LiDAR 채널 등을 대조한다(Isaac 비의존).

Usage:
    python3 pipeline/selfcheck.py     # 불일치 있으면 exit 1
"""
import os
import sys
import ast

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sensors import sensor_config as sc  # noqa: E402

DRIVE = os.path.join(ROOT, "sensor_drive.py")


def _assigns(path):
    """소스의 모듈수준 단순 대입(literal) → {name: value}."""
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        t = node.targets[0]
        try:
            val = ast.literal_eval(node.value)
        except Exception:
            continue
        if isinstance(t, ast.Name):
            out[t.id] = val
        elif isinstance(t, ast.Tuple) and isinstance(val, tuple):
            for sub, v in zip(t.elts, val):     # CAM_W, CAM_H = 640, 360
                if isinstance(sub, ast.Name):
                    out[sub.id] = v
    return out


def main():
    dv = _assigns(DRIVE)
    issues = []

    def eq(name, a, b):
        if a != b:
            issues.append(f"{name}: sensor_drive={a} vs sensor_config={b}")

    eq("CAM_W", dv.get("CAM_W"), sc.CAM_W)
    eq("CAM_H", dv.get("CAM_H"), sc.CAM_H)

    # _CAM_LOCAL pos ↔ CAMERAS pos
    cam_local = dv.get("_CAM_LOCAL", {})
    for name, c in sc.CAMERAS.items():
        d = cam_local.get(name, {})
        if tuple(d.get("pos", ())) != tuple(c["pos"]):
            issues.append(f"카메라 {name} pos: drive={d.get('pos')} "
                          f"vs config={c['pos']}")

    # LiDAR 채널/방위/최대거리
    eq("LIDAR_CH", tuple(dv.get("LIDAR_CH", ())),
       tuple(sc.LIDAR["channels_elev_deg"]))
    eq("LIDAR_AZ", dv.get("LIDAR_AZ"), sc.LIDAR["azimuth_bins"])
    eq("LIDAR_MAX", dv.get("LIDAR_MAX"), sc.LIDAR["max_range_m"])

    print("=== 구성 일관성 자가점검 (sensor_config ↔ sensor_drive) ===")
    if issues:
        for i in issues:
            print(f"  ❌ {i}")
        print(f"\n불일치 {len(issues)}건 — 캘리브 드리프트 위험. sensor_config 갱신 필요.")
        sys.exit(1)
    print("  ✅ 카메라 해상도·위치·LiDAR 파라미터 전부 일치")


if __name__ == "__main__":
    main()
