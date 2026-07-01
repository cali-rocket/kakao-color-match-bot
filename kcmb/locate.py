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


def find_band(bgr):
    """팔레트의 채도 그라데이션 밴드 (x,y,w,h) 반환, 없으면 None."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = (hsv[:, :, 1] > 60).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if not (280 < w < 380 and 60 < h < 300 and w / h >= 1.4):
            continue
        sub = hsv[y:y + h, x:x + w]
        hues = sub[:, :, 0][sub[:, :, 1] > 60]
        if hues.size == 0 or int(np.ptp(hues)) < 70:   # wide hue variety = gradient
            continue
        area = w * h
        if best is None or y < best[1] - 5 or (abs(y - best[1]) <= 5 and area > best[4]):
            best = (x, y, w, h, area)   # prefer the topmost / largest band
    return None if best is None else best[:4]


def locate(bgr, ox=0, oy=0):
    """전체화면 BGR에서 게임 영역을 검출. {answer_swatch, selected_swatch, palette} 또는 None."""
    b = find_band(bgr)
    if b is None:
        return None
    bx, by, bw, bh = b
    ph = int(bw * _PAL_HFRAC)
    return {
        "answer_swatch": Region(ox + bx + _ANS_DX, oy + by + _SW_DY, _SW, _SW),
        "selected_swatch": Region(ox + bx + _SEL_DX, oy + by + _SW_DY, _SW, _SW),
        "palette": Region(ox + bx, oy + by + _PAL_DY, bw, ph),
    }


def locate_live():
    """주 모니터를 잡아 게임 영역을 검출. dict 또는 None."""
    import mss
    with mss.mss() as sct:
        m = sct.monitors[1]
        img = np.asarray(sct.grab(m))[:, :, :3]
        return locate(img, m["left"], m["top"])


def apply_to(cfg, regions):
    """검출된 regions를 cfg에 반영(마커는 팔레트 중심 사용)."""
    cfg.answer_swatch = regions["answer_swatch"]
    cfg.selected_swatch = regions["selected_swatch"]
    cfg.palette = regions["palette"]
    cfg.marker = None
    return cfg
