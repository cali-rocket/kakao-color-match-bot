from typing import Optional, Tuple

import numpy as np

from .coloralg import color_dist


def is_matched(cur, target, tol) -> bool:
    return color_dist(cur, target) <= tol


def unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    n = float(np.linalg.norm(v))
    if n < 1e-9:
        return np.array([1.0, 0.0])
    return v / n


def palette_dim(region) -> float:
    return float(min(region.width, region.height))


def clamp_point(pt, region) -> np.ndarray:
    x = min(max(float(pt[0]), region.left), region.right - 1)
    y = min(max(float(pt[1]), region.top), region.bottom - 1)
    return np.array([x, y], dtype=np.float64)


def probe_plan(C, ehat, probe_frac, region) -> Tuple[np.ndarray, np.ndarray]:
    mag = probe_frac * palette_dim(region)
    v = np.asarray(ehat, dtype=np.float64) * mag
    start = clamp_point(np.asarray(C, dtype=float) - v / 2.0, region)
    end = clamp_point(start + v, region)
    return start, end


def estimate_gain(measured_shift, cursor_move, gain_min, gain_max) -> Optional[float]:
    cm = np.asarray(cursor_move, dtype=np.float64)
    ms = np.asarray(measured_shift, dtype=np.float64)
    denom = float(cm @ cm)
    if denom < 1e-9:
        return None
    g = float(ms @ cm) / denom
    sign = 1.0 if g >= 0 else -1.0
    mag = min(max(abs(g), gain_min), gain_max)
    return sign * mag


def update_gain(gain, cursor_move, measured_shift, min_dist, cfg) -> float:
    cm = np.asarray(cursor_move, dtype=np.float64)
    ms = np.asarray(measured_shift, dtype=np.float64)
    if min_dist > cfg.cluster_eps:
        return gain
    if float(np.linalg.norm(cm)) < cfg.move_floor_px:
        return gain
    dot = float(ms @ cm)
    if dot <= 0:
        return gain
    proj = (dot / float(cm @ cm)) * cm
    perp = ms - proj
    if float(np.linalg.norm(perp)) > float(np.linalg.norm(proj)):
        return gain  # cluster jump, not a clean pan
    est = estimate_gain(ms, cm, cfg.gain_min, cfg.gain_max)
    if est is None:
        return gain
    a = cfg.gain_smooth_alpha
    return (1.0 - a) * gain + a * est


def plan_drag(e, gain, C, region, cfg) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    e = np.asarray(e, dtype=np.float64)
    if float(np.linalg.norm(e)) <= cfg.e_deadband_px:
        return None
    if abs(gain) < 1e-9:
        return None
    v = -cfg.gain_lambda * e / gain
    cap = cfg.max_drag_frac * palette_dim(region)
    n = float(np.linalg.norm(v))
    if n > cap:
        v = v * (cap / n)
    start = clamp_point(np.asarray(C, dtype=float) - v / 2.0, region)
    end = clamp_point(start + v, region)
    if float(np.linalg.norm(end - start)) < 1.0:
        return None
    return start, end
