"""Injects occasional, self-reverting anomalies on top of a host's normal
signal. Three archetypes, chosen to look like real incident shapes:

- spike: a short, sharp multiplicative jump (1-3 ticks) that decays back out.
- sustained: a step-change to a degraded baseline held for tens of ticks, then
  a hard revert (mimics a stuck process / resource contention incident).
- drift: a slow trapezoidal ramp up-hold-down over a long window (mimics a
  memory leak or gradually filling disk).

Each host has independent injection rolls gated by `injection_rate` per tick,
plus a cooldown after any anomaly (active or just-ended) so anomalies don't
overlap or chain back-to-back, which would make them look like one long
incident instead of distinct events.
"""

from __future__ import annotations

import numpy as np

ANOMALY_TYPES = ("spike", "sustained", "drift")

# Which metrics each anomaly type perturbs, and the direction/shape of the
# multiplicative perturbation applied on top of the base signal.
_SPIKE_METRICS = ("latency_ms", "error_rate_pct")
_SUSTAINED_METRICS = ("cpu_pct", "latency_ms", "error_rate_pct")
_DRIFT_METRICS = ("mem_pct",)


class _ActiveAnomaly:
    def __init__(self, kind: str, rng: np.random.Generator):
        self.kind = kind
        self.tick_index = 0
        if kind == "spike":
            # 1-3 tick jump, decaying back to baseline over the last tick.
            peak = rng.uniform(2.5, 4.5)
            self.multipliers = [peak, 1.0 + (peak - 1.0) * 0.35]
            if rng.random() < 0.5:
                self.multipliers.insert(1, 1.0 + (peak - 1.0) * 0.65)
            self.metrics = _SPIKE_METRICS
        elif kind == "sustained":
            self.duration = int(rng.integers(20, 60))
            self.multiplier = rng.uniform(1.6, 2.5)
            self.multipliers = None
            self.metrics = _SUSTAINED_METRICS
        else:  # drift
            self.duration = int(rng.integers(90, 200))
            self.peak_multiplier = rng.uniform(1.5, 2.2)
            self.metrics = _DRIFT_METRICS

    def apply(self, metrics: dict[str, float]) -> tuple[dict[str, float], bool]:
        """Returns (perturbed_metrics, is_finished)."""
        out = dict(metrics)
        if self.kind == "spike":
            if self.tick_index >= len(self.multipliers):
                return out, True
            mult = self.multipliers[self.tick_index]
            for m in self.metrics:
                out[m] = metrics[m] * mult
            self.tick_index += 1
            return out, self.tick_index >= len(self.multipliers)

        if self.kind == "sustained":
            for m in self.metrics:
                out[m] = metrics[m] * self.multiplier
            self.tick_index += 1
            return out, self.tick_index >= self.duration

        # drift: trapezoid over duration — ramp up (1/3), hold (1/3), ramp down (1/3)
        third = max(1, self.duration // 3)
        progress = self.tick_index
        if progress < third:
            frac = progress / third
        elif progress < 2 * third:
            frac = 1.0
        else:
            frac = max(0.0, 1.0 - (progress - 2 * third) / third)
        mult = 1.0 + (self.peak_multiplier - 1.0) * frac
        for m in self.metrics:
            out[m] = metrics[m] * mult
        self.tick_index += 1
        return out, self.tick_index >= self.duration


class AnomalyInjector:
    def __init__(self, injection_rate: float, cooldown_ticks: int, seed: int):
        self.injection_rate = injection_rate
        self.cooldown_ticks = cooldown_ticks
        self.rng = np.random.default_rng(seed)
        self._active: _ActiveAnomaly | None = None
        self._cooldown_remaining = 0

    def maybe_inject(self, base_metrics: dict[str, float]) -> tuple[dict[str, float], dict]:
        """Returns (possibly-perturbed metrics, injected_anomaly info dict)."""
        if self._active is not None:
            perturbed, finished = self._active.apply(base_metrics)
            kind = self._active.kind
            if finished:
                self._active = None
                self._cooldown_remaining = self.cooldown_ticks
            return perturbed, {"active": True, "type": kind}

        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            return base_metrics, {"active": False, "type": None}

        if self.rng.random() < self.injection_rate:
            # str(): np.random.Generator.choice over a tuple of strings
            # returns numpy.str_, which pydantic's Literal validator rejects
            # even though it string-equals a valid value.
            kind = str(self.rng.choice(ANOMALY_TYPES))
            self._active = _ActiveAnomaly(kind, self.rng)
            perturbed, finished = self._active.apply(base_metrics)
            if finished:
                self._active = None
                self._cooldown_remaining = self.cooldown_ticks
            return perturbed, {"active": True, "type": kind}

        return base_metrics, {"active": False, "type": None}
