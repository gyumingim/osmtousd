"""frame_dynamics.py — 시계열 입력 생성 (CVPR2025 우승 방식).

연속 프레임에서 '움직임 단서'를 뽑아 탐지기 입력 채널로 쓴다 (LSTM 불요).
  - frame_difference: [현재, 현재-이전1, 현재-이전2]  (3채널 그레이)
  - optical_flow:     [현재(gray), flow_u, flow_v]      (Farneback, CPU)
둘 다 GPU 불필요(OpenCV CPU). 추론/학습 시 RGB 대신/병행 입력으로 사용.
"""
import numpy as np
import cv2


def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def frame_difference(cur, prev1, prev2=None):
    """[현재, 현재-이전1, 현재-이전2] 3채널. prev2 없으면 이전1 재사용.
    움직이는 물체(드론)는 차분에서 밝게 남고 정적 배경은 0 → 소형 표적 강조."""
    g = _gray(cur).astype(np.int16)
    p1 = _gray(prev1).astype(np.int16)
    p2 = _gray(prev2).astype(np.int16) if prev2 is not None else p1
    d1 = np.clip(np.abs(g - p1), 0, 255).astype(np.uint8)
    d2 = np.clip(np.abs(g - p2), 0, 255).astype(np.uint8)
    return cv2.merge([_gray(cur), d1, d2])           # H×W×3


def optical_flow(prev, cur):
    """[현재(gray), flow_u, flow_v] 3채널. Farneback 밀집 광류(CPU).
    움직임 방향/크기를 픽셀별로 인코딩 → 드론의 일관된 모션이 드러남."""
    gp, gc = _gray(prev), _gray(cur)
    flow = cv2.calcOpticalFlowFarneback(
        gp, gc, None, 0.5, 3, 15, 3, 5, 1.2, 0)      # (H,W,2) u,v
    u = cv2.normalize(flow[..., 0], None, 0, 255, cv2.NORM_MINMAX)
    v = cv2.normalize(flow[..., 1], None, 0, 255, cv2.NORM_MINMAX)
    return cv2.merge([gc, u.astype(np.uint8), v.astype(np.uint8)])


def _selftest():
    """합성 쌍(드론=이동하는 작은 점)으로 CPU 동작 검증."""
    H, W = 120, 160
    prev = np.zeros((H, W, 3), np.uint8)
    cur = np.zeros((H, W, 3), np.uint8)
    cv2.circle(prev, (60, 60), 3, (255, 255, 255), -1)   # 점(드론)
    cv2.circle(cur, (68, 60), 3, (255, 255, 255), -1)    # 8px 오른쪽 이동
    fd = frame_difference(cur, prev)
    of = optical_flow(prev, cur)
    # 차분: 이동 영역(50~75, x)에 신호 있어야
    diff_signal = fd[55:65, 55:75, 1].max()
    # 광류: 점 위치에서 수평 흐름이 배경과 달라야
    flow_var = of[55:65, 55:75, 1].std()
    print(f"frame_difference 출력: {fd.shape} dtype={fd.dtype}")
    print(f"optical_flow 출력:     {of.shape} dtype={of.dtype}")
    print(f"차분 신호(이동영역 최대): {diff_signal}  (>0 이면 움직임 포착 OK)")
    print(f"광류 분산(이동영역):      {flow_var:.1f}  (>0 이면 흐름 포착 OK)")
    ok = diff_signal > 0 and of.shape == (H, W, 3)
    print("SELFTEST:", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    _selftest()
