import datetime as dt
import json
from pathlib import Path

import httpx
import pytest

import pandas as pd

from app.eirgrid import EirGridClient, EirGridError, demo_frame, fill_intensity, parse_rows

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "eirgrid_sample.json").read_text())


def test_parse_rows_builds_wide_frame():
    frame = parse_rows(FIXTURE["Rows"])
    assert len(frame) == 8
    assert str(frame.index.tz) == "Europe/Dublin"
    assert frame["co2_intensity"].iloc[0] == 128
    assert frame["wind"].iloc[1] == 2623
    # Null values and unknown fields are ignored.
    assert frame["demand_fcast"].isna().all()


def test_parse_rows_empty():
    assert parse_rows([]).empty


def test_client_chunks_and_parses(monkeypatch):
    calls = []

    def handler(request: httpx.Request):
        calls.append(dict(request.url.params))
        return httpx.Response(200, json=FIXTURE)

    client = EirGridClient(region="ROI", base_url="https://example.test")
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    frame = client.fetch(dt.date(2026, 9, 1), dt.date(2026, 9, 10))
    # One request per day per data series.
    assert len(calls) == 70
    assert all("," not in c["areas"] for c in calls)
    assert {c["chartType"] for c in calls} == {"co2", "default"}
    assert all(c["dateFrom"] == c["dateTo"] for c in calls)
    assert not frame["co2_intensity"].dropna().empty


def test_client_raises_on_http_error():
    client = EirGridClient(base_url="https://example.test")
    client._http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    client.attempts = 1  # no retry delay in tests
    with pytest.raises(EirGridError):
        client.fetch(dt.date(2026, 9, 1), dt.date(2026, 9, 1))


def test_one_failed_day_does_not_fail_the_fetch():
    def handler(request: httpx.Request):
        if request.url.params["dateFrom"] == "02-Sep-2026":
            return httpx.Response(504)
        return httpx.Response(200, json=FIXTURE)

    client = EirGridClient(base_url="https://example.test")
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    client.attempts = 1
    frame = client.fetch(dt.date(2026, 9, 1), dt.date(2026, 9, 3))
    assert not frame.empty
    assert len(client.last_errors) == 7


def test_intensity_derived_from_emissions_when_missing():
    rows = [r for r in FIXTURE["Rows"] if r["FieldName"] != "CO2_INTENSITY"]
    frame = fill_intensity(parse_rows(rows))
    # 513 tCO2/h / 3629 MW = 141 gCO2/kWh
    assert frame["co2_intensity"].iloc[0] == 141


def test_demo_frame_is_plausible():
    frame = demo_frame(dt.date(2026, 9, 1), dt.date(2026, 9, 14))
    ci = frame["co2_intensity"].dropna()
    assert 50 < ci.min() < ci.max() < 600
    assert (frame["wind"].dropna() >= 0).all()
