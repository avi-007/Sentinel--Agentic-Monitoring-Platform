"""Injects occasional, self-reverting anomalies on top of a host's normal
signal: two kinds, both perturbing latency_ms and error_rate_pct.

- spike: a short (1-2 tick) multiplicative jump that decays back to baseline.
- ramp: a gradual multiplicative climb from 1.0x up to a peak (2.0-3.5x) over
  40-80 ticks, then reverts instantly — enough of a slow trend for the
  detector's early-warning forecast (trend_forecast.py) to have something
  real to extrapolate, distinct from spike's abrupt jump.

Each host has independent injection rolls gated by `injection_rate` per
tick, plus a cooldown after any anomaly so events don't overlap or chain
back-to-back. Kind (spike vs ramp) is chosen ~50/50 on the same roll — no
second independent probability.
"""

from __future__ import annotations

import numpy as np

ANOMALY_METRICS = ("latency_ms", "error_rate_pct")


class _ActiveSpike:
    def __init__(self, rng: np.random.Generator):
        # 1-2 tick jump: peak, then a partial-decay tick before reverting.
        peak = rng.uniform(2.5, 4.5)
        self.multipliers = [peak, 1.0 + (peak - 1.0) * 0.35]
        self.tick_index = 0

    def apply(self, metrics: dict[str, float]) -> tuple[dict[str, float], bool]:
        """Returns (perturbed_metrics, is_finished)."""
        out = dict(metrics)
        mult = self.multipliers[self.tick_index]
        for m in ANOMALY_METRICS:
            out[m] = metrics[m] * mult
        self.tick_index += 1
        return out, self.tick_index >= len(self.multipliers)


class _ActiveRamp:
    def __init__(self, rng: np.random.Generator):
        self.duration = int(rng.integers(40, 81))
        self.peak = rng.uniform(2.0, 3.5)
        self.tick_index = 0

    def apply(self, metrics: dict[str, float]) -> tuple[dict[str, float], bool]:
        """Returns (perturbed_metrics, is_finished). Reverts instantly after
        `duration` ticks — no gradual decay tail like spike has."""
        out = dict(metrics)
        frac = min((self.tick_index + 1) / self.duration, 1.0)
        mult = 1.0 + (self.peak - 1.0) * frac
        for m in ANOMALY_METRICS:
            out[m] = metrics[m] * mult
        self.tick_index += 1
        return out, self.tick_index >= self.duration


_KIND_TO_CLASS = {"spike": _ActiveSpike, "ramp": _ActiveRamp}


class AnomalyInjector:
    def __init__(self, injection_rate: float, cooldown_ticks: int, seed: int):
        self.injection_rate = injection_rate
        self.cooldown_ticks = cooldown_ticks
        self.rng = np.random.default_rng(seed)
        self._active: _ActiveSpike | _ActiveRamp | None = None
        self._active_kind: str | None = None
        self._cooldown_remaining = 0

    def maybe_inject(self, base_metrics: dict[str, float]) -> tuple[dict[str, float], dict]:
        """Returns (possibly-perturbed metrics, injected_anomaly info dict)."""
        if self._active is not None:
            perturbed, finished = self._active.apply(base_metrics)
            kind = self._active_kind
            if finished:
                self._active = None
                self._active_kind = None
                self._cooldown_remaining = self.cooldown_ticks
            return perturbed, {"active": True, "type": kind}

        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            return base_metrics, {"active": False, "type": None}

        if self.rng.random() < self.injection_rate:
            kind = "spike" if self.rng.random() < 0.5 else "ramp"
            self._active = _KIND_TO_CLASS[kind](self.rng)
            self._active_kind = kind
            perturbed, finished = self._active.apply(base_metrics)
            if finished:
                self._active = None
                self._active_kind = None
                self._cooldown_remaining = self.cooldown_ticks
            return perturbed, {"active": True, "type": kind}

        return base_metrics, {"active": False, "type": None}
