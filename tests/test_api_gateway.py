from api_gateway import app
from fastapi.testclient import TestClient

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
    assert len(data["result"]["tools"]) == 13
    tool_names = [t["name"] for t in data["result"]["tools"]]
    assert "compute_procedural_deadline" in tool_names
    assert "verify_normative_validity" in tool_names


def test_mcp_call_compute_procedural_deadline():
    payload = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "compute_procedural_deadline",
            "arguments": {
                "fecha_inicio": "2026-04-01",
                "dias_plazo": 3,
                "tipo_dias": "HABILES_JUDICIALES"
            }
        }
    }
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert data["result"]["isError"] is False
    content_text = data["result"]["content"][0]["text"]
    import json
    res = json.loads(content_text)
    assert res["dias_contados"] == 3
    assert res["fecha_vencimiento"] == "2026-04-08"
    assert "DEADLINE-HAB" in res["doc_id"]
