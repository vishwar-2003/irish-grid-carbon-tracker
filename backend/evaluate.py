"""Backtest the carbon intensity model on real EirGrid data.

Run this on a machine with internet access to get honest accuracy figures for the
README or a CV:

    cd backend
    python evaluate.py --days 56 --folds 7

For each of the last ``folds`` days it trains only on data before that day, forecasts
the day's 24 hours, and compares with what actually happened (rolling-origin
backtest). Results are printed and written to ``evaluation.json``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json

import numpy as np
import pandas as pd

from app.eirgrid import TZ, EirGridClient, demo_frame
from app.forecast import FEATURES, _model, build_features, to_hourly


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=56, help="days of history to download")
    parser.add_argument("--folds", type=int, default=7, help="number of daily backtest folds")
    parser.add_argument("--region", default="ROI", choices=["ROI", "NI", "ALL"])
    parser.add_argument("--demo", action="store_true", help="use simulated data (no network)")
    args = parser.parse_args()

    today = pd.Timestamp.now(tz=TZ).date()
    start, end = today - dt.timedelta(days=args.days), today - dt.timedelta(days=1)
    frame = demo_frame(start, end) if args.demo else EirGridClient(region=args.region).fetch(start, end)
    hourly = to_hourly(frame)
    feats = build_features(hourly)
    target = hourly["co2_intensity"]

    rows = []
    for k in range(args.folds, 0, -1):
        day_start = pd.Timestamp(today - dt.timedelta(days=k), tz=TZ)
        day_end = day_start + pd.Timedelta(days=1)
        train_mask = (feats.index < day_start) & target.notna() & feats["wind_share"].notna()
        test_mask = (feats.index >= day_start) & (feats.index < day_end) & target.notna()
        if train_mask.sum() < 120 or test_mask.sum() < 12:
            continue
        model = _model(loss="absolute_error").fit(feats.loc[train_mask, FEATURES], target[train_mask])
        pred = model.predict(feats.loc[test_mask, FEATURES])
        actual = target[test_mask].to_numpy()
        naive = feats.loc[test_mask, "lag24"].to_numpy()
        ok = ~np.isnan(naive)
        # Did the model pick the right greenest 2-hour window?
        pred_s = pd.Series(pred).rolling(2).mean()
        act_s = pd.Series(actual).rolling(2).mean()
        chosen = act_s.iloc[int(pred_s.idxmin())]
        rows.append({
            "date": day_start.date().isoformat(),
            "mae": float(np.mean(np.abs(actual - pred))),
            "mae_baseline": float(np.mean(np.abs(actual[ok] - naive[ok]))),
            "mape_pct": float(100 * np.mean(np.abs((actual - pred) / actual))),
            "green_window_gap": float(chosen - act_s.min()),
        })

    if not rows:
        raise SystemExit("Not enough data to backtest; increase --days.")
    df = pd.DataFrame(rows)
    summary = {
        "region": args.region,
        "source": "demo" if args.demo else "live",
        "folds": len(df),
        "mae_gco2_kwh": round(df["mae"].mean(), 1),
        "mae_baseline_gco2_kwh": round(df["mae_baseline"].mean(), 1),
        "improvement_vs_baseline_pct": round(100 * (1 - df["mae"].mean() / df["mae_baseline"].mean()), 1),
        "mape_pct": round(df["mape_pct"].mean(), 1),
        "avg_green_window_gap_gco2_kwh": round(df["green_window_gap"].mean(), 1),
        "per_day": df.round(1).to_dict(orient="records"),
    }
    print(json.dumps(summary, indent=2))
    with open("evaluation.json", "w") as fh:
        json.dump(summary, fh, indent=2)


if __name__ == "__main__":
    main()
