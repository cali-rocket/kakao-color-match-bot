# 카카오톡 색 맞추기 봇 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 카카오톡 PC 미니게임 "정답과 같은 색 찾기"를 3초 안에 자동으로 푸는 봇을 만든다.

**Architecture:** 화면을 캡처해 정답 색을 읽고, 팔레트에서 그 색의 위치를 찾아, 중앙 고정 마커로 끌어오도록 마우스를 드래그한다. 드래그 이득(gain)과 부호는 매 라운드 부호 탐침으로 실측하고, 감쇠 비례 폐루프(observe→drag→observe)로 `선택` 색을 정답에 수렴시킨다. 순수 로직(색·제어·상태)과 I/O(캡처·입력·단축키)를 분리해 순수 부분은 TDD로 검증한다.

**Tech Stack:** Python 3.9+, numpy, opencv-python, mss, keyboard, pytest (dev). Windows 전용.

## Global Constraints

- 플랫폼: Windows 11. `ctypes.windll` 사용(비-Windows에서 import 시 실패 허용).
- 파이썬: 3.9+ (타입힌트/numpy).
- 의존성: `mss`, `numpy`, `opencv-python`, `keyboard`; dev: `pytest`.
- 화면 점(좌표)은 전부 `np.ndarray([x, y], dtype=float)`; 색은 `np.ndarray([b, g, r])` (BGR).
- 색 거리 = BGR 유클리드 `color_dist`. 모든 색 임계값은 0~441 기준.
- `config.json`, `debug/`는 git 무시(이미 `.gitignore`에 있음).
- 소스 패키지는 `kcmb/`, 테스트는 `tests/`. 진입점은 `python -m kcmb.<name>`.
- 각 진입점(`calibrate`,`probe`,`main`) **첫 줄**에서 `dpi.set_dpi_aware()` 호출.
- 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- 각 태스크 끝에 커밋.

---

## File Structure

```
kcmb/
├── __init__.py
├── config.py       # Region/Config 데이터클래스, load/save, is_calibrated
├── dpi.py          # set_dpi_aware() 3단계 폴백
├── capture.py      # grab(region)->BGR ndarray, to_bgr 헬퍼
├── coloralg.py     # color_dist, swatch_color, find_nearest_cluster
├── controller.py   # is_matched, probe_plan, estimate_gain, update_gain, plan_drag, helpers
├── targetstate.py  # TargetState.observe (정답색 디바운스 → NEW_TARGET)
├── input_win.py    # to_absolute(순수) + SendInput move/drag/settle_swatch (I/O)
├── hotkeys.py      # F8 arm 토글, F9 종료
├── calibrate.py    # 진입점: selectROI 캘리브레이션
├── probe.py        # 진입점: 상호작용 탐침 (부호/팬/플링/잠금 실측)
└── main.py         # 진입점: 폐루프 배선
tests/
├── __init__.py
├── test_config.py
├── test_coloralg.py
├── test_controller.py
├── test_targetstate.py
├── test_capture.py
└── test_input_win.py
```

---

### Task 1: 프로젝트 스캐폴드 & 개발 도구

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `kcmb/__init__.py`, `tests/__init__.py`, `tests/test_smoke.py`

**Interfaces:**
- Produces: 설치 가능한 패키지 `kcmb`, 실행 가능한 `pytest`.

- [ ] **Step 1: 의존성 파일 작성**

`requirements.txt`:
```
mss>=9.0.1
numpy>=1.24
opencv-python>=4.8
keyboard>=0.13.5
```
`requirements-dev.txt`:
```
-r requirements.txt
pytest>=7.4
```
`pytest.ini`:
```
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 2: 패키지/테스트 초기 파일**

`kcmb/__init__.py`: (빈 파일)
`tests/__init__.py`: (빈 파일)
`tests/test_smoke.py`:
```python
def test_smoke():
    import kcmb
    assert kcmb is not None
```

- [ ] **Step 3: 가상환경 + 설치 + 테스트**

Run:
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest -q
```
Expected: `1 passed`.

- [ ] **Step 4: 커밋**
```bash
git add requirements.txt requirements-dev.txt pytest.ini kcmb tests
git commit -m "chore: scaffold kcmb package and pytest"
```

---

### Task 2: `config.py` — 설정 로드/저장/검증

**Files:**
- Create: `kcmb/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `Region(left,top,width,height)` with `.center()->np.ndarray`, `.right`, `.bottom`
  - `Config` 데이터클래스 (스펙 §6 필드 전부) with `.marker_point -> Optional[np.ndarray]`
  - `load(path='config.json')->Config`, `save(cfg, path='config.json')`, `is_calibrated(cfg)->bool`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_config.py`:
