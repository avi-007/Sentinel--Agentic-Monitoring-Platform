"""IsolationForest lifecycle per host: warm-up fit on the first
DET_WARMUP_EVENTS feature vectors, then periodic sliding-window retraining
every DET_RETRAIN_INTERVAL_EVENTS new events (replacing the model atomically,
bumping model_version). No holdout/rollback validation is performed on refit —
a documented demo simplification; the dynamic threshold layer (dynamic_threshold.py)
is the actual guard against false positives, not the model boundary itself.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import structlog
from sklearn.ensemble import IsolationForest

from .config import DetectorSettings
from .host_state import HostModelState

log = structlog.get_logger(__name__)


def _fit_model(X: list[np.ndarray], settings: DetectorSettings) -> IsolationForest:
    model = IsolationForest(
        n_estimators=settings.det_iso_forest_n_estimators,
        contamination=settings.det_iso_forest_contamination,
        random_state=42,
    )
    model.fit(np.array(X))
    return model


def ingest_and_score(
    state: HostModelState, feature_vector: np.ndarray, settings: DetectorSettings
) -> Optional[float]:
    """Feeds one feature vector into the host's warm-up/train buffers. Returns
    the raw anomaly score (larger = more anomalous) once the model is active,
    or None while still warming up (no score/alert possible yet).
    """
    if not state.is_warmed_up:
        state.warmup_features.append(feature_vector)
        state.events_since_fit += 1
        if state.events_since_fit >= settings.det_warmup_events:
            state.model = _fit_model(state.warmup_features, settings)
            state.model_version += 1
            state.train_window.extend(state.warmup_features)
            state.is_warmed_up = True
            state.warmup_features = []
            state.events_since_fit = 0
            log.info(
                "detector.model_warmed_up",
                host_id=state.host_id,
                model_version=state.model_version,
            )
        return None

    state.train_window.append(feature_vector)
    state.events_since_fit += 1
    if (
        state.events_since_fit >= settings.det_retrain_interval_events
        and len(state.train_window) >= 50
    ):
        state.model = _fit_model(list(state.train_window), settings)
        state.model_version += 1
        state.events_since_fit = 0
        log.info(
            "detector.model_retrained",
            host_id=state.host_id,
            model_version=state.model_version,
            window_size=len(state.train_window),
        )

    # score_samples: higher = more normal. Negate so larger = more anomalous,
    # a convention used consistently through dynamic_threshold.py and storage.
    raw_score = float(-state.model.score_samples(feature_vector.reshape(1, -1))[0])
    return raw_score
