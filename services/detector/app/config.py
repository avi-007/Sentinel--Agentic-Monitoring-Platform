from common.settings import BaseServiceSettings


class DetectorSettings(BaseServiceSettings):
    det_warmup_events: int = 120
    det_rolling_window: int = 10
    det_retrain_interval_events: int = 500
    det_train_window_size: int = 1000
    det_iso_forest_n_estimators: int = 100
    det_iso_forest_contamination: float = 0.02
    det_threshold_percentile: float = 95.0
    det_score_history_size: int = 200
    det_alert_cooldown_seconds: float = 60.0
    det_trend_window_size: int = 10
    det_trend_min_points: int = 5
    det_trend_horizon_minutes: float = 20.0
    det_trend_min_r_squared: float = 0.7
    det_trend_smoothing_window: int = 3
    detector_consumer_group: str = "sentinel-detector"