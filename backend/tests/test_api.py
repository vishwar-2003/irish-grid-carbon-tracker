import os

os.environ["DATA_MODE"] = "demo"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_dashboard_shape():
    body = client.get("/api/dashboard").json()
    assert body["meta"]["source"] == "demo"
    assert body["current"]["intensity"] > 0
    assert len(body["forecast"]) == 24
    assert len(body["appliances"]) == 5
    assert body["model"]["mae"] is not None


def test_unknown_appliance_is_404():
    assert client.get("/api/recommendations", params={"appliance": "toaster"}).status_code == 404


def test_single_appliance():
    body = client.get("/api/recommendations", params={"appliance": "ev_charge"}).json()
    assert [a["appliance"] for a in body["appliances"]] == ["ev_charge"]
