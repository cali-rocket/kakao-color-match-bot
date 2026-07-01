import argparse
import os
import time

import numpy as np
import cv2

from . import dpi, capture, config as C, input_win, controller as K, locate
from .coloralg import swatch_color, color_dist, find_nearest_cluster
from .targetstate import TargetState
from .hotkeys import HotkeyState, install


def _now():
    return time.perf_counter()


def _save_debug(pal, col, row):
    os.makedirs("debug", exist_ok=True)
    img = pal.copy()
    cv2.drawMarker(img, (int(col), int(row)), (255, 255, 255), cv2.MARKER_CROSS, 20, 2)
    cv2.imwrite(f"debug/target_{int(_now()*1000)}.png", img)


def _clamp(p, r):
    return np.array([min(max(p[0], r.left), r.right - 1),
                     min(max(p[1], r.top), r.bottom - 1)], float)


def _settle_selected(cfg):
    input_win.settle_swatch(capture.grab, cfg.selected_swatch, cfg)
    c, _ = swatch_color(capture.grab(cfg.selected_swatch))
    return c


def _start_drag(cfg, Cpt):
    """One horizontal drag through the marker to begin the game."""
    dx = 0.25 * cfg.palette.width
    s = _clamp(Cpt + np.array([-dx, 0.0]), cfg.palette)
    e = _clamp(Cpt + np.array([dx, 0.0]), cfg.palette)
    input_win.drag(s, e, cfg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="계산만, 드래그 안 함")
    ap.add_argument("--autostart", action="store_true", help="시작 시 팔레트 드래그로 게임 시작")
    ap.add_argument("--seconds", type=float, default=0.0, help=">0이면 F8 없이 그 시간 동안 자동 실행")
    ap.add_argument("--no-auto", action="store_true",
                    help="자동검출 끄고 config.json 고정 좌표 사용")
    ap.add_argument("--focus-delay", type=float, default=3.0,
                    help="헤드리스 시작 전 게임 창을 클릭할 시간(초)")
    args = ap.parse_args()
    auto = not args.no_auto   # 기본: 게임 영역 자동검출(창 이동에 무관)

    dpi.set_dpi_aware()
    cfg = C.load()

    def relocate():
        reg = locate.locate_live()
        if reg is not None:
            locate.apply_to(cfg, reg)
            return True
        return False

    if auto:
        if relocate():
            print("auto-located:", cfg.answer_swatch, cfg.selected_swatch, cfg.palette)
        elif not C.is_calibrated(cfg):
            print("게임 영역 자동검출 실패(게임 창이 화면에 보이나요?) & config도 없음")
            return
        else:
            print("자동검출 실패 — config.json 좌표로 대체")
    if not C.is_calibrated(cfg):
        print("calibrate 먼저: python -m kcmb.calibrate (또는 자동검출용 게임 창을 띄우세요)")
        return

    Cpt = cfg.marker_point if cfg.marker_point is not None else cfg.palette.center()
    empty = np.array(cfg.empty_color, dtype=float)
    dim = float(min(cfg.palette.width, cfg.palette.height))
    headless = args.seconds > 0

    if headless:
        class _Auto:
            armed = True
            should_quit = False
        hk = _Auto()
        if args.focus_delay > 0:
            print(f">>> {args.focus_delay:.0f}초 안에 카톡 게임 창을 클릭해 포커스하세요! (드래그가 그 창으로 갑니다)")
            time.sleep(args.focus_delay)
        t_quit = _now() + args.seconds
    else:
        hk = install(HotkeyState())
        t_quit = None
        print("F8=arm/disarm, F9=quit." + (" (dry-run)" if args.dry_run else ""))

    ts = TargetState(cfg)
    gain = None
    prev_v = prev_P = None
    round_start = 0.0
    best_d = float("inf")
    started = False

    while not hk.should_quit and (t_quit is None or _now() < t_quit):
        time.sleep(cfg.loop_delay_ms / 1000.0)
        if not hk.armed:
            continue
        if args.autostart and not started:
            if auto and relocate():   # re-locate in case the window moved since launch
                Cpt = cfg.palette.center()
            _start_drag(cfg, Cpt)
            started = True

        ans, adisp = swatch_color(capture.grab(cfg.answer_swatch))
        if color_dist(ans, empty) < cfg.empty_tol:
            continue  # waiting / between rounds

        if ts.observe(ans, adisp) == "NEW_TARGET":
            gain = None
            prev_v = prev_P = None
            round_start = _now()
            best_d = float("inf")
            print(f"[round] target={ts.target.tolist()}")

        target = ts.target
        if target is None or color_dist(target, empty) < cfg.empty_tol:
            continue
        if _now() - round_start > cfg.round_budget_ms / 1000.0:
            continue

        cur = _settle_selected(cfg)
        d = color_dist(cur, target)
        prev_best = best_d
        best_d = min(best_d, d)
        if K.is_matched(cur, target, cfg.match_tolerance):
            prev_v = prev_P = None
            continue
        # divergence protection: hold if we had a good spot and got much worse
        if prev_best < cfg.hold_margin and d > prev_best + cfg.hold_margin:
            prev_v = prev_P = None
            continue

        pal = capture.grab(cfg.palette)
        col, row, mind = find_nearest_cluster(pal, target, cfg.cluster_eps)
        P = np.array([cfg.palette.left + col, cfg.palette.top + row], float)
        e = P - Cpt

        if args.dry_run:
            print(f"  [dry] target@{P.tolist()} e={e.round(0).tolist()} mind={mind:.1f}")
            _save_debug(pal, col, row)
            continue

        # re-linearize gain from last step, trusting P only when well-located
        if prev_P is not None and prev_v is not None and mind < cfg.gain_gate_mind:
            shift = P - prev_P
            if float(np.linalg.norm(shift)) >= cfg.probe_min_shift_px:
                g = K.estimate_gain(shift, prev_v, cfg.gain_min, cfg.gain_max)
                if g is not None:
                    gain = g if gain is None else \
                        (1 - cfg.gain_smooth_alpha) * gain + cfg.gain_smooth_alpha * g

        if gain is None or mind > cfg.chase_mind:
            v = K.unit(-e) * cfg.probe_px                      # bounded exploratory probe
        else:
            v = -cfg.gain_lambda * e / gain                    # damped correction
            n = float(np.linalg.norm(v))
            if n > cfg.max_drag_frac * dim:
                v = v * (cfg.max_drag_frac * dim / n)

        start = _clamp(Cpt - v / 2.0, cfg.palette)
        end = _clamp(start + v, cfg.palette)
        if float(np.linalg.norm(end - start)) < 2.0:
            v = K.unit(-e) * (cfg.probe_px * 1.6)
            start = _clamp(Cpt - v / 2.0, cfg.palette)
            end = _clamp(start + v, cfg.palette)

        input_win.drag(start, end, cfg)
        prev_P = P
        prev_v = end - start

    print("종료")


if __name__ == "__main__":
    main()
