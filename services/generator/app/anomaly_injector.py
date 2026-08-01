"""Injects occasional, self-reverting spikes on top of a host's normal signal.

A spike is a short (1-2 tick) multiplicative jump on latency_ms and
error_rate_pct that decays back to baseline — enough to give the detector
real anomalous events to catch, without needing a taxonomy of incident
shapes to explain.

Each host has independent injection rolls gated by `injection_rate` per
tick, plus a cooldown after any spike so events don't overlap or chain
back-to-back.
"""

from __future__ import annotations

import numpy as np

SPIKE_METRICS = ("latency_ms", "error_rate_pct")


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
        for m in SPIKE_METRICS:
            out[m] = metrics[m] * mult
        self.tick_index += 1
        return out, self.tick_index >= len(self.multipliers)


class AnomalyInjector:
    def __init__(self, injection_rate: float, cooldown_ticks: int, seed: int):
        self.injection_rate = injection_rate
        self.cooldown_ticks = cooldown_ticks
        self.rng = np.random.default_rng(seed)
        self._active: _ActiveSpike | None = None
        self._cooldown_remaining = 0

    def maybe_inject(self, base_metrics: dict[str, float]) -> tuple[dict[str, float], dict]:
        """Returns (possibly-perturbed metrics, injected_anomaly info dict)."""
        if self._active is not None:
            perturbed, finished = self._active.apply(base_metrics)
            if finished:
                self._active = None
                self._cooldown_remaining = self.cooldown_ticks
            return perturbed, {"active": True, "type": "spike"}

        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            return base_metrics, {"active": False, "type": None}

        if self.rng.random() < self.injection_rate:
            self._active = _ActiveSpike(self.rng)
            perturbed, finished = self._active.apply(base_metrics)
            if finished:
                self._active = None
                self._cooldown_remaining = self.cooldown_ticks
            return perturbed, {"active": True, "type": "spike"}

        return base_metrics, {"active": False, "type": None}
