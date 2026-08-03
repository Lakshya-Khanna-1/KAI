from app.llm.registry import discover_tools, discover_routers


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "status" in data
    assert data["database"] == "ok"
    assert "ollama" in data
    assert "reachable" in data["ollama"]


def test_dummy_module_router_discovery(client):
    response = client.get("/dummy/ping")
    assert response.status_code == 200
    assert response.json() == {"message": "pong"}


def test_dummy_module_tools_discovery():
    tools = discover_tools()
    tool_names = [t["function"]["name"] for t in tools if "function" in t]
    assert "dummy_echo" in tool_names
