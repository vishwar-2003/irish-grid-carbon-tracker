"""24-hour carbon intensity forecast.

Approach
--------
Carbon intensity on the Irish grid is driven mostly by how much of demand is met by
wind. EirGrid publishes its own day-ahead wind and demand forecasts, so the model
learns the mapping

    (forecast wind share, hour of day, day of week, intensity 24h earlier) -> gCO2/kWh

with gradient-boosted trees, trained on the last few weeks of 15-minute data
aggregated to hourly. Training uses EirGrid's wind *forecast* (not the actual) as
the input, so the model sees the same kind of input at training and prediction
time. Two extra quantile models give a 10th-90th percentile band.

The model is scored on the most recent 72 hours, held out in time order, against a
seasonal-naive baseline ("same as this hour yesterday").
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from .config import settings

log = logging.getLogger(__name__)

FEATURES = ["hour_sin", "hour_cos", "dow", "weekend", "wind_share", "wind_ref", "demand_ref", "lag24"]
HOLDOUT_HOURS = 72
HORIZON_HOURS = 24
MIN_TRAIN_ROWS = 120


def to_hourly(frame: pd.DataFrame) -> pd.DataFrame:
    hourly = frame.resample("1h").mean()
    return hourly


def build_features(hourly: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(index=hourly.index)
    hour = hourly.index.hour
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["dow"] = hourly.index.dayofweek
    df["weekend"] = (hourly.index.dayofweek >= 5).astype(int)

    demand_ref = hourly["demand_fcast"].fillna(hourly["demand"])
    # Where neither is available, use the typical demand for that hour of day.
    profile = hourly["demand"].groupby(hour).mean()
    demand_ref = demand_ref.fillna(pd.Series(hour.map(profile).to_numpy(dtype=float), index=hourly.index))
    wind_ref = hourly["wind_fcast"].fillna(hourly["wind"])

    df["wind_ref"] = wind_ref
    df["demand_ref"] = demand_ref
    df["wind_share"] = (wind_ref / demand_ref).clip(0, 1.5)
    lag = hourly["co2_intensity"].copy()
    lag.index = lag.index + pd.Timedelta(hours=24)
    df["lag24"] = lag.reindex(df.index)
    return df


def _model(**kwargs) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=10,
        l2_regularization=1.0, random_state=0, **kwargs,
    )


@dataclass
class TrainedModel:
    median: HistGradientBoostingRegressor | None
    low: HistGradientBoostingRegressor | None
    high: HistGradientBoostingRegressor | None
    metrics: dict
    trained_at: float
    source: str
    rows: int


def _mae(a, b) -> float:
    return float(np.mean(np.abs(np.asarray(a) - np.asarray(b))))


def train(hourly: pd.DataFrame, source: str) -> TrainedModel:
    feats = build_features(hourly)
    target = hourly["co2_intensity"]
    usable = target.notna() & feats["wind_share"].notna()
    X, y = feats.loc[usable, FEATURES], target[usable]

    if len(y) < MIN_TRAIN_ROWS:
        log.warning("Only %d hourly rows; using seasonal-naive forecast", len(y))
        return TrainedModel(None, None, None, {"note": "not enough history to train"}, time.time(), source, len(y))

    # Time-ordered holdout: train on everything except the final 72 hours.
    cut = len(y) - HOLDOUT_HOURS
    X_tr, y_tr, X_te, y_te = X.iloc[:cut], y.iloc[:cut], X.iloc[cut:], y.iloc[cut:]
    evaluator = _model(loss="absolute_error").fit(X_tr, y_tr)
    pred = evaluator.predict(X_te)
    naive_ok = X_te["lag24"].notna()
    mae_model = _mae(y_te, pred)
    mae_naive = _mae(y_te[naive_ok], X_te.loc[naive_ok, "lag24"])
    metrics = {
        "holdout_hours": int(len(y_te)),
        "train_hours": int(len(y_tr)),
        "mae": round(mae_model, 1),
        "mae_baseline": round(mae_naive, 1),
        "skill_vs_baseline_pct": round(100 * (1 - mae_model / mae_naive), 1) if mae_naive else None,
        "mape_pct": round(100 * float(np.mean(np.abs((y_te - pred) / y_te))), 1),
        "baseline": "seasonal naive (same hour yesterday)",
        "algorithm": "HistGradientBoostingRegressor + quantile models (p10/p90)",
    }

    # Refit on all available data for the live forecast.
    median = _model(loss="absolute_error").fit(X, y)
    low = _model(loss="quantile", quantile=0.1).fit(X, y)
    high = _model(loss="quantile", quantile=0.9).fit(X, y)
    log.info("Trained carbon model on %d hours: %s", len(y), metrics)
    return TrainedModel(median, low, high, metrics, time.time(), source, int(len(y)))


@dataclass
class Forecast:
    points: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    trained_at: float = 0.0
    training_rows: int = 0


def predict(hourly: pd.DataFrame, model: TrainedModel) -> Forecast:
    observed = hourly["co2_intensity"].dropna()
    if observed.empty:
        return Forecast(metrics=model.metrics)
    start = observed.index[-1] + pd.Timedelta(hours=1)
    future_index = pd.date_range(start, periods=HORIZON_HOURS, freq="1h")
    extended = hourly.reindex(hourly.index.union(future_index))
    feats = build_features(extended).loc[future_index]

    if model.median is not None:
        X = feats[FEATURES]
        mid = model.median.predict(X)
        lo = np.minimum(model.low.predict(X), mid)
        hi = np.maximum(model.high.predict(X), mid)
    else:  # seasonal naive fallback
        mid = feats["lag24"].fillna(observed.tail(24).mean()).to_numpy()
        lo, hi = mid * 0.85, mid * 1.15

    points = [
        {
            "time": ts.isoformat(),
            "intensity": round(float(m), 1),
            "low": round(float(max(l, 0)), 1),
            "high": round(float(h), 1),
            "wind_share": None if pd.isna(ws) else round(float(min(ws, 1.0)) * 100, 1),
        }
        for ts, m, l, h, ws in zip(future_index, mid, lo, hi, feats["wind_share"])
    ]
    return Forecast(points, model.metrics, model.trained_at, model.rows)


class ForecastService:
    def __init__(self):
        self._lock = threading.Lock()
        self._model: TrainedModel | None = None

    def forecast(self, frame: pd.DataFrame, source: str) -> Forecast:
        hourly = to_hourly(frame)
        with self._lock:
            stale = (
                self._model is None
                or self._model.source != source
                or time.time() - self._model.trained_at > settings.model_ttl
            )
            if stale:
                self._model = train(hourly, source)
            model = self._model
        return predict(hourly, model)
