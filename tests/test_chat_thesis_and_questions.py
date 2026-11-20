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


def test_no_thesis_chain_before_thesis(auth_headers):
    # Step 1: Initial intake with tip text
    resp = client.post(
        "/api/v1/chat/message",
        data={"text": "Neel sent me a tip: buy Tata Motors targeting 950."},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["stage"] == "awaiting_thesis"
    assert data["questions_asked"] == 0

    block_types = [b["type"] for b in data["blocks"]]
    assert "claim_card" in block_types
    assert "source_record" in block_types
    assert "context_card" in block_types
    assert "text" in block_types

    # Hard rule: No thesis_chain is ever returned before the user has written a thesis
    assert "thesis_chain" not in block_types


def test_one_question_per_turn_and_6_question_cap(auth_headers):
    # Step 1: Start new conversation with a tip
    resp1 = client.post(
        "/api/v1/chat/message",
        data={"text": "Neel says Tata Motors will rally to 950 soon on EV fleet deal."},
        headers=auth_headers,
    )
    assert resp1.status_code == 200
    d1 = resp1.json()
    conv_id = d1["conversation_id"]
    assert d1["stage"] == "awaiting_thesis"

    # Step 2: User provides their own thesis reasoning
    thesis_text = "I think Tata Motors EV division will maintain 70% market share and raw material battery costs will fall."
    resp2 = client.post(
        "/api/v1/chat/message",
        data={"conversation_id": conv_id, "text": thesis_text},
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    d2 = resp2.json()

    # Rule: Now thesis_chain must be present
    btypes2 = [b["type"] for b in d2["blocks"]]
    assert "thesis_chain" in btypes2
    assert d2["stage"] == "questioning"
    assert d2["questions_asked"] == 1

    # Exactly one question text block returned
    text_blocks = [b for b in d2["blocks"] if b["type"] == "text"]
    assert len(text_blocks) == 1

    # Quick replies include __dont_know__
    assert any(q["value"] == "__dont_know__" for q in d2["quick_replies"])

    # Step 3: Answer questions one by one (verifying one question per turn)
    current_q_asked = d2["questions_asked"]
    while current_q_asked < 6:
        resp_q = client.post(
            "/api/v1/chat/message",
            data={"conversation_id": conv_id, "text": "__dont_know__"},
            headers=auth_headers,
        )
        assert resp_q.status_code == 200
        dq = resp_q.json()

        if dq["stage"] == "questioning":
            assert dq["questions_asked"] == current_q_asked + 1
            current_q_asked = dq["questions_asked"]
            # Verify one question text block per turn
            q_text_blocks = [b for b in dq["blocks"] if b["type"] == "text"]
            assert len(q_text_blocks) == 1
        elif dq["stage"] == "gate":
            # Reached gate
            break

    # After at most 6 questions, stage must be gate and contain decision_gate block
    if dq["stage"] != "gate":
        resp_final = client.post(
            "/api/v1/chat/message",
            data={"conversation_id": conv_id, "text": "My final answer"},
            headers=auth_headers,
        )
        dq = resp_final.json()

    assert dq["stage"] == "gate"
    final_btypes = [b["type"] for b in dq["blocks"]]
    assert "decision_gate" in final_btypes
    gate_block = next(b for b in dq["blocks"] if b["type"] == "decision_gate")
    assert gate_block["locked"] is False
    assert "exit_target" in gate_block["required_fields"]