```python
import numpy as np
from kcmb import config as C

def test_region_center():
    r = C.Region(left=10, top=20, width=100, height=80)
    assert np.allclose(r.center(), [60, 60])
    assert r.right == 110 and r.bottom == 100

def test_defaults_not_calibrated():
    cfg = C.Config()
    assert C.is_calibrated(cfg) is False

def test_is_calibrated_true_when_regions_set():
    cfg = C.Config(
        answer_swatch=C.Region(1, 1, 10, 10),
        selected_swatch=C.Region(1, 1, 10, 10),
        palette=C.Region(1, 1, 100, 100),
    )
    assert C.is_calibrated(cfg) is True

def test_marker_point_none_and_set():
    assert C.Config().marker_point is None
    cfg = C.Config(marker=[5, 7])
    assert np.allclose(cfg.marker_point, [5, 7])

def test_save_load_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    cfg = C.Config(palette=C.Region(2, 3, 40, 50), marker=[10, 11], match_tolerance=9)
    C.save(cfg, str(p))
    got = C.load(str(p))
    assert got.palette.width == 40 and got.palette.top == 3
    assert got.marker == [10, 11]
    assert got.match_tolerance == 9

def test_load_missing_returns_defaults(tmp_path):
    got = C.load(str(tmp_path / "nope.json"))
    assert C.is_calibrated(got) is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -q`
Expected: FAIL (`ModuleNotFoundError` / attribute errors).

- [ ] **Step 3: 구현**

`kcmb/config.py`:
```python
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional, List

import numpy as np


@dataclass
class Region:
    left: int = 0
    top: int = 0
    width: int = 0
    height: int = 0

    def center(self) -> np.ndarray:
        return np.array([self.left + self.width / 2.0,
                         self.top + self.height / 2.0], dtype=float)

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


@dataclass
class Config:
    answer_swatch: Region = field(default_factory=Region)
    selected_swatch: Region = field(default_factory=Region)
    palette: Region = field(default_factory=Region)
    marker: Optional[List[int]] = None

    stability_tolerance: float = 6
    stability_frames: int = 2
    dispersion_tolerance: float = 12
    new_round_threshold: float = 40
    match_tolerance: float = 10
    cluster_eps: float = 6

    gain_lambda: float = 0.5
    gain_min: float = 0.05
    gain_max: float = 20
    gain_smooth_alpha: float = 0.5
    probe_frac: float = 0.12
    probe_min_shift_px: float = 4
    move_floor_px: float = 15
    max_drag_frac: float = 0.6
    e_deadband_px: float = 4
    stall_no_improve_n: int = 3
    improve_margin: float = 3
    round_budget_ms: int = 2800

    loop_delay_ms: int = 15
    drag_pre_dwell_ms: int = 20
    drag_steps: int = 20
    drag_step_ms: int = 9
    drag_end_dwell_ms: int = 40
    settle_poll_ms: int = 15
    settle_stable_reads: int = 2
    settle_cap_ms: int = 120

    @property
    def marker_point(self) -> Optional[np.ndarray]:
        return None if self.marker is None else np.array(self.marker, dtype=float)


_REGION_FIELDS = ("answer_swatch", "selected_swatch", "palette")


def from_dict(d: dict) -> Config:
    cfg = Config()
    for k, v in d.items():
        if k in _REGION_FIELDS and isinstance(v, dict):
            setattr(cfg, k, Region(**v))
        elif hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg


def load(path: str = "config.json") -> Config:
    if not os.path.exists(path):
        return Config()
    with open(path, "r", encoding="utf-8") as f:
        return from_dict(json.load(f))


def save(cfg: Config, path: str = "config.json") -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=2, ensure_ascii=False)


def is_calibrated(cfg: Config) -> bool:
    return all(r.width > 0 and r.height > 0
               for r in (cfg.answer_swatch, cfg.selected_swatch, cfg.palette))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: 커밋**
```bash
git add kcmb/config.py tests/test_config.py
git commit -m "feat: config load/save/validate with Region and defaults"
```

---

### Task 3: `coloralg.py` — 색 거리 / 대표색 / 최근접 클러스터

**Files:**
- Create: `kcmb/coloralg.py`, `tests/test_coloralg.py`

**Interfaces:**
- Produces:
  - `color_dist(a, b) -> float`
  - `swatch_color(img_bgr) -> (np.ndarray[b,g,r] int, dispersion float)`
  - `find_nearest_cluster(palette_bgr, target_bgr, eps) -> (col int, row int, min_dist float)`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_coloralg.py`:
