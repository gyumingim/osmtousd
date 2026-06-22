"""데이터 표준화 스키마 (TODO 공통인프라 schema.py)

ZIP 패키지 내부 구조·파일명 규칙의 단일 출처. packager/validate_zip 이 참조해
포맷 드리프트를 방지한다.

ZIP 구조:
    data/    frame_NNNN.png            합성 멀티센서 합성뷰
    labels/  frame_NNNN.json           프레임 라벨(bbox2d/3d·ego·ttc 등)
             frame_NNNN.yaml           동일 내용 yaml
             frame_NNNN_seg.png        시맨틱 세그
             frame_NNNN_inst.png       인스턴스 세그
             frame_NNNN_depth.png      깊이맵
             frame_NNNN_lidar.pcd      LiDAR 점구름(ASCII)
             frame_NNNN_radar.csv      Radar 검지
             frame_NNNN_ultrasonic.csv 초음파 검지
             trajectories.json         객체·ego 궤적 트랙
             v2x_log.json              (V2X 시나리오) 통신 로그
    meta/    metadata.json             데이터셋 스펙·통계
             calibration.json          센서 내·외부 파라미터
    README.md
"""

FRAME_FMT = "frame_{:04d}"

# ZIP 내부 경로 규칙
PATHS = {
    "data": "data/",
    "labels": "labels/",
    "meta": "meta/",
    "metadata": "meta/metadata.json",
    "calibration": "meta/calibration.json",
    "readme": "README.md",
}

# 프레임당 라벨 파일 접미사
LABEL_SUFFIX = {
    "seg": "_seg.png", "inst": "_inst.png", "depth": "_depth.png",
    "lidar": "_lidar.pcd", "radar": "_radar.csv", "ultrasonic": "_ultrasonic.csv",
}

# metadata.json 필수 키
META_REQUIRED = ["scenario", "scenario_name", "variant", "frame_count",
                 "sensors", "labels", "source"]

# 의미 클래스(라벨) 화이트리스트
CLASSES = ["building", "road", "road_marking", "crosswalk", "sidewalk",
           "traffic_sign", "traffic_light", "car", "truck", "bus",
           "motorcycle", "bicycle", "pedestrian"]

# 데이터셋 폴더명 규칙: scenario_NN/<variant>
DATASET_DIR_RE = r"scenario_\d2/[A-Za-z0-9_]+"


def frame_name(i):
    return FRAME_FMT.format(i)


def zip_name(scenario, variant):
    return f"{scenario}_{variant}.zip"
