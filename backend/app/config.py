"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # "auto" tries EirGrid and falls back to synthetic demo data if it is unreachable.
    # "live" never falls back. "demo" never calls EirGrid (useful offline / in CI).
    data_mode: str = os.getenv("DATA_MODE", "auto").lower()

    # EirGrid region: ROI (Republic of Ireland), NI (Northern Ireland) or ALL (all-island).
    region: str = os.getenv("GRID_REGION", "ROI").upper()

    # Days of history used to train the forecasting model.
    training_days: int = int(os.getenv("TRAINING_DAYS", "21"))

    # Cache lifetimes in seconds.
    recent_cache_ttl: int = int(os.getenv("RECENT_CACHE_TTL", "600"))
    history_cache_ttl: int = int(os.getenv("HISTORY_CACHE_TTL", "21600"))
    model_ttl: int = int(os.getenv("MODEL_TTL", "21600"))

    eirgrid_base_url: str = os.getenv("EIRGRID_BASE_URL", "https://www.smartgriddashboard.com")
    request_timeout: float = float(os.getenv("REQUEST_TIMEOUT", "30"))

    allowed_origins: list[str] = field(
        default_factory=lambda: _list(os.getenv("ALLOWED_ORIGINS", "*"))
    )


settings = Settings()
