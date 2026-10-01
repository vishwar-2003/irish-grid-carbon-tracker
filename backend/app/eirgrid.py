"""Client for EirGrid's public Smart Grid Dashboard data.

The dashboard at https://www.smartgriddashboard.com serves its charts from a public
JSON endpoint (``/api/chart/``). Each response is ``{"Rows": [...]}`` where every row
looks like::

    {"EffectiveTime": "29-Sep-2026 00:15:00", "FieldName": "CO2_INTENSITY",
     "Region": "ROI", "Value": 128}

Timestamps are Irish local time at 15-minute resolution. The endpoint is not a
documented, versioned API, so everything that depends on its shape lives here.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

import httpx
import numpy as np
import pandas as pd

from .config import settings

log = logging.getLogger(__name__)

TZ = "Europe/Dublin"

# EirGrid FieldName -> column name used throughout the app.
FIELD_MAP = {
    "CO2_INTENSITY": "co2_intensity",  # gCO2/kWh
    "CO2_EMISSIONS": "co2_emissions",  # tCO2/hr
    "WIND_ACTUAL": "wind",  # MW
    "SOLAR_ACTUAL": "solar",  # MW
    "SYSTEM_DEMAND": "demand",  # MW
    "WIND_FCAST": "wind_fcast",  # MW, EirGrid's own wind forecast
    "DEMAND_FORECAST_VALUE": "demand_fcast",  # MW, EirGrid's own demand forecast
}
COLUMNS = list(FIELD_MAP.values())

# (chartType, area) pairs. Each series is requested on its own: combined requests are
# much slower on EirGrid's side and are the ones that time out when it is busy.
REQUESTS = [
    ("co2", "co2intensity"),
    ("co2", "co2emission"),
    ("default", "windactual"),
    ("default", "demandactual"),
    ("default", "solaractual"),
    ("default", "windforecast"),
    ("default", "demandforecast"),
]


class EirGridError(RuntimeError):
    pass


def parse_rows(rows: Iterable[dict]) -> pd.DataFrame:
    """Turn raw dashboard rows into a wide 15-minute frame indexed by tz-aware time."""
    records = []
    for row in rows:
        column = FIELD_MAP.get(row.get("FieldName"))
        value = row.get("Value")
        if column is None or value is None:
            continue
        records.append((row["EffectiveTime"], column, float(value)))

    if not records:
        return pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], tz=TZ, name="time"))

    long = pd.DataFrame(records, columns=["time", "column", "value"])
    long["time"] = pd.to_datetime(long["time"], format="%d-%b-%Y %H:%M:%S")
    # Local timestamps: the October DST hour is ambiguous and is dropped rather than guessed.
    long["time"] = long["time"].dt.tz_localize(TZ, ambiguous="NaT", nonexistent="shift_forward")
    long = long.dropna(subset=["time"])

    wide = long.pivot_table(index="time", columns="column", values="value", aggfunc="mean")
    wide = wide.reindex(columns=COLUMNS)
    wide.index.name = "time"
    return wide.sort_index()


def fill_intensity(frame: pd.DataFrame) -> pd.DataFrame:
    """Use EirGrid's CO2_INTENSITY where present; otherwise derive it.

    CO2 emissions in tCO2/h divided by demand in MW gives tCO2/MWh, which is
    numerically kgCO2/kWh, so x1000 gives gCO2/kWh. EirGrid's own figure divides by
    generation rather than demand, so the derived value is a close approximation.
    """
    if frame.empty:
        return frame
    derived = frame["co2_emissions"] * 1000 / frame["demand"].where(frame["demand"] > 0)
    frame["co2_intensity"] = frame["co2_intensity"].fillna(derived.round())
    return frame


class EirGridClient:
    """Requests one day at a time, in parallel, with retries. A day that still fails
    is skipped, so one slow or broken EirGrid request does not take the app down."""

    def __init__(self, region: str | None = None, base_url: str | None = None):
        self.region = region or settings.region
        self.base_url = (base_url or settings.eirgrid_base_url).rstrip("/")
        self._http = httpx.Client(
            timeout=settings.request_timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.smartgriddashboard.com/",
            },
        )
        self.attempts = 2
        self.last_errors: list[str] = []

    def _chart(self, chart_type: str, area: str, start: dt.date, end: dt.date,
               attempts: int | None = None) -> list[dict]:
        attempts = attempts or self.attempts
        params = {
            "region": self.region,
            "chartType": chart_type,
            "dateRange": "day",
            "dateFrom": start.strftime("%d-%b-%Y"),
            "dateTo": end.strftime("%d-%b-%Y"),
            "areas": area,
        }
        error: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = self._http.get(f"{self.base_url}/api/chart/", params=params)
                resp.raise_for_status()
                payload = resp.json()
                if not isinstance(payload, dict) or "Rows" not in payload:
                    raise ValueError("unexpected response shape")
                return payload["Rows"]
            except (httpx.HTTPError, ValueError) as exc:
                error = exc
                if attempt < attempts - 1:
                    time.sleep(1.5 * (attempt + 1))
        raise EirGridError(f"{area} {start:%d-%b}: {type(error).__name__} {error}".strip())

    def fetch(self, start: dt.date, end: dt.date) -> pd.DataFrame:
        """Fetch every field for each day in [start, end] (inclusive)."""
        days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
        jobs = [(ct, area, day) for day in days for ct, area in REQUESTS]
        rows: list[dict] = []
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(self._chart, ct, area, day, day) for ct, area, day in jobs]
            for future in as_completed(futures):
                try:
                    rows.extend(future.result())
                except EirGridError as exc:
                    errors.append(str(exc))
        self.last_errors = errors
        if errors:
            log.warning("%d of %d EirGrid requests failed, e.g. %s", len(errors), len(jobs), errors[0])
        frame = fill_intensity(parse_rows(rows))
        if frame.empty or frame["co2_intensity"].dropna().empty:
            detail = errors[0] if errors else "no CO2 rows in response"
            raise EirGridError(f"No carbon intensity data from EirGrid ({detail})")
        return frame


def demo_frame(start: dt.date, end: dt.date, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Realistic synthetic grid data for offline development and as a fallback.

    Wind follows slow weather-like swings, demand follows Irish daily and weekly
    shape, and carbon intensity falls as the wind + solar share rises. Actuals stop
    at ``now``; EirGrid-style forecasts run to the end of ``end``.
    """
    now = (now or pd.Timestamp.now(tz=TZ)).floor("15min")
    index = pd.date_range(
        pd.Timestamp(start, tz=TZ), pd.Timestamp(end, tz=TZ) + pd.Timedelta(hours=23, minutes=45),
        freq="15min", name="time",
    )
    rng = np.random.default_rng(int(pd.Timestamp(start).toordinal()))
    t_hours = (index - index[0]).total_seconds().to_numpy() / 3600.0
    hour = np.asarray(index.hour) + np.asarray(index.minute) / 60.0
    weekend = np.asarray(index.dayofweek >= 5)

    # Demand: overnight trough, morning ramp, evening peak, lower at weekends.
    demand = (
        3900
        + 650 * np.exp(-((hour - 18.5) ** 2) / 6)
        + 450 * np.exp(-((hour - 10.5) ** 2) / 10)
        - 750 * np.exp(-((hour - 4.5) ** 2) / 8)
        - 300 * weekend
        + rng.normal(0, 40, len(index))
    )

    # Wind: weather systems passing over several days, plus AR(1) gustiness.
    phases = rng.uniform(0, 2 * np.pi, 3)
    weather = (
        0.45
        + 0.22 * np.sin(2 * np.pi * t_hours / 97 + phases[0])
        + 0.12 * np.sin(2 * np.pi * t_hours / 41 + phases[1])
        + 0.06 * np.sin(2 * np.pi * t_hours / 13 + phases[2])
    )
    noise = np.zeros(len(index))
    for i in range(1, len(index)):
        noise[i] = 0.97 * noise[i - 1] + rng.normal(0, 0.01)
    capacity = 4800.0
    wind = np.clip(weather + noise, 0.03, 0.95) * capacity

    # Solar: autumn daylight bell curve.
    solar = np.clip(np.sin(np.pi * (hour - 7.5) / 11), 0, None) ** 1.5 * 650 * rng.uniform(0.6, 1.0)

    renewable_share = np.clip((wind + solar) / demand, 0, 0.92)
    intensity = 470 * (1 - 0.88 * renewable_share) + 25 + rng.normal(0, 6, len(index))

    frame = pd.DataFrame(index=index)
    frame["co2_intensity"] = intensity.round()
    frame["co2_emissions"] = (intensity * demand / 1000).round()
    frame["wind"] = wind.round()
    frame["solar"] = solar.round()
    frame["demand"] = demand.round()
    horizon = np.clip((index - now).total_seconds().to_numpy() / 3600.0, 0, None)
    frame["wind_fcast"] = (wind * (1 + rng.normal(0, 0.04, len(index)) * (1 + horizon / 12))).round()
    frame["demand_fcast"] = (demand + rng.normal(0, 60, len(index))).round()

    future = index > now
    frame.loc[future, ["co2_intensity", "co2_emissions", "wind", "solar", "demand"]] = np.nan
    return frame[COLUMNS]
