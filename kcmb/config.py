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