```python
import numpy as np
from kcmb import coloralg as A

def test_color_dist_basic():
    assert A.color_dist([0, 0, 0], [0, 0, 0]) == 0.0
    assert abs(A.color_dist([0, 0, 0], [0, 0, 255]) - 255.0) < 1e-6
    assert abs(A.color_dist([0, 0, 0], [255, 255, 255]) - (255 * 3 ** 0.5)) < 1e-6

def test_swatch_color_flat():
    img = np.full((40, 40, 3), (10, 20, 30), dtype=np.uint8)
    color, disp = A.swatch_color(img)
    assert np.array_equal(color, [10, 20, 30])
    assert disp == 0.0

def test_swatch_color_ignores_border():
    # border is noise, center is uniform (12,34,56)
    img = np.zeros((40, 40, 3), dtype=np.uint8)
    img[:] = (200, 200, 200)
    img[10:30, 10:30] = (12, 34, 56)  # center 50% region
    color, _ = A.swatch_color(img)
    assert np.array_equal(color, [12, 34, 56])

def test_swatch_color_dispersion_flags_mixed():
    img = np.zeros((40, 40, 3), dtype=np.uint8)
    img[10:20, 10:30] = (0, 0, 0)
    img[20:30, 10:30] = (255, 255, 255)  # half/half center -> high dispersion
    _, disp = A.swatch_color(img)
    assert disp > 50

def test_find_nearest_cluster_locates_target():
    pal = np.zeros((100, 200, 3), dtype=np.uint8)
    pal[:] = (0, 0, 0)
    # a 10x10 block of target color at cols 150..160, rows 40..50
    pal[40:50, 150:160] = (0, 200, 0)
    col, row, d = A.find_nearest_cluster(pal, [0, 200, 0], eps=6)
    assert 150 <= col <= 160 and 40 <= row <= 50
    assert d < 1.0

def test_find_nearest_cluster_robust_to_single_noise_pixel():
    pal = np.full((60, 60, 3), (30, 30, 30), dtype=np.uint8)
    pal[0, 0] = (0, 201, 0)                 # lone noisy near-match at corner
    pal[25:35, 25:35] = (0, 200, 0)         # the real cluster near center
    col, row, _ = A.find_nearest_cluster(pal, [0, 200, 0], eps=6)
    assert 24 <= col <= 35 and 24 <= row <= 35  # centroid of the cluster, not the corner
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/Scripts/python -m pytest tests/test_coloralg.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: 구현**

`kcmb/coloralg.py`:
```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/Scripts/python -m pytest tests/test_coloralg.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: 커밋**
```bash
git add kcmb/coloralg.py tests/test_coloralg.py
git commit -m "feat: color distance, swatch color, nearest-cluster locator"
```

---

### Task 4: `controller.py` — 부호 탐침 + 감쇠 비례 제어 (+ 폐루프 시뮬레이션)

**Files:**
- Create: `kcmb/controller.py`, `tests/test_controller.py`

**Interfaces:**
- Consumes: `coloralg.color_dist`, `config.Region`, `config.Config`.
- Produces:
  - `is_matched(cur, target, tol) -> bool`
  - `unit(v) -> np.ndarray`
  - `palette_dim(region) -> float`, `clamp_point(pt, region) -> np.ndarray`
  - `probe_plan(C, ehat, probe_frac, region) -> (start, end)`
  - `estimate_gain(measured_shift, cursor_move, gain_min, gain_max) -> Optional[float]`
  - `update_gain(gain, cursor_move, measured_shift, min_dist, cfg) -> float`
  - `plan_drag(e, gain, C, region, cfg) -> Optional[(start, end)]`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_controller.py`:
```python
import numpy as np
from kcmb import controller as K
from kcmb.config import Config, Region

PAL = Region(left=0, top=0, width=200, height=200)
C = PAL.center()  # [100, 100]

def test_is_matched():
    assert K.is_matched([10, 10, 10], [12, 11, 10], tol=10) is True
    assert K.is_matched([0, 0, 0], [0, 0, 255], tol=10) is False

def test_plan_drag_direction_pans_target_to_center():
    # target is to the RIGHT of center (e.x > 0): cursor must move LEFT (v.x < 0) for k>0
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
    # field moves SAME direction as cursor -> positive gain
    g = K.estimate_gain(measured_shift=[20, 0], cursor_move=[20, 0], gain_min=0.05, gain_max=20)
    assert abs(g - 1.0) < 1e-6
    # field moves OPPOSITE -> negative gain
    g2 = K.estimate_gain(measured_shift=[-10, 0], cursor_move=[20, 0], gain_min=0.05, gain_max=20)
    assert g2 < 0

