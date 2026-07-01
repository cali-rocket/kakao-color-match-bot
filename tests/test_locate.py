import numpy as np
import cv2
from kcmb import locate


def _scene():
    img = np.full((600, 800, 3), 255, np.uint8)          # white background
    band = np.zeros((120, 320, 3), np.uint8)             # hue-gradient band
    for x in range(320):
        hue = int(x / 320 * 179)
        band[:, x] = cv2.cvtColor(np.uint8([[[hue, 255, 255]]]), cv2.COLOR_HSV2BGR)[0, 0]
    img[300:420, 200:520] = band
    return img


def test_find_band_locates_gradient():
    b = locate.find_band(_scene())
    assert b is not None
    x, y, w, h = b
    assert abs(x - 200) < 10 and abs(y - 300) < 10 and abs(w - 320) < 10


def test_find_band_none_on_plain():
    img = np.full((600, 800, 3), 255, np.uint8)
    assert locate.find_band(img) is None


def test_locate_offsets_apply_origin():
    r = locate.locate(_scene(), ox=1000, oy=500)
    assert r is not None
    a, s, p = r["answer_swatch"], r["selected_swatch"], r["palette"]
    assert a.left == 1000 + 200 + 84 and a.top == 500 + 300 - 92
    assert s.left == 1000 + 200 + 172
    assert a.width == 72 and a.height == 72
    assert p.left == 1000 + 200 and p.width == 320
