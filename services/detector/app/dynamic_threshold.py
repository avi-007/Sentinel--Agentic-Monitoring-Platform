"""Adaptive per-host threshold — percentile based, nothing to memorize.

Why not a static threshold: a fixed score cutoff assumes every host behaves
the same and never drifts, but scores drift with retraining, load changes,
and different baseline noise per host — a noisy host trips a single global
cutoff constantly, a quiet host never trips a loose one.

Algorithm, per host, on raw_score = -model.score_samples(x) (larger = more anomalous):

1. Keep the last `score_history_size` raw scores for this host.
2. Threshold = the 95th percentile of that recent history. If a new score is
   higher than 95% of what's been typical for this host lately, it's
   anomalous. Adapts automatically as behavior shifts — no formulas to tune.
3. Cooldown: once an alert is published for a host, suppress further
   publications for DET_ALERT_COOLDOWN_SECONDS so one sustained incident
   doesn't spam repeat alerts. Every event is still scored and written to
   `metrics` regardless of cooldown.

Note: `ewma_mean`/`ewma_std` in ThresholdResult are legacy field names kept
for DB/schema compatibility — they now hold a plain rolling mean/std of
recent scores, for display only, not used in the threshold calculation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from .config import DetectorSettings
from .host_state import HostModelState

MIN_HISTORY_FOR_THRESHOLD = 10


@dataclass
class ThresholdResult:
    threshold: Optional[float]  # None until MIN_HISTORY_FOR_THRESHOLD scores are in — never alert during that gap
    ewma_mean: float
    ewma_std: float
    is_anomaly: bool
    severity: Optional[str]
    should_publish_alert: bool


def evaluate(
    state: HostModelState, raw_score: float, settings: DetectorSettings, now: datetime
) -> ThresholdResult:
    state.score_history.append(raw_score)
    history = list(state.score_history)

    threshold: Optional[float] = None
    if len(history) >= MIN_HISTORY_FOR_THRESHOLD:
        threshold = float(np.percentile(history, settings.det_threshold_percentile))

    mean = float(np.mean(history))
    std = float(np.std(history))
    is_anomaly = threshold is not None and raw_score > threshold

    severity: Optional[str] = None
    if is_anomaly:
        severity = "critical" if raw_score > threshold + std else "warning"

    cooldown_active = (
        state.last_alert_time is not None
        and (now - state.last_alert_time).total_seconds() < settings.det_alert_cooldown_seconds
    )
    should_publish_alert = is_anomaly and not cooldown_active
    if should_publish_alert:
        state.last_alert_time = now

    return ThresholdResult(
        threshold=threshold,
        ewma_mean=mean,
        ewma_std=std,
        is_anomaly=is_anomaly,
        severity=severity,
        should_publish_alert=should_publish_alert,
    )
