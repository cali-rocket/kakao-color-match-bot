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
    폭(~일정)으로 후보를 좁히고, 중앙의 흰 마커 존재로 아이콘/썸네일 등 오검출을 배제."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = (hsv[:, :, 1] > 60).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    marked, plain = [], []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if not (280 < w < 380 and 90 < h < 320):   # 팔레트 폭은 일정, 높이는 가변
            continue
        cen = bgr[y + h // 5:y + 4 * h // 5, x + w // 3:x + 2 * w // 3]
        if _has_marker(cen):
            # 중앙 흰 마커 = 팔레트의 확실한 신호. 색 범위가 좁아도(노랑-초록 등) 채택.
            marked.append((x, y, w, h))
        else:
            # 마커 없는 후보는 넓은 hue 범위일 때만 폴백 대상으로(decoy 배제)
            sub = hsv[y:y + h, x:x + w]
            hues = sub[:, :, 0][sub[:, :, 1] > 60]
            if hues.size and int(np.ptp(hues)) >= 90:
                plain.append((x, y, w, h))
    pool = marked or plain   # 마커 있는 것 우선; 없을 때만 넓은-hue 폴백
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


def _locate_in_rect(full, ox, oy, rect):
    l, t, r, b = rect
    x0, y0 = max(0, l - ox), max(0, t - oy)
    x1, y1 = min(full.shape[1], r - ox), min(full.shape[0], b - oy)
    if x1 - x0 < 150 or y1 - y0 < 150:
        return None
    return locate(full[y0:y1, x0:x1], ox + x0, oy + y0)


def locate_live():
    """게임을 검출한다. 우선순위: (1) 커서 아래 창 (2) 활성 창 (3) 전체 화면.
    사용자가 게임 창 위에 마우스를 올려두면 그 창 안에서만 찾으므로 다른 창의
    컬러풀한 요소를 오검출하지 않는다. dict 또는 None."""
    import mss
    from .input_win import window_under_cursor, foreground_rect
    with mss.mss() as sct:
        m = sct.monitors[1]
        full = np.asarray(sct.grab(m))[:, :, :3]
        ox, oy = m["left"], m["top"]
    wc = window_under_cursor()
    if wc is not None:
        res = _locate_in_rect(full, ox, oy, wc[1])
        if res is not None:
            return res
    fr = foreground_rect()
    if fr is not None:
        res = _locate_in_rect(full, ox, oy, fr)
        if res is not None:
            return res
    return locate(full, ox, oy)


def apply_to(cfg, regions):
    """검출된 regions를 cfg에 반영. C는 팔레트 기하중심 사용(marker=None)."""
    cfg.answer_swatch = regions["answer_swatch"]
    cfg.selected_swatch = regions["selected_swatch"]
    cfg.palette = regions["palette"]
    cfg.marker = None
    return cfg
