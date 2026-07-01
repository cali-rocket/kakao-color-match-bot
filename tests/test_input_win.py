import numpy as np
from kcmb import input_win as I
from kcmb.config import Config, Region


def test_to_absolute_corners():
    assert I.to_absolute(0, 0, 0, 0, 1920, 1080) == (0, 0)
    nx, ny = I.to_absolute(1919, 1079, 0, 0, 1920, 1080)
    assert nx == 65535 and ny == 65535


def test_to_absolute_negative_origin():
    nx, _ = I.to_absolute(-1920, 0, -1920, 0, 3840, 1080)
    assert nx == 0


def test_settle_swatch_returns_when_stable():
    cfg = Config()  # settle_stable_reads=2, stability_tolerance=6
    frames = [np.full((8, 8, 3), (5, 5, 5), np.uint8),
              np.full((8, 8, 3), (100, 100, 100), np.uint8),  # still moving
              np.full((8, 8, 3), (100, 100, 100), np.uint8),
              np.full((8, 8, 3), (100, 100, 100), np.uint8)]
    it = iter(frames)

    def fake_grab(_region):
        return next(it, frames[-1])

    color = I.settle_swatch(fake_grab, Region(0, 0, 8, 8), cfg)
    assert np.array_equal(color, [100, 100, 100])
