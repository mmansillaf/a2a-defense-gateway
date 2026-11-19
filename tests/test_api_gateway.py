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
    assert len(data["result"]["tools"]) == 14
    tool_names = [t["name"] for t in data["result"]["tools"]]
    assert "compute_procedural_deadline" in tool_names
    assert "verify_normative_validity" in tool_names
    assert "audit_sunat_cpe_xml" in tool_names


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


def test_mcp_call_audit_sunat_cpe_xml():
    sample_xml = "<Invoice><cbc:ID>F001-123</cbc:ID><cac:AccountingSupplierParty><cbc:ID>20131312955</cbc:ID></cac:AccountingSupplierParty><cac:TaxTotal><cbc:TaxAmount>18.00</cbc:TaxAmount><cbc:TaxableAmount>100.00</cbc:TaxableAmount></cac:TaxTotal><cac:LegalMonetaryTotal><cbc:PayableAmount>118.00</cbc:PayableAmount></cac:LegalMonetaryTotal></Invoice>"
    payload = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "audit_sunat_cpe_xml",
            "arguments": {
                "xml_content": sample_xml
            }
        }
    }
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    import json
    res = json.loads(data["result"]["content"][0]["text"])
    assert res["es_valido"] is True
    assert res["emisor_ruc"] == "20131312955"
    assert res["emisor_ruc_valido"] is True
    assert res["monto_total"] == 118.00
