import numpy as np
from kcmb.targetstate import TargetState
from kcmb.config import Config


def feed(ts, color, disp=0.0, n=1):
    ev = None
    for _ in range(n):
        ev = ts.observe(np.array(color, dtype=float), disp)
    return ev


def test_first_round_fires_after_stable_frames():
    ts = TargetState(Config())  # stability_frames=2
    assert feed(ts, [10, 20, 30]) is None          # frame 1
    assert feed(ts, [10, 20, 30]) is None           # frame 2 (count=1)
    assert feed(ts, [10, 20, 30]) == 'NEW_TARGET'   # frame 3 (count=2)
    assert np.allclose(ts.target, [10, 20, 30])


def test_no_duplicate_for_same_target():
    ts = TargetState(Config())
    feed(ts, [10, 20, 30], n=3)
    assert feed(ts, [10, 20, 30], n=5) is None


def test_new_target_after_change():
    ts = TargetState(Config())
    feed(ts, [10, 20, 30], n=3)
    assert feed(ts, [200, 10, 10], n=3) == 'NEW_TARGET'


def test_dispersion_frame_rejected():
    ts = TargetState(Config())  # dispersion_tolerance=12
    assert feed(ts, [10, 20, 30], disp=50.0, n=5) is None


def test_similar_within_threshold_not_new_round():
    ts = TargetState(Config())  # new_round_threshold=40
    feed(ts, [10, 20, 30], n=3)
    assert feed(ts, [16, 24, 33], n=5) is None