def test_update_gain_gates_on_cluster_jump():
    cfg = Config()
    # shift perpendicular to move (a cluster jump) -> gain unchanged
    g = K.update_gain(1.0, cursor_move=[40, 0], measured_shift=[0, 40], min_dist=0.0, cfg=cfg)
    assert g == 1.0

def test_update_gain_gates_on_min_dist():
    cfg = Config()  # cluster_eps=6
    g = K.update_gain(1.0, cursor_move=[40, 0], measured_shift=[40, 0], min_dist=99.0, cfg=cfg)
    assert g == 1.0

def _simulate(k_true, e0, cfg, max_steps=8):
    """가상 색판: 드래그 커서이동 v에 대해 타깃 위치가 P += k_true*v 만큼 이동.
    center C에 도달(|e|<=deadband)하면 성공. 컨트롤러가 수렴시키는지 검증."""
    P = C + np.array(e0, dtype=float)
    gain = None
    prev_P = prev_v = None
    traj = [np.linalg.norm(P - C)]
    for _ in range(max_steps):
        e = P - C
        if np.linalg.norm(e) <= cfg.e_deadband_px:
            return True, traj
        if gain is None:  # 부호 탐침
            start, end = K.probe_plan(C, K.unit(-e), cfg.probe_frac, PAL)
            v = end - start
            P = P + k_true * v
            gain = K.estimate_gain(P - (P - k_true * v), v, cfg.gain_min, cfg.gain_max)
            prev_P, prev_v = P, v
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
    assert ok, traj  # sign-probe must capture the negative sign

def test_closed_loop_does_not_diverge_large_gain():
    cfg = Config()
    ok, traj = _simulate(k_true=3.0, e0=[60, 0], cfg=cfg)
    assert max(traj) < 400  # bounded, no runaway
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/Scripts/python -m pytest tests/test_controller.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: 구현**

`kcmb/controller.py`:
```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/Scripts/python -m pytest tests/test_controller.py -q`
Expected: PASS (all). 특히 `test_closed_loop_converges_wrong_sign_gain`가 부호 탐침을 검증.

- [ ] **Step 5: 커밋**
```bash
git add kcmb/controller.py tests/test_controller.py
git commit -m "feat: sign-probe + damped proportional drag controller with closed-loop sim tests"
```

---

### Task 5: `targetstate.py` — 정답색 디바운스 / 라운드 감지

**Files:**
- Create: `kcmb/targetstate.py`, `tests/test_targetstate.py`

**Interfaces:**
- Consumes: `coloralg.color_dist`, `config.Config`.
- Produces: `TargetState(cfg)` with `.target`, `.observe(answer_color, dispersion) -> Optional[str]` ('NEW_TARGET'|None).

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_targetstate.py`:
```python
import numpy as np
from kcmb.targetstate import TargetState
from kcmb.config import Config

def feed(ts, color, disp=0.0, n=1):
    ev = None
    for _ in range(n):
        ev = ts.observe(np.array(color, dtype=float), disp)
    return ev

def test_first_round_fires_after_stable_frames():
    ts = TargetState(Config())  # stability_frames=2
    assert feed(ts, [10, 20, 30]) is None          # frame 1
    assert feed(ts, [10, 20, 30]) is None           # frame 2 (count=1)
    assert feed(ts, [10, 20, 30]) == 'NEW_TARGET'   # frame 3 (count=2)
    assert np.allclose(ts.target, [10, 20, 30])

def test_no_duplicate_for_same_target():
    ts = TargetState(Config())
    feed(ts, [10, 20, 30], n=3)
    assert feed(ts, [10, 20, 30], n=5) is None      # same target, no refire

def test_new_target_after_change():
    ts = TargetState(Config())
    feed(ts, [10, 20, 30], n=3)
    assert feed(ts, [200, 10, 10], n=3) == 'NEW_TARGET'

def test_dispersion_frame_rejected():
    ts = TargetState(Config())  # dispersion_tolerance=12
    assert feed(ts, [10, 20, 30], disp=50.0, n=5) is None  # transition frames never stabilize

def test_similar_within_threshold_not_new_round():
    ts = TargetState(Config())  # new_round_threshold=40
    feed(ts, [10, 20, 30], n=3)
    # differs by ~10 (< 40): treated as same round -> no refire
    assert feed(ts, [16, 24, 33], n=5) is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/Scripts/python -m pytest tests/test_targetstate.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: 구현**

