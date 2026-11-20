import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def auth_headers():
    # Login as demo user
    resp = client.post("/api/v1/auth/login", json={"email": "demo@signalnoise.app", "password": "demo1234"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_gate_validation_missing_fields(auth_headers):
    # Attempting to lock a decision with empty/missing fields
    resp = client.post("/api/v1/decisions/lock", json={"decision_id": "d_demo_1"}, headers=auth_headers)
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "gate_incomplete"
    missing = data["error"]["details"]["missing_fields"]
    assert "action" in missing
    assert "timeframe_days" in missing
    assert "exit_target" in missing
    assert "max_loss_pct" in missing
    assert "confidence" in missing


def test_gate_validation_invalid_values(auth_headers):
    # Invalid timeframe (negative), invalid exit_target (zero), invalid max_loss_pct (> 100), invalid confidence (> 5)
    resp = client.post(
        "/api/v1/decisions/lock",
        json={
            "decision_id": "d_demo_1",
            "action": "invalid_action",
            "timeframe_days": -10,
            "exit_target": 0,
            "max_loss_pct": 120,
            "confidence": 6,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "gate_incomplete"
    missing = data["error"]["details"]["missing_fields"]
    assert "action" in missing
    assert "timeframe_days" in missing
    assert "exit_target" in missing
    assert "max_loss_pct" in missing
    assert "confidence" in missing


def test_gate_validation_success(auth_headers):
    # Valid payload locks the decision
    resp = client.post(
        "/api/v1/decisions/lock",
        json={
            "decision_id": "d_demo_1",
            "action": "bought",
            "timeframe_days": 30,
            "exit_target": 950.0,
            "max_loss_pct": 8.0,
            "confidence": 4,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "decision" in data
    decision = data["decision"]
    assert decision["id"] == "d_demo_1"
    assert decision["action"] == "bought"
    assert decision["timeframe_days"] == 30
    assert decision["exit_target"] == 950.0
    assert decision["max_loss_pct"] == 8.0
    assert decision["confidence"] == 4
    assert decision["locked_at"] is not None
