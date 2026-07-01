import numpy as np
from kcmb import controller as K
from kcmb.config import Config, Region

PAL = Region(left=0, top=0, width=200, height=200)
C = PAL.center()  # [100, 100]


def test_is_matched():
    assert K.is_matched([10, 10, 10], [12, 11, 10], tol=10) is True
    assert K.is_matched([0, 0, 0], [0, 0, 255], tol=10) is False


def test_plan_drag_direction_pans_target_to_center():
    e = np.array([60.0, 0.0])
    cfg = Config()
    start, end = K.plan_drag(e, gain=1.0, C=C, region=PAL, cfg=cfg)
    v = end - start
    assert v[0] < 0


def test_plan_drag_deadband_returns_none():
    cfg = Config()
    assert K.plan_drag(np.array([2.0, 1.0]), 1.0, C, PAL, cfg) is None


def test_plan_drag_stays_in_bounds():
    cfg = Config()
    for e in ([180.0, 0.0], [-180.0, 0.0], [0.0, 180.0], [0.0, -180.0]):
        start, end = K.plan_drag(np.array(e), 1.0, C, PAL, cfg)
        for p in (start, end):
            assert PAL.left <= p[0] <= PAL.right - 1
            assert PAL.top <= p[1] <= PAL.bottom - 1


def test_estimate_gain_sign():
    g = K.estimate_gain(measured_shift=[20, 0], cursor_move=[20, 0], gain_min=0.05, gain_max=20)
    assert abs(g - 1.0) < 1e-6
    g2 = K.estimate_gain(measured_shift=[-10, 0], cursor_move=[20, 0], gain_min=0.05, gain_max=20)
    assert g2 < 0


def test_update_gain_gates_on_cluster_jump():
    cfg = Config()
    g = K.update_gain(1.0, cursor_move=[40, 0], measured_shift=[0, 40], min_dist=0.0, cfg=cfg)
    assert g == 1.0


def test_update_gain_gates_on_min_dist():
    cfg = Config()  # cluster_eps=6
    g = K.update_gain(1.0, cursor_move=[40, 0], measured_shift=[40, 0], min_dist=99.0, cfg=cfg)
    assert g == 1.0


def _simulate(k_true, e0, cfg, max_steps=8):
    """가상 색판: 드래그 커서이동 v에 대해 타깃 위치가 P += k_true*v 만큼 이동."""
    P = C + np.array(e0, dtype=float)
    gain = None
    prev_P = prev_v = None
    traj = [np.linalg.norm(P - C)]
    for _ in range(max_steps):
        e = P - C
        if np.linalg.norm(e) <= cfg.e_deadband_px:
            return True, traj
        if gain is None:
            start, end = K.probe_plan(C, K.unit(-e), cfg.probe_frac, PAL)
            v = end - start
            prev_P = P
            P = P + k_true * v
            gain = K.estimate_gain(P - prev_P, v, cfg.gain_min, cfg.gain_max)
            prev_v = v
            traj.append(np.linalg.norm(P - C))
            continue
        gain = K.update_gain(gain, prev_v, P - prev_P, 0.0, cfg)
        plan = K.plan_drag(e, gain, C, PAL, cfg)
        if plan is None:
            return True, traj
        start, end = plan
        v = end - start
        prev_P = P
        P = P + k_true * v
        prev_v = v
        traj.append(np.linalg.norm(P - C))
    return np.linalg.norm(P - C) <= cfg.e_deadband_px, traj


def test_closed_loop_converges_positive_gain():
    cfg = Config()
    ok, traj = _simulate(k_true=1.0, e0=[70, -40], cfg=cfg)
    assert ok, traj


def test_closed_loop_converges_wrong_sign_gain():
    cfg = Config()
    ok, traj = _simulate(k_true=-1.0, e0=[70, -40], cfg=cfg)
    assert ok, traj


def test_closed_loop_does_not_diverge_large_gain():
    cfg = Config()
    ok, traj = _simulate(k_true=3.0, e0=[60, 0], cfg=cfg)
    assert max(traj) < 400