`kcmb/targetstate.py`:
```python
from typing import Optional

import numpy as np

from .coloralg import color_dist


class TargetState:
    def __init__(self, cfg):
        self.cfg = cfg
        self.target: Optional[np.ndarray] = None
        self.prev: Optional[np.ndarray] = None
        self.stable_count = 0

    def observe(self, answer_color, dispersion) -> Optional[str]:
        cfg = self.cfg
        ac = np.asarray(answer_color, dtype=np.float64)
        if dispersion > cfg.dispersion_tolerance:
            self.stable_count = 0
            self.prev = ac
            return None
        if self.prev is not None and color_dist(ac, self.prev) <= cfg.stability_tolerance:
            self.stable_count += 1
        else:
            self.stable_count = 0
        self.prev = ac
        if self.stable_count >= cfg.stability_frames:
            if self.target is None or color_dist(ac, self.target) > cfg.new_round_threshold:
                self.target = ac
                return "NEW_TARGET"
        return None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/Scripts/python -m pytest tests/test_targetstate.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: 커밋**
```bash
git add kcmb/targetstate.py tests/test_targetstate.py
git commit -m "feat: target-color debounce and round-change detection"
```

---

### Task 6: `dpi.py` + `capture.py` — DPI 설정과 화면 캡처

**Files:**
- Create: `kcmb/dpi.py`, `kcmb/capture.py`, `tests/test_capture.py`

**Interfaces:**
- Produces:
  - `dpi.set_dpi_aware() -> str` ('per_monitor_v2'|'per_monitor_v1'|'system'|'none')
  - `capture.to_bgr(bgra_ndarray) -> ndarray` (알파 제거, 3채널)
  - `capture.grab(region) -> np.ndarray` (BGR, mss)

- [ ] **Step 1: 실패 테스트 작성** (순수 부분 `to_bgr`만 단위 테스트)

`tests/test_capture.py`:
```python
import numpy as np
from kcmb import capture

def test_to_bgr_drops_alpha():
    bgra = np.zeros((5, 7, 4), dtype=np.uint8)
    bgra[..., 0] = 1; bgra[..., 1] = 2; bgra[..., 2] = 3; bgra[..., 3] = 255
    bgr = capture.to_bgr(bgra)
    assert bgr.shape == (5, 7, 3)
    assert np.array_equal(bgr[0, 0], [1, 2, 3])

def test_dpi_set_returns_string():
    from kcmb import dpi
    assert isinstance(dpi.set_dpi_aware(), str)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/Scripts/python -m pytest tests/test_capture.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: 구현**

`kcmb/dpi.py`:
```python
import ctypes


def set_dpi_aware() -> str:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return "per_monitor_v2"
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per_monitor_v1"
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return "system"
    except (AttributeError, OSError):
        pass
    return "none"
```

`kcmb/capture.py`:
```python
import numpy as np
import mss

_sct = None


def _grabber():
    global _sct
    if _sct is None:
        _sct = mss.mss()
    return _sct


def to_bgr(bgra) -> np.ndarray:
    arr = np.asarray(bgra)
    return arr[:, :, :3]


def grab(region) -> np.ndarray:
    mon = {"left": int(region.left), "top": int(region.top),
           "width": int(region.width), "height": int(region.height)}
    raw = _grabber().grab(mon)
    return to_bgr(np.asarray(raw))
```

- [ ] **Step 4: 테스트 통과 + 수동 캡처 확인**

Run: `.venv/Scripts/python -m pytest tests/test_capture.py -q`
Expected: PASS (2 passed).

수동 확인 (화면 필요):
```bash
.venv/Scripts/python -c "from kcmb import dpi,capture; from kcmb.config import Region; dpi.set_dpi_aware(); print(capture.grab(Region(0,0,50,50)).shape)"
```
Expected: `(50, 50, 3)`.

- [ ] **Step 5: 커밋**
```bash
git add kcmb/dpi.py kcmb/capture.py tests/test_capture.py
git commit -m "feat: DPI awareness and mss BGR screen capture"
```

---

### Task 7: `input_win.py` — 좌표 정규화(순수) + SendInput 드래그/settle(I/O)

**Files:**
- Create: `kcmb/input_win.py`, `tests/test_input_win.py`

**Interfaces:**
- Consumes: `coloralg.swatch_color`.
- Produces:
  - `to_absolute(px, py, vx, vy, vcx, vcy) -> (nx, ny)` (순수)
  - `vscreen_metrics() -> (vx, vy, vcx, vcy)` (I/O)
  - `move_abs(pt)`, `left_down_at(pt)`, `left_up_at(pt)`
  - `drag(start, end, cfg)` — 모션 프로파일(pre-dwell/ease/종단 dwell)
  - `settle_swatch(grab_fn, region, cfg) -> np.ndarray`

- [ ] **Step 1: 실패 테스트 작성** (순수 `to_absolute` + `settle_swatch`를 fake로)

