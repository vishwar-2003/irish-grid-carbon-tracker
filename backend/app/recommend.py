"""Turn a carbon intensity forecast into advice: when to run appliances."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Typical household figures. Energy per cycle varies by model and programme; these are
# reasonable mid-range values used only to estimate the CO2 difference between times.
APPLIANCES = {
    "dishwasher": {"label": "Dishwasher", "kwh": 1.0, "hours": 2},
    "washing_machine": {"label": "Washing machine", "kwh": 0.8, "hours": 2},
    "tumble_dryer": {"label": "Tumble dryer", "kwh": 2.5, "hours": 2},
    "ev_charge": {"label": "EV charge (7 kW, 4 h)", "kwh": 28.0, "hours": 4},
    "immersion": {"label": "Immersion heater", "kwh": 3.0, "hours": 1},
}

# Fixed bands in gCO2/kWh so "low" means the same thing every day.
BANDS = [(200, "low"), (300, "moderate"), (float("inf"), "high")]


def band(intensity: float | None) -> str | None:
    if intensity is None or pd.isna(intensity):
        return None
    for limit, name in BANDS:
        if intensity < limit:
            return name
    return "high"


@dataclass
class Window:
    start: str
    end: str
    avg_intensity: float


def windows(points: list[dict], hours: int) -> list[Window]:
    """Every contiguous run of ``hours`` forecast hours, in time order."""
    out = []
    for i in range(len(points) - hours + 1):
        chunk = points[i : i + hours]
        avg = sum(p["intensity"] for p in chunk) / hours
        end = pd.Timestamp(chunk[-1]["time"]) + pd.Timedelta(hours=1)
        out.append(Window(chunk[0]["time"], end.isoformat(), round(avg, 1)))
    return out


def best_window(points: list[dict], hours: int) -> Window | None:
    found = windows(points, hours)
    return min(found, key=lambda w: w.avg_intensity) if found else None


def recommend(points: list[dict], appliance: str) -> dict | None:
    spec = APPLIANCES[appliance]
    hours = spec["hours"]
    found = windows(points, hours)
    if not found:
        return None
    best = min(found, key=lambda w: w.avg_intensity)
    now = found[0]
    worst = max(found, key=lambda w: w.avg_intensity)
    kwh = spec["kwh"]
    saving_g = (now.avg_intensity - best.avg_intensity) * kwh
    return {
        "appliance": appliance,
        "label": spec["label"],
        "kwh": kwh,
        "hours": hours,
        "best": best.__dict__,
        "start_now": now.__dict__,
        "worst": worst.__dict__,
        "co2_best_g": round(best.avg_intensity * kwh),
        "co2_now_g": round(now.avg_intensity * kwh),
        "co2_worst_g": round(worst.avg_intensity * kwh),
        "saving_vs_now_g": round(max(saving_g, 0)),
        "saving_vs_now_pct": round(100 * max(saving_g, 0) / (now.avg_intensity * kwh), 1)
        if now.avg_intensity else 0.0,
        "run_now": best.start == now.start,
    }


def greenest_hours(points: list[dict], count: int = 4) -> list[dict]:
    ranked = sorted(points, key=lambda p: p["intensity"])[:count]
    return sorted(ranked, key=lambda p: p["time"])
