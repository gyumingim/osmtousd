"""센서 리그 구성 (TODO 1-B) — 순수 데이터(Isaac 비의존).

sensor_drive.py의 실제 센서 배치와 일치하는 단일 출처. 캘리브레이션 생성
(pipeline/gen_calibration.py)과 문서화가 이 값을 공유한다. ego 로컬 좌표계
(x=전방, y=좌, z=상). 단위 m, 각도 deg.
"""

# ── 공통 ─────────────────────────────────────────────────────────────────────
SAMPLE_HZ = 10                      # 전 센서 동기 샘플링(동일 스텝)
WORLD_UP = (0.0, 0.0, 1.0)

# ── 카메라 4대 (ego 로컬 pos·바라보는 방향) ─────────────────────────────────
CAM_W, CAM_H = 640, 360
CAM_FOCAL_MM = 18.0
CAM_H_APERTURE_MM = 20.955          # Omniverse 기본 수평 aperture
CAMERAS = {
    "front": {"pos": (2.0,  0.0, 1.5), "dir": (1,  0, 0)},
    "back":  {"pos": (-2.0, 0.0, 1.5), "dir": (-1, 0, 0)},
    "left":  {"pos": (0.0,  1.5, 1.5), "dir": (0,  1, 0)},
    "right": {"pos": (0.0, -1.5, 1.5), "dir": (0, -1, 0)},
}

# ── LiDAR (PhysX raycast 점구름) ─────────────────────────────────────────────
LIDAR = {
    "mount": (0.0, 0.0, 2.2),
    "channels_elev_deg": [-15, -11, -8, -5, -3, -1, 0, 1, 2, 4, 7, 11],
    "azimuth_bins": 200,
    "max_range_m": 100.0,
}

# ── Radar (전방 FMCW 근사) ───────────────────────────────────────────────────
RADAR = {
    "mount": (3.0, 0.0, 0.5),
    "fov_deg": 60,
    "beams": 15,
    "max_range_m": 120.0,
}

# ── 초음파 8개 (범퍼 근접) ───────────────────────────────────────────────────
ULTRASONIC = {
    "max_range_m": 5.0,
    "sensors": ["FL", "FR", "RL", "RR", "SL1", "SL2", "SR1", "SR2"],
}


def camera_intrinsics():
    """focal/aperture/해상도 → K(3x3), 정사각 픽셀 가정."""
    fx = CAM_FOCAL_MM / CAM_H_APERTURE_MM * CAM_W
    fy = fx                                   # square pixels
    cx, cy = CAM_W / 2.0, CAM_H / 2.0
    return [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]]