`tests/test_input_win.py`:
```python
import numpy as np
from kcmb import input_win as I
from kcmb.config import Config, Region

def test_to_absolute_corners():
    # virtual screen origin (0,0), size 1920x1080
    assert I.to_absolute(0, 0, 0, 0, 1920, 1080) == (0, 0)
    nx, ny = I.to_absolute(1919, 1079, 0, 0, 1920, 1080)
    assert nx == 65535 and ny == 65535

def test_to_absolute_negative_origin():
    # left monitor starting at -1920
    nx, _ = I.to_absolute(-1920, 0, -1920, 0, 3840, 1080)
    assert nx == 0

def test_settle_swatch_returns_when_stable():
    cfg = Config()  # settle_stable_reads=2, stability_tolerance=6
    frames = [np.full((8, 8, 3), (5, 5, 5), np.uint8),
              np.full((8, 8, 3), (100, 100, 100), np.uint8),  # still moving
              np.full((8, 8, 3), (100, 100, 100), np.uint8),
              np.full((8, 8, 3), (100, 100, 100), np.uint8)]
    it = iter(frames)
    def fake_grab(_region):
        return next(it, frames[-1])
    color = I.settle_swatch(fake_grab, Region(0, 0, 8, 8), cfg)
    assert np.array_equal(color, [100, 100, 100])
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/Scripts/python -m pytest tests/test_input_win.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: 구현**

`kcmb/input_win.py`:
```python
import ctypes
import time
from ctypes import wintypes

import numpy as np

from .coloralg import swatch_color

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
    # 드래그 임계 통과용 1~2px 미소 이동
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
    from .coloralg import color_dist
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `.venv/Scripts/python -m pytest tests/test_input_win.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: 커밋**
```bash
git add kcmb/input_win.py tests/test_input_win.py
git commit -m "feat: virtual-desktop SendInput drag with fling-safe profile and settle gate"
```

---

### Task 8: `hotkeys.py` — F8 arm 토글 / F9 종료

**Files:**
- Create: `kcmb/hotkeys.py`

**Interfaces:**
- Produces: `HotkeyState` with `.armed: bool`, `.should_quit: bool`; `install(state)` (F8 토글, F9 종료).

- [ ] **Step 1: 구현** (전역 훅은 단위 테스트 불가 — 상태 객체만 분리해 로직 검증 가능)

`kcmb/hotkeys.py`:
```python
import keyboard


class HotkeyState:
    def __init__(self):
        self.armed = False
        self.should_quit = False

    def toggle(self):
        self.armed = not self.armed
        print(f"[hotkey] armed = {self.armed}")

    def quit(self):
        self.should_quit = True
        print("[hotkey] quit")


def install(state: HotkeyState):
    keyboard.add_hotkey("f8", state.toggle)
    keyboard.add_hotkey("f9", state.quit)
    return state
```

- [ ] **Step 2: 수동 확인**
```bash
.venv/Scripts/python -c "import time; from kcmb.hotkeys import HotkeyState, install; s=install(HotkeyState()); print('press F8 a few times, F9 to quit'); [time.sleep(0.1) for _ in range(1)] "
```
(대화형으로 F8/F9 눌러 콘솔 출력 확인 — 통합 테스트 시 게임 포커스 상태에서도 먹는지 확인.)

- [ ] **Step 3: 커밋**
```bash
git add kcmb/hotkeys.py
git commit -m "feat: F8 arm toggle / F9 quit global hotkeys"
```

---

### Task 9: `probe.py` — 상호작용 탐침 (실측)

**Files:**
- Create: `kcmb/probe.py`

**Interfaces:**
- Consumes: `dpi`, `config`, `capture`, `input_win`, `coloralg`, `hotkeys`.
- Produces: 실행형 스크립트. 한 번의 드래그 전/후 `선택` 색·팔레트 중앙색을 로그해 부호/팬/플링/잠금을 사람이 판단.

- [ ] **Step 1: 구현**

`kcmb/probe.py`:
```python
"""상호작용 탐침: config가 있어야 함(calibrate 먼저). F8로 arm 후 한 번 드래그.
드래그 전/후 선택색을 비교해 (1) 색판이 반응하는지 (2) 커서와 같은/반대 방향인지
(3) 놓은 뒤 계속 움직이는지(플링) 를 사람이 확인한다."""
import time

import numpy as np

from . import dpi, capture, input_win, config as C
from .coloralg import swatch_color, color_dist


