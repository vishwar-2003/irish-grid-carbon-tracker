"""Cached access to grid data, with automatic fallback to demo data."""

from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from dataclasses import dataclass

import pandas as pd

from .config import settings
from .eirgrid import TZ, EirGridClient, EirGridError, demo_frame

log = logging.getLogger(__name__)

# After EirGrid fails, wait this long before trying again so page loads stay fast.
FAILURE_COOLDOWN = 120


@dataclass
class GridData:
    frame: pd.DataFrame  # 15-minute, tz-aware index, actuals + EirGrid forecasts
    source: str  # "live" or "demo"
    fetched_at: pd.Timestamp
    note: str | None = None


class GridDataService:
    """Splits data into stable history (cached for hours) and a recent window
    (yesterday to tomorrow, cached for minutes) so the live view stays fresh
    without re-downloading weeks of history on every request."""

    def __init__(self, client: EirGridClient | None = None):
        self.client = client or EirGridClient()
        self._lock = threading.Lock()
        self._history: tuple[float, dt.date, pd.DataFrame] | None = None
        self._recent: tuple[float, pd.DataFrame] | None = None
        self._last: GridData | None = None
        self._failed_at: float = 0.0
        self._last_error: str | None = None
        self.history_error: str | None = None

    def _today(self) -> dt.date:
        return pd.Timestamp.now(tz=TZ).date()

    def _live(self) -> pd.DataFrame:
        today = self._today()
        now = time.time()

        # Recent window first: this is what the live view needs.
        if self._recent is None or now - self._recent[0] > settings.recent_cache_ttl:
            recent = self.client.fetch(today - dt.timedelta(days=1), today + dt.timedelta(days=1))
            self._recent = (now, recent)

        # Older history only feeds model training, so a failure here is not fatal.
        history_end = today - dt.timedelta(days=2)
        history_start = today - dt.timedelta(days=settings.training_days)
        if (
            self._history is None
            or now - self._history[0] > settings.history_cache_ttl
            or self._history[1] != history_end
        ):
            try:
                self._history = (now, history_end, self.client.fetch(history_start, history_end))
                self.history_error = None
            except EirGridError as exc:
                log.warning("History unavailable, continuing with recent data only: %s", exc)
                self.history_error = str(exc)
                if self._history is None:
                    # Retry history after the cooldown rather than on every request.
                    self._history = (now - settings.history_cache_ttl + FAILURE_COOLDOWN,
                                     history_end, self._recent[1].iloc[0:0])

        combined = pd.concat([self._history[2], self._recent[1]])
        return combined[~combined.index.duplicated(keep="last")].sort_index()

    def _demo(self) -> pd.DataFrame:
        today = self._today()
        return demo_frame(today - dt.timedelta(days=settings.training_days), today + dt.timedelta(days=1))

    def _fallback(self, reason: str) -> GridData:
        if self._last is not None and self._last.source == "live":
            return GridData(self._last.frame, "live", self._last.fetched_at,
                            note=f"EirGrid is not responding ({reason}); showing the most recent data received.")
        return GridData(self._demo(), "demo", pd.Timestamp.now(tz=TZ),
                        note=f"EirGrid is not responding ({reason}); showing simulated data.")

    def get(self) -> GridData:
        with self._lock:
            mode = settings.data_mode
            if mode == "demo":
                return GridData(self._demo(), "demo", pd.Timestamp.now(tz=TZ), note="Demo mode: simulated data.")

            if mode == "auto" and time.time() - self._failed_at < FAILURE_COOLDOWN:
                return self._fallback(self._last_error or "unknown error")

            try:
                frame = self._live()
            except EirGridError as exc:
                log.warning("EirGrid unavailable: %s", exc)
                if mode == "live":
                    raise
                self._failed_at = time.time()
                self._last_error = str(exc)
                return self._fallback(self._last_error)

            self._failed_at = 0.0
            note = None
            if self.history_error:
                note = "Older EirGrid history is unavailable right now, so the forecast uses fewer days."
            self._last = GridData(frame, "live", pd.Timestamp.now(tz=TZ), note=note)
            return self._last
