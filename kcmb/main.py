import argparse
import os
import time

import numpy as np
import cv2

from . import dpi, capture, config as C, input_win, controller as K
from .coloralg import swatch_color, color_dist, find_nearest_cluster
from .targetstate import TargetState
from .hotkeys import HotkeyState, install


def _now_ms():
    return time.perf_counter() * 1000.0


def _save_debug(pal, col, row):
    os.makedirs("debug", exist_ok=True)
    img = pal.copy()
    cv2.drawMarker(img, (int(col), int(row)), (255, 255, 255),
                   cv2.MARKER_CROSS, 20, 2)
    cv2.imwrite(f"debug/target_{int(_now_ms())}.png", img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    dpi.set_dpi_aware()
    cfg = C.load()
    if not C.is_calibrated(cfg):
        print("calibrate 먼저: python -m kcmb.calibrate")
        return

    Cpt = cfg.marker_point if cfg.marker_point is not None else cfg.palette.center()
    hk = install(HotkeyState())
    ts = TargetState(cfg)
    gain = None
    prev_v = prev_P = None
    round_start = 0.0
    best_dist = float("inf")
    no_improve = 0
    prev_dist = float("inf")
    print("F8=arm/disarm, F9=quit. (dry-run)" if args.dry_run else "F8=arm/disarm, F9=quit.")

    while not hk.should_quit:
        time.sleep(cfg.loop_delay_ms / 1000.0)
        if not hk.armed:
            continue

        ans, adisp = swatch_color(capture.grab(cfg.answer_swatch))
        if ts.observe(ans, adisp) == "NEW_TARGET":
            gain = None
            prev_v = prev_P = None
            round_start = _now_ms()
            best_dist = float("inf")
            no_improve = 0
            prev_dist = float("inf")
            print(f"[round] new target {ts.target}")

        target = ts.target
        if target is None:
            continue
        if _now_ms() - round_start > cfg.round_budget_ms:
            continue  # 예산 초과 → best-effort 대기

        input_win.settle_swatch(capture.grab, cfg.selected_swatch, cfg)
        cur, _ = swatch_color(capture.grab(cfg.selected_swatch))
        d = color_dist(cur, target)
        if K.is_matched(cur, target, cfg.match_tolerance):
            prev_v = prev_P = None
            continue

        if d < best_dist - cfg.improve_margin:
            best_dist = d
            no_improve = 0
        else:
            no_improve += 1
        if no_improve >= cfg.stall_no_improve_n or d > prev_dist:
            prev_v = prev_P = None
            continue  # stall/발산 → 이 타깃 드래그 중단
        prev_dist = d

        pal = capture.grab(cfg.palette)
        col, row, mind = find_nearest_cluster(pal, target, cfg.cluster_eps)
        P = np.array([cfg.palette.left + col, cfg.palette.top + row], dtype=float)
        e = P - Cpt

        if args.dry_run:
            print(f"[dry] target@{P} e={e} mind={mind:.1f}")
            _save_debug(pal, col, row)
            continue  # dry-run: 목표 위치만 검증

        if gain is None:
            if prev_P is None:
                # 라운드 첫 드래그 = 부호 탐침
                start, end = K.probe_plan(Cpt, K.unit(-e), cfg.probe_frac, cfg.palette)
            else:
                # 부호 탐침의 실측 이동으로 signed gain 확립
                shift = P - prev_P
                if float(np.linalg.norm(shift)) < cfg.probe_min_shift_px:
                    print("[warn] 색판 미반응(probe shift too small) — 라운드 스킵")
                    prev_P = prev_v = None
                    continue
                gain = K.estimate_gain(shift, prev_v, cfg.gain_min, cfg.gain_max)
                if gain is None:
                    prev_P = prev_v = None
                    continue
                plan = K.plan_drag(e, gain, Cpt, cfg.palette, cfg)
                if plan is None:
                    continue
                start, end = plan
        else:
            gain = K.update_gain(gain, prev_v, P - prev_P, mind, cfg)
            plan = K.plan_drag(e, gain, Cpt, cfg.palette, cfg)
            if plan is None:
                continue
            start, end = plan

        input_win.drag(start, end, cfg)
        prev_P = P
        prev_v = end - start

    print("종료")


if __name__ == "__main__":
    main()
