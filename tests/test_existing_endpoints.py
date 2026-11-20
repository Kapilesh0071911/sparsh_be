import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Tip Checkpoint API is running" in data["message"]


def test_meta():
    resp = client.get("/api/v1/meta")
    assert resp.status_code == 200
    data = resp.json()
    assert "dataset" in data or "app" in data


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_sources():
    resp = client.get("/api/v1/sources")
    assert resp.status_code == 200
    data = resp.json()
    # Checks backwards-compatible items AND contract sources
    assert "items" in data
    assert "sources" in data
    assert len(data["sources"]) > 0
    src = data["sources"][0]
    assert "id" in src
    assert "name" in src
    assert "type" in src
    assert "tips_total" in src
    assert "tips_worked" in src
    assert "shrunk_hit_rate" in src
    assert "evidence_level" in src
    assert "label" in src


def test_coordination_flags():
    resp = client.get("/api/v1/coordination/flags")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data


def test_archive_chain_head():
    resp = client.get("/api/v1/archive/chain/head")
    assert resp.status_code == 200
    data = resp.json()
    assert "seq" in data


def test_eval_results():
    resp = client.get("/api/v1/eval/results")
    assert resp.status_code == 200
    data = resp.json()
    assert "arms" in data
