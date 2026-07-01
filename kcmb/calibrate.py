"""캘리브레이션: 전체 가상화면을 캡처해 스케일-안전 selectROI로 4개 영역/점을 지정."""
import argparse

import numpy as np
import cv2
import mss

from . import dpi, config as C


def _grab_monitor(index):
    with mss.mss() as sct:
        mon = sct.monitors[index]
        img = np.asarray(sct.grab(mon))[:, :, :3]  # BGR
        return img, mon["left"], mon["top"]


def _select(title, disp_img, scale):
    r = cv2.selectROI(title, disp_img, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow(title)
    x, y, w, h = r
    return int(x / scale), int(y / scale), int(w / scale), int(h / scale)


def _click_point(title, disp_img, scale):
    pt = {}

    def on_mouse(event, x, y, flags, _):
        if event == cv2.EVENT_LBUTTONDOWN:
            pt["x"], pt["y"] = x, y

    cv2.imshow(title, disp_img)
    cv2.setMouseCallback(title, on_mouse)
    while "x" not in pt:
        if cv2.waitKey(20) == 27:  # ESC = skip
            break
    cv2.destroyWindow(title)
    if "x" not in pt:
        return None
    return int(pt["x"] / scale), int(pt["y"] / scale)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--monitor", type=int, default=0, help="0=전체 가상화면")
    args = ap.parse_args()
    dpi.set_dpi_aware()

    img, ox, oy = _grab_monitor(args.monitor)
    h, w = img.shape[:2]
    max_side = 1400
    scale = min(1.0, max_side / max(h, w))
    disp = cv2.resize(img, (int(w * scale), int(h * scale))) if scale < 1.0 else img

    ax, ay, aw, ah = _select("정답 스와치 드래그", disp, scale)
    sx, sy, sw, sh = _select("선택 스와치 드래그", disp, scale)
    px, py, pw, ph = _select("팔레트 영역 드래그", disp, scale)
    mk = _click_point("마커(중앙 피커) 클릭 / ESC=중앙사용", disp, scale)

    cfg = C.load()
    cfg.answer_swatch = C.Region(ox + ax, oy + ay, aw, ah)
    cfg.selected_swatch = C.Region(ox + sx, oy + sy, sw, sh)
    cfg.palette = C.Region(ox + px, oy + py, pw, ph)
    cfg.marker = None if mk is None else [ox + mk[0], oy + mk[1]]
    C.save(cfg)

    print("저장됨 config.json")
    print("정답:", cfg.answer_swatch, "선택:", cfg.selected_swatch)
    print("팔레트:", cfg.palette, "마커:", cfg.marker)
    from . import capture
    from .coloralg import swatch_color
    print("정답 대표색:", swatch_color(capture.grab(cfg.answer_swatch))[0])
    print("선택 대표색:", swatch_color(capture.grab(cfg.selected_swatch))[0])


if __name__ == "__main__":
    main()
