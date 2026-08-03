import pytest
from unittest.mock import AsyncMock, patch
from app.llm.client import OllamaClient, OllamaConnectionError


def test_estimate_tokens_string():
    text = "Hello world! This is a simple test string."
    count = OllamaClient.estimate_tokens(text)
    assert count > 0
    assert count == len(text) // 4


def test_estimate_tokens_messages():
    messages = [
        {"role": "user", "content": "Hello, KAI!"},
        {"role": "assistant", "content": "Hello! How can I help you today?"}
    ]
    count = OllamaClient.estimate_tokens(messages)
    assert count > 0
    # Overheads + lengths
    assert count >= 10


def test_client_default_configuration():
    client = OllamaClient()
    assert client.default_model == "qwen3:8b"
    assert client.default_embed_model == "nomic-embed-text"
    assert client.default_keep_alive == "30m"


def test_models_endpoint(client):
    response = client.get("/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert isinstance(data["models"], list)


def test_ollama_connection_error_handling():
    async def _test():
        client = OllamaClient(base_url="http://invalid-host-99999:11434/v1", max_retries=1)
        with pytest.raises(OllamaConnectionError) as exc_info:
            await client.chat_completion(messages=[{"role": "user", "content": "hi"}])
        assert "Could not connect to local Ollama server" in str(exc_info.value)

    import asyncio
    asyncio.run(_test())
