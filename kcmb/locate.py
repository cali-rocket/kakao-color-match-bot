"""게임 영역 자동 검출: 팔레트의 채도 그라데이션 밴드를 앵커로 잡고,
정답/선택 스와치·팔레트를 고정 오프셋으로 계산한다. 카톡 게임 창은 크기가
일정하고 위치만 변하므로(팝업), 밴드 대비 상대 오프셋은 UI 상수로 일정하다.
→ 창이 움직여도 매번 올바른 좌표를 얻어, 고정 캘리브레이션의 취약성을 없앤다."""
import numpy as np
import cv2

from .config import Region

# 팔레트 채도밴드 좌상단 대비 오프셋(게임 UI 상수, 알려진 캘리브레이션에서 측정)
_ANS_DX = 84
_SEL_DX = 172
_SW_DY = -92
_SW = 72
_PAL_DY = -3
_PAL_HFRAC = 0.75


def _has_marker(sub_bgr):
    """중앙 영역에 게임의 흰 마커(핀)로 보이는 compact near-white blob이 있는가."""
    white = np.all(sub_bgr > 225, axis=2).astype(np.uint8)
    white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _lab, stats, _c = cv2.connectedComponentsWithStats(white, 8)
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        if 150 < a < 4000 and 0.5 < w / max(h, 1) < 2.0:
            return True
    return False


def find_band(bgr):
    """팔레트의 색 그라데이션 영역 (x,y,w,h) 반환, 없으면 None.
    창-범위(게임 창) 안에서 쓰므로 decoy가 없다 → 폭이 맞는 최대 그라데이션이 팔레트.
    마커(핀)는 '선택' 색을 띠어 흰색이 아닐 수 있으므로 필수 조건으로 쓰지 않고,
    흰 마커가 있으면 우선(전체화면 폴백 시 decoy 배제용)하는 정도로만 사용."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = (hsv[:, :, 1] > 50).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    marked, plain = [], []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if not (280 < w < 380 and 90 < h < 320):   # 팔레트 폭은 일정, 높이는 가변
            continue
        sub = hsv[y:y + h, x:x + w]
        hues = sub[:, :, 0][sub[:, :, 1] > 50]
        if hues.size == 0 or int(np.ptp(hues)) < 40:   # near-solid(버튼/텍스트) 배제
            continue
        cen = bgr[y + h // 5:y + 4 * h // 5, x + w // 3:x + 2 * w // 3]
        (marked if _has_marker(cen) else plain).append((x, y, w, h))
    pool = marked or plain   # 흰 마커 있으면 우선, 없으면 최대 그라데이션(창 안이라 안전)
    if not pool:
        return None
    return max(pool, key=lambda b: b[2] * b[3])


def _marker_point(bgr, box):
    """밴드 중앙 영역에서 흰 마커(핀)의 centroid (x,y) 반환. 없으면 None.
    이 지점이 게임의 실제 색 샘플 지점 = 컨트롤러 기준점 C."""
    x, y, w, h = box
    rx0, ry0 = x + w // 3, y
    sub = bgr[ry0:y + h, rx0:x + 2 * w // 3]
    white = np.all(sub > 225, axis=2).astype(np.uint8)
    white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _lab, stats, cents = cv2.connectedComponentsWithStats(white, 8)
    best = None
    for i in range(1, n):
        a = int(stats[i, cv2.CC_STAT_AREA])
        ww = int(stats[i, cv2.CC_STAT_WIDTH])
        hh = int(stats[i, cv2.CC_STAT_HEIGHT])
        if 150 < a < 4000 and 0.5 < ww / max(hh, 1) < 2.0:
            if best is None or a > best[0]:
                best = (a, cents[i])
    if best is None:
        return None
    return (int(rx0 + best[1][0]), int(ry0 + best[1][1]))


def locate(bgr, ox=0, oy=0):
    """전체화면 BGR에서 게임 영역을 검출. {answer_swatch, selected_swatch, palette, marker} 또는 None."""
    b = find_band(bgr)
    if b is None:
        return None
    bx, by, bw, bh = b
    ph = int(bw * _PAL_HFRAC)
    out = {
        "answer_swatch": Region(ox + bx + _ANS_DX, oy + by + _SW_DY, _SW, _SW),
        "selected_swatch": Region(ox + bx + _SEL_DX, oy + by + _SW_DY, _SW, _SW),
        "palette": Region(ox + bx, oy + by + _PAL_DY, bw, ph),
    }
    mk = _marker_point(bgr, b)
    if mk is not None:
        out["marker"] = [ox + mk[0], oy + mk[1]]
    return out


# 게임 창(전체, 타이틀바 포함) 대비 UI 요소의 고정 비율 (420x640 창에서 측정).
# 게임 창은 고정 크기 팝업이라 팔레트/스와치 위치가 창 대비 일정 → 팔레트 색/채도
# 분포와 무관하게 정확히 영역을 얻는다.
_FRAC = {
    "answer_swatch": (0.3095, 0.4062, 0.1714, 0.1125),
    "selected_swatch": (0.5190, 0.4062, 0.1714, 0.1125),
    "palette": (0.1095, 0.5406, 0.7810, 0.3844),
}


def regions_from_window(l, t, ww, hh):
    """게임 창 사각형 대비 고정 비율로 {answer_swatch, selected_swatch, palette} 계산."""
    return {k: Region(int(l + fx * ww), int(t + fy * hh), int(fw * ww), int(fh * hh))
            for k, (fx, fy, fw, fh) in _FRAC.items()}


def palette_is_gradient(bgr):
    """팔레트 영역 crop이 실제 색 그라데이션인지(시작/플레이 화면) 판정.
    결과화면(흰 배경+텍스트)은 채도 높은 픽셀이 거의 없어(≈5%) 걸러진다
    (진짜 팔레트는 창백해도 ≈60%가 채도>60)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    if float((sat > 60).mean()) < 0.20:
        return False
    hues = hsv[:, :, 0][sat > 40]
    return hues.size > 500 and int(np.ptp(hues)) > 55


def locate_live():
    """Win32로 게임 창을 찾아 고정 비율로 영역 계산. 팔레트가 그라데이션일 때만
    반환(결과화면 등은 None). 커서 위치와 무관. dict 또는 None."""
    from . import capture
    from .input_win import find_game_window
    gw = find_game_window()
    if gw is None:
        return None
    l, t, r, b = gw[1]
    reg = regions_from_window(l, t, r - l, b - t)
    try:
        if not palette_is_gradient(capture.grab(reg["palette"])):
            return None
    except Exception:
        return None
    return reg


def apply_to(cfg, regions):
    """검출된 regions를 cfg에 반영. C는 팔레트 기하중심 사용(marker=None)."""
    cfg.answer_swatch = regions["answer_swatch"]
    cfg.selected_swatch = regions["selected_swatch"]
    cfg.palette = regions["palette"]
    cfg.marker = None
    return cfg
