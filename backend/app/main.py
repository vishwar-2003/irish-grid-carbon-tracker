"""Irish Grid Carbon Tracker API."""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .data import GridDataService
from .eirgrid import EirGridError
from .forecast import ForecastService, to_hourly
from .recommend import APPLIANCES, band, greenest_hours, recommend

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Irish Grid Carbon Tracker",
    description="Live carbon intensity and wind share for the Irish grid, a 24-hour forecast, "
    "and the greenest times to run household appliances. Data: EirGrid Smart Grid Dashboard.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

grid = GridDataService()
forecaster = ForecastService()


def _num(value, digits: int = 1):
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
        return None
    return round(float(value), digits)


def _load():
    try:
        return grid.get()
    except EirGridError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _current(frame: pd.DataFrame) -> dict:
    observed = frame.dropna(subset=["co2_intensity"])
    if observed.empty:
        raise HTTPException(status_code=503, detail="No carbon intensity data available")
    latest = observed.iloc[-1]
    ts = observed.index[-1]
    demand = latest.get("demand")
    wind = latest.get("wind")
    solar = latest.get("solar")
    last_24h = observed.loc[observed.index > ts - pd.Timedelta(hours=24), "co2_intensity"]
    wind_24h = observed.loc[observed.index > ts - pd.Timedelta(hours=24)]
    return {
        "time": ts.isoformat(),
        "intensity": _num(latest["co2_intensity"], 0),
        "band": band(latest["co2_intensity"]),
        "wind_mw": _num(wind, 0),
        "solar_mw": _num(solar, 0),
        "demand_mw": _num(demand, 0),
        "wind_share": _num(100 * wind / demand) if demand else None,
        "renewable_share": _num(100 * ((wind or 0) + (solar or 0)) / demand) if demand else None,
        "intensity_24h": {
            "min": _num(last_24h.min(), 0),
            "avg": _num(last_24h.mean(), 0),
            "max": _num(last_24h.max(), 0),
        },
        "wind_share_24h_avg": _num(100 * (wind_24h["wind"] / wind_24h["demand"]).mean()),
    }


def _history(frame: pd.DataFrame, hours: int) -> list[dict]:
    hourly = to_hourly(frame).dropna(subset=["co2_intensity"]).tail(hours)
    return [
        {
            "time": ts.isoformat(),
            "intensity": _num(row["co2_intensity"]),
            "wind_share": _num(100 * row["wind"] / row["demand"]) if row["demand"] else None,
            "wind_mw": _num(row["wind"], 0),
            "demand_mw": _num(row["demand"], 0),
        }
        for ts, row in hourly.iterrows()
    ]


def _meta(data) -> dict:
    return {
        "source": data.source,
        "region": settings.region,
        "fetched_at": data.fetched_at.isoformat(),
        "note": data.note,
        "attribution": "Data: EirGrid Smart Grid Dashboard (smartgriddashboard.com)",
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": settings.data_mode, "region": settings.region}


@app.get("/api/current")
def current():
    data = _load()
    return {"meta": _meta(data), **_current(data.frame)}


@app.get("/api/history")
def history(hours: int = Query(24, ge=1, le=24 * 14)):
    data = _load()
    return {"meta": _meta(data), "points": _history(data.frame, hours)}


@app.get("/api/forecast")
def forecast():
    data = _load()
    fc = forecaster.forecast(data.frame, data.source)
    return {
        "meta": _meta(data),
        "points": fc.points,
        "model": {**fc.metrics, "training_hours": fc.training_rows,
                  "trained_at": pd.Timestamp(fc.trained_at, unit="s", tz="UTC").isoformat()},
    }


@app.get("/api/appliances")
def appliances():
    return [{"id": key, **spec} for key, spec in APPLIANCES.items()]


@app.get("/api/recommendations")
def recommendations(appliance: str | None = None):
    if appliance and appliance not in APPLIANCES:
        raise HTTPException(status_code=404, detail=f"Unknown appliance '{appliance}'")
    data = _load()
    fc = forecaster.forecast(data.frame, data.source)
    keys = [appliance] if appliance else list(APPLIANCES)
    return {
        "meta": _meta(data),
        "greenest_hours": greenest_hours(fc.points),
        "appliances": [r for k in keys if (r := recommend(fc.points, k))],
    }


@app.get("/api/dashboard")
def dashboard(history_hours: int = Query(24, ge=1, le=24 * 14)):
    """Everything the front end needs in one request."""
    data = _load()
    fc = forecaster.forecast(data.frame, data.source)
    return {
        "meta": _meta(data),
        "current": _current(data.frame),
        "history": _history(data.frame, history_hours),
        "forecast": fc.points,
        "model": {**fc.metrics, "training_hours": fc.training_rows,
                  "trained_at": pd.Timestamp(fc.trained_at, unit="s", tz="UTC").isoformat()},
        "greenest_hours": greenest_hours(fc.points),
        "appliances": [r for k in APPLIANCES if (r := recommend(fc.points, k))],
    }


# Optional: serve the built React app from the same service (single-deploy option).
_dist = Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
