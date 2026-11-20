import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.scoring import run_scoring_job

client = TestClient(app)


@pytest.fixture(scope="module")
def auth_headers():
    resp = client.post("/api/v1/auth/login", json={"email": "demo@signalnoise.app", "password": "demo1234"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_scoring_job_and_alerts(auth_headers):
    # Execute manual scoring job
    run_scoring_job()

    # Verify alerts endpoint
    resp = client.get("/api/v1/alerts", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "unread_count" in data
    assert "alerts" in data
    assert len(data["alerts"]) >= 3

    # Check alert structure
    alert = data["alerts"][0]
    assert "id" in alert
    assert "type" in alert
    assert "results" in alert
    assert "d7" in alert["results"]
    assert "d30" in alert["results"]
    assert "d90" in alert["results"]

    # Mark single alert as read
    first_unread = next((a for a in data["alerts"] if not a["read"]), None)
    if first_unread:
        resp_read = client.post(f"/api/v1/alerts/{first_unread['id']}/read", headers=auth_headers)
        assert resp_read.status_code == 200
        assert resp_read.json()["unread_count"] == data["unread_count"] - 1

    # Mark all read
    resp_all = client.post("/api/v1/alerts/read_all", headers=auth_headers)
    assert resp_all.status_code == 200
    assert resp_all.json()["unread_count"] == 0


def test_insights(auth_headers):
    resp = client.get("/api/v1/insights", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "insights" in data
    insights = data["insights"]
    assert len(insights) > 0
    jump_insight = next((i for i in insights if i["id"] == "i_jump_loss"), None)
    assert jump_insight is not None
    assert "8%+ jump" in jump_insight["text"]
    assert jump_insight["evidence_count"] >= 2
