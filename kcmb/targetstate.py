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
