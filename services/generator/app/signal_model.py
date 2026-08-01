"""Per-host synthetic signal generator.

For each metric, at simulated time t:

    value(t) = baseline
             + diurnal_amplitude * sin(2*pi*t/DAY_PERIOD + phase)   # day/night shape
             + noise(t)                                              # independent jitter

Each metric jitters independently — day/night shape plus random noise,
nothing more. Kept deliberately simple: the interesting engineering in this
project lives in the detector's adaptive threshold and the agent's
tool-calling loop, not in how realistic the fake telemetry looks.
"""

from __future__ import annotations

import math

import numpy as np

from .host_profiles import METRIC_BOUNDS, METRIC_NAMES, HostProfile

DAY_PERIOD_SECONDS = 24 * 60 * 60

# Per-metric noise std-dev, roughly proportional to how "twitchy" each metric
# naturally is.
NOISE_SIGMA = {"cpu_pct": 1.5, "mem_pct": 1.0, "latency_ms": 4.0, "error_rate_pct": 0.08}


class HostSignalGenerator:
    def __init__(self, profile: HostProfile, time_scale_factor: float):
        self.profile = profile
        self.time_scale_factor = time_scale_factor
        self.rng = np.random.default_rng(profile.seed)
        self.elapsed_sim_seconds = self.rng.uniform(0, DAY_PERIOD_SECONDS)

    def tick(self, dt_wall_seconds: float) -> dict[str, float]:
        self.elapsed_sim_seconds += dt_wall_seconds * self.time_scale_factor

        diurnal = math.sin(
            2 * math.pi * self.elapsed_sim_seconds / DAY_PERIOD_SECONDS + self.profile.phase_offset
        )

        values: dict[str, float] = {}
        for metric in METRIC_NAMES:
            noise = self.rng.normal(0, NOISE_SIGMA[metric])
            value = (
                self.profile.baseline[metric]
                + self.profile.diurnal_amplitude[metric] * diurnal
                + noise
            )
            lo, hi = METRIC_BOUNDS[metric]
            values[metric] = float(np.clip(value, lo, hi))

        return values
