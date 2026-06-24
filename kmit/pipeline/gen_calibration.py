"""센서 캘리브레이션 자동 생성 (TODO 1-B) — Isaac 비의존.

sensors/sensor_config.py 로부터 카메라 내부행렬(K)·각 센서의 ego 기준 외부
변환(4x4)·동기 타임스탬프를 계산해 calibration.json 으로 출력. 데이터셋마다
복사해 두면 패키징에 포함된다(라벨/포인트클라우드 좌표 해석에 필요).

Usage:
    python3 pipeline/gen_calibration.py            # config/calibration.json
    python3 pipeline/gen_calibration.py --datasets # 각 output/scenario_*/* 에도 복사
"""
import os
import sys
import json
import glob
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sensors import sensor_config as sc  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _norm(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return [c / n for c in v]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def _extrinsic(pos, look):
    """센서→ego 4x4. 카메라 광축=look(+forward), up=world up.
    열: right, up, forward, translation."""
    f = _norm(look)
    up = list(sc.WORLD_UP)
    r = _norm(_cross(up, f))
    u = _cross(f, r)
    # 4x4 (행 우선): [r u f t]를 열로
    return [
        [r[0], u[0], f[0], pos[0]],
        [r[1], u[1], f[1], pos[1]],
        [r[2], u[2], f[2], pos[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def build_calibration():
    K = sc.camera_intrinsics()
    hfov = 2 * math.degrees(math.atan(
        sc.CAM_H_APERTURE_MM / (2 * sc.CAM_FOCAL_MM)))
    cams = {}
    for name, c in sc.CAMERAS.items():
        cams[name] = {
            "intrinsics_K": [[round(v, 3) for v in row] for row in K],
            "resolution": [sc.CAM_W, sc.CAM_H],
            "focal_mm": sc.CAM_FOCAL_MM,
            "hfov_deg": round(hfov, 2),
            "extrinsic_to_ego": _extrinsic(c["pos"], c["dir"]),
        }
    return {
        "coordinate_frame": "ego-local (x=forward, y=left, z=up), meters",
        "sync": {"all_sensors_hz": sc.SAMPLE_HZ,
                 "note": "전 센서 동일 시뮬 스텝 → 시간동기(타임스탬프 = frame/Hz)"},
        "cameras": cams,
        "lidar": {
            "extrinsic_translation": list(sc.LIDAR["mount"]),
            "channels_elev_deg": sc.LIDAR["channels_elev_deg"],
            "azimuth_bins": sc.LIDAR["azimuth_bins"],
            "max_range_m": sc.LIDAR["max_range_m"],
        },
        "radar": {
            "extrinsic_translation": list(sc.RADAR["mount"]),
            "fov_deg": sc.RADAR["fov_deg"], "beams": sc.RADAR["beams"],
            "max_range_m": sc.RADAR["max_range_m"],
        },
        "ultrasonic": {
            "sensors": sc.ULTRASONIC["sensors"],
            "max_range_m": sc.ULTRASONIC["max_range_m"],
        },
    }


def main():
    calib = build_calibration()
    os.makedirs(os.path.join(ROOT, "config"), exist_ok=True)
    gpath = os.path.join(ROOT, "config", "calibration.json")
    json.dump(calib, open(gpath, "w"), indent=2, ensure_ascii=False)
    print(f"✅ {gpath}")
    fx = calib["cameras"]["front"]["intrinsics_K"][0][0]
    print(f"   카메라 K: fx={fx} hfov={calib['cameras']['front']['hfov_deg']}°"
          f" · LiDAR {len(calib['lidar']['channels_elev_deg'])}채널"
          f" · {calib['sync']['all_sensors_hz']}Hz 동기")
    if "--datasets" in sys.argv:
        n = 0
        for cd in glob.glob(os.path.join(ROOT, "output", "scenario_*", "*")):
            if os.path.isdir(cd):
                json.dump(calib, open(os.path.join(cd, "calibration.json"),
                                      "w"), indent=2, ensure_ascii=False)
                n += 1
        print(f"   데이터셋 {n}곳에 calibration.json 복사")


if __name__ == "__main__":
    main()
