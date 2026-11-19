from fastapi.testclient import TestClient
from api_gateway import app

client = TestClient(app)


def test_root_landing_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "A2A Defense &amp; Monetization Gateway" in response.text or "A2A Defense & Monetization Gateway" in response.text
    assert "https://a2a.vilmamonroy.com/mcp" in response.text
    assert "get_alpha_intelligence_feed" in response.text
    assert "arbitrate_dispute" in response.text


def test_mcp_initialize():
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {}
    }
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["result"]["serverInfo"]["name"] == "a2a-defense-monetization-gateway"


def test_mcp_tools_list():
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["result"]["tools"]) == 11
