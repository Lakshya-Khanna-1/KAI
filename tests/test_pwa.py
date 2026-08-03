import json
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app

client = TestClient(app)


def test_static_files_served():
    resp_index = client.get("/")
    assert resp_index.status_code == 200
    assert "KAI — Personal AI Assistant" in resp_index.text

    resp_manifest = client.get("/manifest.json")
    assert resp_manifest.status_code == 200
    assert "KAI Personal Assistant" in resp_manifest.text

    resp_sw = client.get("/sw.js")
    assert resp_sw.status_code == 200
    assert "CACHE_NAME" in resp_sw.text

    resp_css = client.get("/style.css")
    assert resp_css.status_code == 200
    assert "--bg-primary" in resp_css.text

    resp_js = client.get("/app.js")
    assert resp_js.status_code == 200
    assert "handleSSEEvent" in resp_js.text


def test_auth_verification(db_session: Session):
    with patch.object(settings, "API_TOKEN", "secret-token-123"):
        # Without token -> 401
        res_no_auth = client.post("/api/chat/stream", json={"message": "hello"})
        assert res_no_auth.status_code == 401

        # With invalid token -> 401
        res_bad_auth = client.post("/api/chat/stream", json={"message": "hello"}, headers={"Authorization": "Bearer wrong-token"})
        assert res_bad_auth.status_code == 401

        # With valid token -> 200 streaming
        with patch("app.llm.client.ollama_client.chat_completion", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "choices": [{"message": {"role": "assistant", "content": "Hello user"}}]
            }
            res_valid = client.post(
                "/api/chat/stream",
                json={"message": "hello"},
                headers={"Authorization": "Bearer secret-token-123"}
            )
            assert res_valid.status_code == 200
            assert "text/event-stream" in res_valid.headers["content-type"]


def test_chat_stream_endpoint(db_session: Session):
    with patch.object(settings, "API_TOKEN", ""):
        with patch("app.llm.client.ollama_client.chat_completion", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {
                "choices": [{"message": {"role": "assistant", "content": "I am KAI."}}]
            }
            res = client.post("/api/chat/stream", json={"message": "Who are you?"})
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        body_text = res.text
        assert "data: " in body_text
        assert "I am KAI." in body_text
