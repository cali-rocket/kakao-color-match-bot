import ctypes
import time
from ctypes import wintypes

import numpy as np

from .coloralg import swatch_color, color_dist

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def to_absolute(px, py, vx, vy, vcx, vcy):
    nx = round((px - vx) * 65535 / (vcx - 1))
    ny = round((py - vy) * 65535 / (vcy - 1))
    return int(nx), int(ny)


def vscreen_metrics():
    gsm = ctypes.windll.user32.GetSystemMetrics
    return (gsm(SM_XVIRTUALSCREEN), gsm(SM_YVIRTUALSCREEN),
            gsm(SM_CXVIRTUALSCREEN), gsm(SM_CYVIRTUALSCREEN))


def _send(flags, nx=0, ny=0):
    mi = _MOUSEINPUT(nx, ny, 0, flags, 0, 0)
    inp = _INPUT(0, _INPUT._U(mi))  # type 0 = INPUT_MOUSE
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _abs_flags(extra=0):
    return MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK | extra


def move_abs(pt, vm=None):
    vm = vm or vscreen_metrics()
    nx, ny = to_absolute(pt[0], pt[1], *vm)
    _send(_abs_flags(), nx, ny)


def left_down_at(pt, vm=None):
    vm = vm or vscreen_metrics()
    nx, ny = to_absolute(pt[0], pt[1], *vm)
    _send(_abs_flags(MOUSEEVENTF_LEFTDOWN), nx, ny)


def left_up_at(pt, vm=None):
    vm = vm or vscreen_metrics()
    nx, ny = to_absolute(pt[0], pt[1], *vm)
    _send(_abs_flags(MOUSEEVENTF_LEFTUP), nx, ny)


def drag(start, end, cfg):
    """fling 방지 모션 프로파일: pre-dwell 임계통과 → ease-in/out → 종단 정지 dwell."""
    start = np.asarray(start, dtype=float)
    end = np.asarray(end, dtype=float)
    vm = vscreen_metrics()
    left_down_at(start, vm)
    time.sleep(cfg.drag_pre_dwell_ms / 1000.0)
    d = end - start
    n = float(np.linalg.norm(d))
    nudge = start + (d / n) * 2.0 if n > 1e-6 else start + np.array([2.0, 0.0])
    move_abs(nudge, vm)
    time.sleep(0.005)
    steps = max(2, cfg.drag_steps)
    for i in range(1, steps + 1):
        t = i / steps
        s = t * t * (3 - 2 * t)  # smoothstep ease-in/out
        move_abs(start + d * s, vm)
        time.sleep(cfg.drag_step_ms / 1000.0)
    time.sleep(cfg.drag_end_dwell_ms / 1000.0)  # 종단 속도 0
    left_up_at(end, vm)


def settle_swatch(grab_fn, region, cfg):
    """선택 스와치가 연속 안정될 때까지 폴링하여 최종 대표색 반환."""
    prev = None
    stable = 0
    waited = 0
    while waited <= cfg.settle_cap_ms:
        cur, _ = swatch_color(grab_fn(region))
        if prev is not None and color_dist(cur, prev) <= cfg.stability_tolerance:
            stable += 1
            if stable >= cfg.settle_stable_reads:
                return cur
        else:
            stable = 0
        prev = cur
        time.sleep(cfg.settle_poll_ms / 1000.0)
        waited += cfg.settle_poll_ms
    return prev
