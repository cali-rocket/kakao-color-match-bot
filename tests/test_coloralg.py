import numpy as np
from kcmb import coloralg as A


def test_color_dist_basic():
    assert A.color_dist([0, 0, 0], [0, 0, 0]) == 0.0
    assert abs(A.color_dist([0, 0, 0], [0, 0, 255]) - 255.0) < 1e-6
    assert abs(A.color_dist([0, 0, 0], [255, 255, 255]) - (255 * 3 ** 0.5)) < 1e-6


def test_swatch_color_flat():
    img = np.full((40, 40, 3), (10, 20, 30), dtype=np.uint8)
    color, disp = A.swatch_color(img)
    assert np.array_equal(color, [10, 20, 30])
    assert disp == 0.0


def test_swatch_color_ignores_border():
    img = np.zeros((40, 40, 3), dtype=np.uint8)
    img[:] = (200, 200, 200)
    img[10:30, 10:30] = (12, 34, 56)  # center 50% region
    color, _ = A.swatch_color(img)
    assert np.array_equal(color, [12, 34, 56])


def test_swatch_color_dispersion_flags_mixed():
    img = np.zeros((40, 40, 3), dtype=np.uint8)
    img[10:20, 10:30] = (0, 0, 0)
    img[20:30, 10:30] = (255, 255, 255)  # half/half center -> high dispersion
    _, disp = A.swatch_color(img)
    assert disp > 50


def test_find_nearest_cluster_locates_target():
    pal = np.zeros((100, 200, 3), dtype=np.uint8)
    pal[:] = (0, 0, 0)
    pal[40:50, 150:160] = (0, 200, 0)
    col, row, d = A.find_nearest_cluster(pal, [0, 200, 0], eps=6)
    assert 150 <= col <= 160 and 40 <= row <= 50
    assert d < 1.0


def test_find_nearest_cluster_robust_to_single_noise_pixel():
    pal = np.full((60, 60, 3), (30, 30, 30), dtype=np.uint8)
    pal[0, 0] = (0, 201, 0)                 # lone noisy near-match at corner
    pal[25:35, 25:35] = (0, 200, 0)         # the real cluster near center
    col, row, _ = A.find_nearest_cluster(pal, [0, 200, 0], eps=6)
    assert 24 <= col <= 35 and 24 <= row <= 35
