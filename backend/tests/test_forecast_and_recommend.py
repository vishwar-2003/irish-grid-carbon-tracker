import datetime as dt

import pandas as pd

from app.eirgrid import TZ, demo_frame
from app.forecast import HORIZON_HOURS, predict, to_hourly, train
from app.recommend import band, best_window, greenest_hours, recommend


def _points(values):
    start = pd.Timestamp("2026-10-01 15:00", tz=TZ)
    return [{"time": (start + pd.Timedelta(hours=i)).isoformat(), "intensity": v} for i, v in enumerate(values)]


def test_best_window_finds_lowest_contiguous_run():
    pts = _points([300, 280, 150, 140, 290, 100, 310])
    w = best_window(pts, 2)
    assert w.avg_intensity == 145.0
    assert w.start == pts[2]["time"]
    # A single very low hour wins a 1-hour window.
    assert best_window(pts, 1).start == pts[5]["time"]


def test_recommend_reports_saving_against_starting_now():
    pts = _points([300, 300, 100, 100, 300])
    rec = recommend(pts, "dishwasher")  # 1.0 kWh over 2 h
    assert rec["co2_now_g"] == 300 and rec["co2_best_g"] == 100
    assert rec["saving_vs_now_g"] == 200
    assert rec["run_now"] is False


def test_greenest_hours_sorted_by_time():
    hours = greenest_hours(_points([300, 120, 250, 110, 400]), count=2)
    assert [h["intensity"] for h in hours] == [120, 110]


def test_band_thresholds():
    assert band(150) == "low" and band(250) == "moderate" and band(450) == "high" and band(None) is None


def test_model_trains_and_forecasts_24h():
    today = dt.date(2026, 10, 1)
    now = pd.Timestamp("2026-10-01 14:30", tz=TZ)
    frame = demo_frame(today - dt.timedelta(days=21), today + dt.timedelta(days=1), now=now)
    hourly = to_hourly(frame)
    model = train(hourly, "demo")
    assert model.median is not None
    assert model.metrics["mae"] < model.metrics["mae_baseline"]
    fc = predict(hourly, model)
    assert len(fc.points) == HORIZON_HOURS
    assert all(p["low"] <= p["intensity"] <= p["high"] for p in fc.points)
    assert pd.Timestamp(fc.points[0]["time"]) > now
