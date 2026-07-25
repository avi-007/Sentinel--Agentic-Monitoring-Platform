"""The adaptive threshold that replaces a static score cutoff.

Why not a static threshold: a fixed cutoff assumes a stationary anomaly-score
distribution, but IsolationForest scores drift with (a) periodic retraining,
(b) legitimate diurnal/seasonal load changes, and (c) heterogeneous per-host
baseline noise — a naturally noisier host trips a single global cutoff
constantly, a quiet host never trips a loose one. This module instead tracks a
per-host, continuously-updating "normal" band and only fires on genuine
deviation from *recent local* behavior.

Algorithm, per host, on raw_score = -model.score_samples(x) (larger = more anomalous):

1. EWMA control band (Shewhart-style adaptive control limit):
       mu_t    = alpha * score_t + (1 - alpha) * mu_{t-1}
       sigma_t = sqrt(alpha * (score_t - mu_t)^2 + (1 - alpha) * sigma_{t-1}^2)
       ewma_threshold_t = mu_t + k * sigma_t

2. Percentile floor guard (prevents threshold collapse — and a false-positive
   flood — during unusually calm stretches where sigma_t shrinks toward 0):
       threshold_t = max(ewma_threshold_t, p95(recent raw scores))

3. Hysteresis / cooldown: once an alert is *published* for a host, suppress
   further alert publications for that host for DET_ALERT_COOLDOWN_SECONDS even
   if the score stays above threshold, to avoid alert storms during one
   sustained incident. Every event is still scored and written to `metrics`
   regardless of cooldown — only the Kafka publish + `alerts` row insert are
   throttled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from .config import DetectorSettings
from .host_state import HostModelState


@dataclass
class ThresholdResult:
    threshold: float
    ewma_mean: float
    ewma_std: float
    is_anomaly: bool  # score > threshold, regardless of cooldown — written to every metrics row
    severity: Optional[str]  # "warning" | "critical" | None
    should_publish_alert: bool  # is_anomaly AND cooldown allows it


def evaluate(
    state: HostModelState, raw_score: float, settings: DetectorSettings, now: datetime
) -> ThresholdResult:
    alpha = settings.det_ewma_alpha

    if not state.ewma_initialized:
        state.ewma_mean = raw_score
        state.ewma_std = 0.0
        state.ewma_initialized = True
    else:
        prev_mean = state.ewma_mean
        state.ewma_mean = alpha * raw_score + (1 - alpha) * prev_mean
        deviation_sq = (raw_score - state.ewma_mean) ** 2
        state.ewma_std = math.sqrt(alpha * deviation_sq + (1 - alpha) * state.ewma_std**2)

    state.score_history.append(raw_score)

    ewma_threshold = state.ewma_mean + settings.det_threshold_k * state.ewma_std
    if len(state.score_history) >= 10:
        percentile_floor = float(np.percentile(list(state.score_history), settings.det_threshold_percentile))
    else:
        percentile_floor = ewma_threshold

    threshold = max(ewma_threshold, percentile_floor)
    is_anomaly = raw_score > threshold

    severity: Optional[str] = None
    if is_anomaly:
        severity = "critical" if raw_score > threshold + state.ewma_std else "warning"

    cooldown_active = (
        state.last_alert_time is not None
        and (now - state.last_alert_time).total_seconds() < settings.det_alert_cooldown_seconds
    )
    should_publish_alert = is_anomaly and not cooldown_active
    if should_publish_alert:
        state.last_alert_time = now

    return ThresholdResult(
        threshold=threshold,
        ewma_mean=state.ewma_mean,
        ewma_std=state.ewma_std,
        is_anomaly=is_anomaly,
        severity=severity,
        should_publish_alert=should_publish_alert,
    )
