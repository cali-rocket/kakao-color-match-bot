import numpy as np
from kcmb import capture


def test_to_bgr_drops_alpha():
    bgra = np.zeros((5, 7, 4), dtype=np.uint8)
    bgra[..., 0] = 1
    bgra[..., 1] = 2
    bgra[..., 2] = 3
    bgra[..., 3] = 255
    bgr = capture.to_bgr(bgra)
    assert bgr.shape == (5, 7, 3)
    assert np.array_equal(bgr[0, 0], [1, 2, 3])


def test_dpi_set_returns_string():
    from kcmb import dpi
    assert isinstance(dpi.set_dpi_aware(), str)
