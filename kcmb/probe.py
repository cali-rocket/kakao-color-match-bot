"""상호작용 탐침: config가 있어야 함(calibrate 먼저). 한 번 드래그해서
(1) 색판이 반응하는지 (2) 커서와 같은/반대 방향인지 (3) 놓은 뒤 계속 움직이는지(플링)
를 사람이 확인한다."""
import time

import numpy as np

from . import dpi, capture, input_win, config as C
from .coloralg import swatch_color, color_dist


def main():
    dpi.set_dpi_aware()
    cfg = C.load()
    if not C.is_calibrated(cfg):
        print("calibrate 먼저: python -m kcmb.calibrate")
        return
    Cpt = cfg.marker_point if cfg.marker_point is not None else cfg.palette.center()
    print("게임 창을 활성화하세요. 3초 후 팔레트에서 오른쪽으로 고정 드래그를 1회 실행합니다.")
    time.sleep(3)

    before, _ = swatch_color(capture.grab(cfg.selected_swatch))
    dim = min(cfg.palette.width, cfg.palette.height)
    start = np.array([Cpt[0] - 0.15 * dim, Cpt[1]])
    end = np.array([Cpt[0] + 0.15 * dim, Cpt[1]])  # 커서 오른쪽 이동
    print(f"drag {start} -> {end} (커서 +x)")
    input_win.drag(start, end, cfg)

    time.sleep(0.15)
    after1, _ = swatch_color(capture.grab(cfg.selected_swatch))
    time.sleep(0.3)
    after2, _ = swatch_color(capture.grab(cfg.selected_swatch))

    print(f"선택색 before={before} after(+150ms)={after1} after(+450ms)={after2}")
    print(f"변화량 |after1-before| = {color_dist(after1, before):.1f}")
    print(f"놓은 뒤 추가변화(플링) |after2-after1| = {color_dist(after2, after1):.1f}")
    print("→ 변화가 0이면 미반응/잠금. after2!=after1이면 플링(관성) 있음.")


if __name__ == "__main__":
    main()