def main():
    dpi.set_dpi_aware()
    cfg = C.load()
    if not C.is_calibrated(cfg):
        print("calibrate 먼저: python -m kcmb.calibrate")
        return
    Cpt = cfg.marker_point if cfg.marker_point is not None else cfg.palette.center()
    print("F8로 게임 창을 활성화한 뒤, 3초 후 오른쪽으로 고정 드래그를 1회 실행합니다.")
    time.sleep(3)

    before, _ = swatch_color(capture.grab(cfg.selected_swatch))
    dim = min(cfg.palette.width, cfg.palette.height)
    start = np.array([Cpt[0] - 0.15 * dim, Cpt[1]])
    end = np.array([Cpt[0] + 0.15 * dim, Cpt[1]])  # 커서 오른쪽 이동
    print(f"drag {start} -> {end} (커서 +x)")
    input_win.drag(start, end, cfg)

    time.sleep(0.15)
    after1, _ = swatch_color(capture.grab(cfg.selected_swatch))
    time.sleep(0.3)
    after2, _ = swatch_color(capture.grab(cfg.selected_swatch))

    print(f"선택색 before={before} after(+150ms)={after1} after(+450ms)={after2}")
    print(f"변화량 |after1-before| = {color_dist(after1, before):.1f}")
    print(f"놓은 뒤 추가변화(플링) |after2-after1| = {color_dist(after2, after1):.1f}")
    print("→ 변화가 0이면 미반응/잠금. after2!=after1이면 플링(관성) 있음.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 커밋** (실행은 캘리브레이션 후 §실측 단계에서)
```bash
git add kcmb/probe.py
git commit -m "feat: interaction probe to measure drag sign/pan/fling/lock"
```

---

### Task 10: `calibrate.py` — 영역 캘리브레이션

**Files:**
- Create: `kcmb/calibrate.py`

**Interfaces:**
- Consumes: `dpi`, `capture`(mss 직접), `config`, `cv2`.
- Produces: 실행형 스크립트. 정답/선택 스와치 + 팔레트 ROI + 마커점을 지정해 `config.json` 저장.

- [ ] **Step 1: 구현**

`kcmb/calibrate.py`:
```python
"""캘리브레이션: 전체 가상화면을 캡처해 스케일-안전 selectROI로 4개 영역/점을 지정."""
import argparse

import numpy as np
import cv2
import mss

from . import dpi, config as C


def _grab_monitor(index):
    with mss.mss() as sct:
        mon = sct.monitors[index]
        img = np.asarray(sct.grab(mon))[:, :, :3]  # BGR
        return img, mon["left"], mon["top"]


def _select(title, disp_img, scale):
    r = cv2.selectROI(title, disp_img, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow(title)
    x, y, w, h = r
    return int(x / scale), int(y / scale), int(w / scale), int(h / scale)


def _click_point(title, disp_img, scale):
    pt = {}
    def on_mouse(event, x, y, flags, _):
        if event == cv2.EVENT_LBUTTONDOWN:
            pt["x"], pt["y"] = x, y
    cv2.imshow(title, disp_img)
    cv2.setMouseCallback(title, on_mouse)
    while "x" not in pt:
        if cv2.waitKey(20) == 27:  # ESC = skip
            break
    cv2.destroyWindow(title)
    if "x" not in pt:
        return None
    return int(pt["x"] / scale), int(pt["y"] / scale)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--monitor", type=int, default=0, help="0=전체 가상화면")
    args = ap.parse_args()
    dpi.set_dpi_aware()

    img, ox, oy = _grab_monitor(args.monitor)
    h, w = img.shape[:2]
    max_side = 1400
    scale = min(1.0, max_side / max(h, w))
    disp = cv2.resize(img, (int(w * scale), int(h * scale))) if scale < 1.0 else img

    ax, ay, aw, ah = _select("정답 스와치 드래그", disp, scale)
    sx, sy, sw, sh = _select("선택 스와치 드래그", disp, scale)
    px, py, pw, ph = _select("팔레트 영역 드래그", disp, scale)
    mk = _click_point("마커(중앙 피커) 클릭 / ESC=중앙사용", disp, scale)

    cfg = C.load()
    cfg.answer_swatch = C.Region(ox + ax, oy + ay, aw, ah)
    cfg.selected_swatch = C.Region(ox + sx, oy + sy, sw, sh)
    cfg.palette = C.Region(ox + px, oy + py, pw, ph)
    cfg.marker = None if mk is None else [ox + mk[0], oy + mk[1]]
    C.save(cfg)

    print("저장됨 config.json")
    print("정답:", cfg.answer_swatch, "선택:", cfg.selected_swatch)
    print("팔레트:", cfg.palette, "마커:", cfg.marker)
    # 확인용 재캡처
    from . import capture
    from .coloralg import swatch_color
    print("정답 대표색:", swatch_color(capture.grab(cfg.answer_swatch))[0])
    print("선택 대표색:", swatch_color(capture.grab(cfg.selected_swatch))[0])


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 커밋**
```bash
git add kcmb/calibrate.py
git commit -m "feat: scale-safe ROI calibration for swatches, palette, marker"
```

---

### Task 11: `main.py` — 폐루프 배선 + 진입점

**Files:**
- Create: `kcmb/main.py`

**Interfaces:**
- Consumes: 전 모듈.
- Produces: 실행형. `--dry-run` 지원. §5.5 폐루프 배선 + 라운드 타이머/가드/stall/발산.

- [ ] **Step 1: 구현**

`kcmb/main.py`:
```python
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
            continue  # dry-run: 목표 위치만 검증 (폐루프는 시뮬 테스트+실플레이로 검증)

        if gain is None:
            if prev_P is None:
                # 라운드 첫 드래그 = 부호 탐침
                start, end = K.probe_plan(Cpt, K.unit(-e), cfg.probe_frac, cfg.palette)
            else:
                # 부호 탐침의 실측 이동으로 signed gain 확립 (시뮬 테스트와 동일 경로)
                shift = P - prev_P
                if float(np.linalg.norm(shift)) < cfg.probe_min_shift_px:
                    print("[warn] 색판 미반응(probe shift too small) — 라운드 스킵")
                    prev_P = prev_v = None
                    continue  # round_budget으로 자연 종료
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
```

> 배선 설명: 라운드마다 `gain=None`으로 시작 → 첫 드래그는 `probe_plan`(부호 탐침).
> 다음 루프에서 실측 이동 `P-prev_P`로 `estimate_gain`(부호 포함) 확립 후 `plan_drag`.
> 이후 루프는 `update_gain`(게이팅)으로 정련. `test_closed_loop_*` 시뮬레이션과 동일 경로.

- [ ] **Step 2: dry-run 스모크(캘리브레이션 후, 게임 화면에서)**
```bash
.venv/Scripts/python -m kcmb.main --dry-run
```
F8로 arm → 콘솔에 `[round] new target ...`와 `[dry] ... drag ...`가 찍히고
`debug/`에 목표 마킹 이미지가 저장되는지 확인.

- [ ] **Step 3: 커밋**
```bash
git add kcmb/main.py
git commit -m "feat: closed-loop main with dry-run, round timer, stall/divergence guards"
```

---

### Task 12: README 갱신 + 실게임 검증/튜닝

**Files:**
- Modify: `README.md`

- [ ] **Step 1: README에 실행법/권한/검증 절차 추가**

`README.md`의 "상태"와 "동작 개요" 아래에 실행 절차 추가:
```markdown
## 실행 방법 (Windows)

    python -m venv .venv
    .venv/Scripts/python -m pip install -r requirements-dev.txt
    .venv/Scripts/python -m pytest -q          # 단위 테스트

    .venv/Scripts/python -m kcmb.calibrate     # 1) 영역 지정
    .venv/Scripts/python -m kcmb.probe         # 2) 상호작용 실측(부호/팬/플링)
    .venv/Scripts/python -m kcmb.main --dry-run # 3) 목표 좌표 검증
    .venv/Scripts/python -m kcmb.main          # 4) 실플레이 (F8 arm, F9 quit)

- 카카오톡과 봇은 같은 권한(둘 다 비관리자 권장)으로 실행.
- config.json은 기기별 좌표라 커밋하지 않음(.gitignore).
```

- [ ] **Step 2: 실게임 검증 체크리스트 실행** (사람 필요)
  1. `calibrate` 실행 → `config.json` 생성, 대표색 출력이 실제 색과 일치 확인.
  2. `probe` 실행 → 부호(커서 +x에 선택색이 어떻게 변하는지)·플링 유무 기록.
     - 필요 시 `gain_*`, `drag_*` 상수를 §실측값으로 `config.json`에서 조정.
  3. `main --dry-run` → `debug/` 이미지의 십자가 위치가 정답색 위치와 맞는지.
  4. `main` 실드래그 → 1라운드 수렴 확인 → 5라운드 통과 확인.
  5. 게임 포커스 상태에서 F8/F9 동작, post-up drift 확인.

- [ ] **Step 3: 커밋**
```bash
git add README.md
git commit -m "docs: usage, permissions, and real-game verification steps"
```

---

## 실행 순서 요약

1. Task 1–8: 순수/IO 모듈 (TDD, 화면 없이 대부분 검증). 
2. Task 9–11: 진입점(probe/calibrate/main).
3. Task 6 실측: `calibrate` → `probe`로 부호/gain/플링 실측 → 상수 확정.
4. Task 12: `main --dry-run` → 실플레이 검증/튜닝.
