import pytest
import os
import shutil
from fastapi.testclient import TestClient
from pathlib import Path

# Set up test environment before imports
TEST_DATA_ROOT = Path("tests/marius_test_data")
os.environ["MARIUS_DATA_ROOT"] = str(TEST_DATA_ROOT)
os.environ["MCHARNESS_DATA_ROOT"] = str(TEST_DATA_ROOT)
os.environ["MARIUS_TELEGRAM_ENABLED"] = "0"

from src.warden.app import app
from src.marius.tools import redact_secrets

@pytest.fixture(autouse=True)
def setup_teardown():
    if TEST_DATA_ROOT.exists():
        shutil.rmtree(TEST_DATA_ROOT)
    TEST_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    yield
    if TEST_DATA_ROOT.exists():
        shutil.rmtree(TEST_DATA_ROOT)

def test_marius_health():
    client = TestClient(app)
    response = client.get("/api/mcharness/marius/health")
    assert response.status_code == 200
    assert response.json()["status"] == "OK"

def test_marius_status_redaction():
    client = TestClient(app)
    response = client.get("/api/mcharness/marius/status")
    assert response.status_code == 200
    data = response.json()
    assert "git" in data
    assert "services" in data
    
    # Verify redaction logic directly
    secret_text = "My key is sk-1234567890abcdef1234567890abcdef"
    redacted = redact_secrets(secret_text)
    assert "[REDACTED]" in redacted
    assert "sk-1234567890" not in redacted

def test_marius_chat_fallback():
    client = TestClient(app)
    # Ensure OLLAMA_URL points to nothing valid
    os.environ["OLLAMA_URL"] = "http://localhost:1/invalid"
    response = client.post("/api/mcharness/marius/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert "fallback" in response.json()["provider"]
    assert "unavailable" in response.json()["response"].lower()

def test_marius_memory_cycle():
    client = TestClient(app)
    # Remember
    rem_resp = client.post(
        "/api/mcharness/marius/memory/remember", 
        json={"content": "Marius is back", "category": "test"}
    )
    assert rem_resp.status_code == 200
    
    # Recall
    rec_resp = client.get("/api/mcharness/marius/memory/recall?q=Marius")
    assert rec_resp.status_code == 200
    results = rec_resp.json()
    assert len(results) > 0
    assert results[0]["content"] == "Marius is back"

def test_telegram_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MARIUS_TELEGRAM_ENABLED", raising=False)
    from src.marius.bot import start_bot
    # Should return None and not start a thread
    thread = start_bot()
    assert thread is None

def test_marius_projects():
    client = TestClient(app)
    response = client.get("/api/mcharness/marius/projects")
    assert response.status_code == 200
    projs = response.json()
    assert any(p["id"] == "warden" for p in projs)
    assert any(p["id"] == "hybrid" for p in projs)

def test_marius_handoff():
    client = TestClient(app)
    response = client.post(
        "/api/mcharness/marius/handoff/agent-prompt", 
        json={"target": "codex", "context": "Fixing bugs"}
    )
    assert response.status_code == 200
    assert "CODEX HANDOFF" in response.json()["prompt"]
