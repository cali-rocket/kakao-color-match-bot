import numpy as np
import mss

_sct = None


def _grabber():
    global _sct
    if _sct is None:
        _sct = mss.mss()
    return _sct


def to_bgr(bgra) -> np.ndarray:
    arr = np.asarray(bgra)
    return arr[:, :, :3]


def grab(region) -> np.ndarray:
    mon = {"left": int(region.left), "top": int(region.top),
           "width": int(region.width), "height": int(region.height)}
    raw = _grabber().grab(mon)
    return to_bgr(np.asarray(raw))
