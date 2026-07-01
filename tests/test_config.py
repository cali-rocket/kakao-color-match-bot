import numpy as np
from kcmb import config as C


def test_region_center():
    r = C.Region(left=10, top=20, width=100, height=80)
    assert np.allclose(r.center(), [60, 60])
    assert r.right == 110 and r.bottom == 100


def test_defaults_not_calibrated():
    cfg = C.Config()
    assert C.is_calibrated(cfg) is False


def test_is_calibrated_true_when_regions_set():
    cfg = C.Config(
        answer_swatch=C.Region(1, 1, 10, 10),
        selected_swatch=C.Region(1, 1, 10, 10),
        palette=C.Region(1, 1, 100, 100),
    )
    assert C.is_calibrated(cfg) is True


def test_marker_point_none_and_set():
    assert C.Config().marker_point is None
    cfg = C.Config(marker=[5, 7])
    assert np.allclose(cfg.marker_point, [5, 7])


def test_save_load_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    cfg = C.Config(palette=C.Region(2, 3, 40, 50), marker=[10, 11], match_tolerance=9)
    C.save(cfg, str(p))
    got = C.load(str(p))
    assert got.palette.width == 40 and got.palette.top == 3
    assert got.marker == [10, 11]
    assert got.match_tolerance == 9


def test_load_missing_returns_defaults(tmp_path):
    got = C.load(str(tmp_path / "nope.json"))
    assert C.is_calibrated(got) is False
