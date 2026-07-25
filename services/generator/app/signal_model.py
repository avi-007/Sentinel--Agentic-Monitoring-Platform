"""Per-host synthetic signal generator.

For each metric, at simulated time t:

    value(t) = baseline
             + diurnal_amplitude * sin(2*pi*t/DAY_PERIOD + phase)   # day/night shape
             + ar1_noise(t)                                          # autocorrelated jitter
             + stress_loading * latent_stress(t)                     # shared cross-metric factor

`latent_stress(t)` is a single per-host AR(1) process (clipped to be
non-negative, so it represents "load pressure" bursts rather than symmetric
noise) shared across cpu/mem/latency/error_rate with different loadings per
host_profiles.py. This is what makes "high latency correlates with high error
rate" emerge from the model instead of being a hard-coded pairwise rule.
"""

from __future__ import annotations

import math

import numpy as np

from .host_profiles import METRIC_BOUNDS, METRIC_NAMES, HostProfile

DAY_PERIOD_SECONDS = 24 * 60 * 60

AR1_PHI = 0.6  # per-metric noise autocorrelation
STRESS_PHI = 0.85  # latent stress autocorrelation (slower/smoother than metric noise)
STRESS_SIGMA = 0.18

# Per-metric AR(1) noise std-dev, roughly proportional to how "twitchy" each
# metric naturally is.
NOISE_SIGMA = {"cpu_pct": 1.5, "mem_pct": 1.0, "latency_ms": 4.0, "error_rate_pct": 0.08}


class HostSignalGenerator:
    def __init__(self, profile: HostProfile, time_scale_factor: float):
        self.profile = profile
        self.time_scale_factor = time_scale_factor
        self.rng = np.random.default_rng(profile.seed)
        self.elapsed_sim_seconds = self.rng.uniform(0, DAY_PERIOD_SECONDS)
        self._noise_state = {m: 0.0 for m in METRIC_NAMES}
        self._stress_state = 0.0

    def tick(self, dt_wall_seconds: float) -> dict[str, float]:
        self.elapsed_sim_seconds += dt_wall_seconds * self.time_scale_factor

        # latent stress: AR(1), clipped at 0 so it models occasional load
        # pressure bursts rather than symmetric noise.
        stress_innovation = self.rng.normal(0, STRESS_SIGMA)
        self._stress_state = max(0.0, STRESS_PHI * self._stress_state + stress_innovation)

        diurnal = math.sin(
            2 * math.pi * self.elapsed_sim_seconds / DAY_PERIOD_SECONDS + self.profile.phase_offset
        )

        values: dict[str, float] = {}
        for metric in METRIC_NAMES:
            noise_innovation = self.rng.normal(0, NOISE_SIGMA[metric])
            self._noise_state[metric] = AR1_PHI * self._noise_state[metric] + noise_innovation

            value = (
                self.profile.baseline[metric]
                + self.profile.diurnal_amplitude[metric] * diurnal
                + self._noise_state[metric]
                + self.profile.stress_loading[metric] * self._stress_state
            )
            lo, hi = METRIC_BOUNDS[metric]
            values[metric] = float(np.clip(value, lo, hi))

        return values
