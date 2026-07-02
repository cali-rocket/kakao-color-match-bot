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


def foreground_rect():
    """활성(foreground) 창의 사각형 (left, top, right, bottom) 물리픽셀. 없으면 None."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    r = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    return (int(r.left), int(r.top), int(r.right), int(r.bottom))


def window_under_cursor():
    """커서 아래 최상위 창의 (hwnd, (left,top,right,bottom)). 없으면 None.
    사용자가 게임 창 위에 마우스를 두면 그 창을 정확히 집어낸다."""
    user32 = ctypes.windll.user32
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.restype = wintypes.HWND
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    hwnd = user32.WindowFromPoint(pt)
    if not hwnd:
        return None
    root = user32.GetAncestor(hwnd, 2) or hwnd   # GA_ROOT = 2 (최상위 창)
    r = wintypes.RECT()
    if not user32.GetWindowRect(root, ctypes.byref(r)):
        return None
    return int(root), (int(r.left), int(r.top), int(r.right), int(r.bottom))


def set_foreground(hwnd):
    """해당 창을 활성(foreground)으로. 드래그 입력이 그 창에 전달되게 한다."""
    try:
        ctypes.windll.user32.SetForegroundWindow(int(hwnd))
    except Exception:
        pass


def _send(flags, nx=0, ny=0):
    mi = _MOUSEINPUT(nx, ny, 0, flags, 0, 0)
    inp = _INPUT(0, _INPUT._U(mi))  # type 0 = INPUT_MOUSE
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _abs_flags(extra=0):
    return MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK | extra


def move_abs(pt, vm=None):
    # SetCursorPos: 물리 픽셀 직접(DPI-aware), 멀티모니터 정확. SendInput ABSOLUTE는
    # 이 환경에서 좌표가 어긋나 사용하지 않는다.
    ctypes.windll.user32.SetCursorPos(int(round(pt[0])), int(round(pt[1])))


def left_down_at(pt, vm=None):
    move_abs(pt)
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)


def left_up_at(pt, vm=None):
    move_abs(pt)
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


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
