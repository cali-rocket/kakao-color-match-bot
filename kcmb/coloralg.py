import numpy as np
import cv2


def color_dist(a, b) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    return float(np.sqrt(np.sum((a - b) ** 2)))


def swatch_color(img_bgr):
    """중앙 50% 크롭의 채널별 median = 대표색, 채널별 MAD 평균 = 산포."""
    h, w = img_bgr.shape[:2]
    y0, y1 = h // 4, h - h // 4
    x0, x1 = w // 4, w - w // 4
    crop = img_bgr[y0:y1, x0:x1].reshape(-1, 3).astype(np.float64)
    med = np.median(crop, axis=0)
    mad = float(np.mean(np.median(np.abs(crop - med), axis=0)))
    return med.astype(int), mad


def find_nearest_cluster(palette_bgr, target_bgr, eps):
    """정답색과 최근접 픽셀 집합의 최대 연결성분 중심점 (col,row)과 min_dist."""
    target = np.asarray(target_bgr, dtype=np.int32)
    pal = palette_bgr.astype(np.int32)
    dist2 = ((pal - target) ** 2).sum(axis=2)
    min_d2 = float(dist2.min())
    min_dist = float(np.sqrt(min_d2))
    thresh = (np.sqrt(min_d2) + eps) ** 2
    mask = (dist2 <= thresh).astype(np.uint8)
    num, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    best_label, best_area = -1, -1
    for lbl in range(1, num):  # 0 = background
        area = int(stats[lbl, cv2.CC_STAT_AREA])
        if area > best_area:
            best_area, best_label = area, lbl
    if best_label < 0:
        row, col = np.unravel_index(int(dist2.argmin()), dist2.shape)
        return int(col), int(row), min_dist
    cx, cy = centroids[best_label]
    return int(round(cx)), int(round(cy)), min_dist
