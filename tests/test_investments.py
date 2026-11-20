import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module")
def auth_headers():
    resp = client.post("/api/v1/auth/login", json={"email": "demo@signalnoise.app", "password": "demo1234"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_investment_confirm_only_on_complete_purchase(auth_headers):
    # 1. Intentions should NEVER create an investment_confirm block
    resp_intention = client.post(
        "/api/v1/chat/message",
        data={"text": "I am thinking of buying Tata Motors next week."},
        headers=auth_headers,
    )
    assert resp_intention.status_code == 200
    btypes = [b["type"] for b in resp_intention.json()["blocks"]]
    assert "investment_confirm" not in btypes

    # 2. Questions should NEVER create an investment_confirm block
    resp_question = client.post(
        "/api/v1/chat/message",
        data={"text": "What do you think of Tata Motors at current levels?"},
        headers=auth_headers,
    )
    assert resp_question.status_code == 200
    btypes = [b["type"] for b in resp_question.json()["blocks"]]
    assert "investment_confirm" not in btypes

    # 3. Incomplete purchase statements (missing qty, price, or date) should NOT create one
    resp_incomplete = client.post(
        "/api/v1/chat/message",
        data={"text": "I bought some Tata Motors shares yesterday."},
        headers=auth_headers,
    )
    assert resp_incomplete.status_code == 200
    btypes = [b["type"] for b in resp_incomplete.json()["blocks"]]
    assert "investment_confirm" not in btypes

    # 4. Completed purchase statement with ticker, quantity, avg price, and date MUST create one
    resp_complete = client.post(
        "/api/v1/chat/message",
        data={"text": "I bought 10 shares of TATAMOTORS at 200 on 2026-11-19"},
        headers=auth_headers,
    )
    assert resp_complete.status_code == 200
    d = resp_complete.json()
    btypes = [b["type"] for b in d["blocks"]]
    assert "investment_confirm" in btypes

    confirm_block = next(b for b in d["blocks"] if b["type"] == "investment_confirm")
    token = confirm_block["confirm_token"]
    assert token is not None
    assert confirm_block["draft"]["ticker"] == "TATAMOTORS"
    assert confirm_block["draft"]["quantity"] == 10
    assert confirm_block["draft"]["avg_price"] == 200
    assert confirm_block["draft"]["purchase_date"] == "2026-11-19"

    # 5. Confirm investment via POST /investments/confirm
    resp_confirm = client.post(
        "/api/v1/investments/confirm",
        json={"confirm_token": token},
        headers=auth_headers,
    )
    assert resp_confirm.status_code == 201, resp_confirm.text
    inv_data = resp_confirm.json()["investment"]
    assert inv_data["ticker"] == "TATAMOTORS"
    assert inv_data["quantity"] == 10
    assert inv_data["avg_price"] == 200

    # 6. Verify it appears in GET /investments
    resp_list = client.post if False else client.get("/api/v1/investments", headers=auth_headers)
    assert resp_list.status_code == 200
    invs = resp_list.json()["investments"]
    assert any(inv["id"] == inv_data["id"] for inv in invs)
