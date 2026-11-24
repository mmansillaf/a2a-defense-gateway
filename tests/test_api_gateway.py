import json
from datetime import UTC

from api_gateway import app, server
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


def test_robots_txt_and_sitemap():
    resp_robots = client.get("/robots.txt")
    assert resp_robots.status_code == 200
    assert "User-agent: *" in resp_robots.text
    assert "Allow: /mcp" in resp_robots.text

    resp_sitemap = client.get("/sitemap.xml")
    assert resp_sitemap.status_code == 200
    assert "https://a2a.vilmamonroy.com/mcp" in resp_sitemap.text

    resp_auth = client.get("/.well-known/mcp-registry-auth")
    assert resp_auth.status_code == 200
    assert "v=MCPv1; k=ed25519" in resp_auth.text


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
    assert len(data["result"]["tools"]) == len(server.list_tools())
    tool_names = [t["name"] for t in data["result"]["tools"]]
    assert "compute_procedural_deadline" in tool_names
    assert "compute_us_procedural_deadline" in tool_names
    assert "validate_bluebook_citation" in tool_names
    assert "search_us_court_opinions" in tool_names
    assert "verify_normative_validity" in tool_names
    assert "audit_sunat_cpe_xml" in tool_names
    assert "audit_excel_macro_forensics" in tool_names
    assert "match_peruvian_procurement" in tool_names
    assert "query_deep_context_archive" in tool_names
    assert "publish_enterprise_artifact" in tool_names
    assert "generate_audio_briefing" in tool_names
    assert "sync_tabular_ledger" in tool_names


def test_mcp_call_audit_excel_macro_forensics():
    payload = {
        "jsonrpc": "2.0",
        "id": 105,
        "method": "tools/call",
        "params": {
            "name": "audit_excel_macro_forensics",
            "arguments": {
                "vba_code": "Sub Test()\n Shell \"cmd.exe\"\nEnd Sub",
                "auto_deobfuscate": True,
            },
        },
    }
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 105
    res = json.loads(data["result"]["content"][0]["text"])
    assert res["is_suspicious"] is True
    assert "Shell" in res["detected_shell_invocations"]


def test_mcp_call_match_peruvian_procurement():
    payload = {
        "jsonrpc": "2.0",
        "id": 106,
        "method": "tools/call",
        "params": {
            "name": "match_peruvian_procurement",
            "arguments": {
                "requirement_text": "Servicio de desarrollo de software para mesa de partes virtual",
            },
        },
    }
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 106
    res = json.loads(data["result"]["content"][0]["text"])
    assert res["is_match"] is True
    assert len(res["matched_clusters"]) >= 1


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


def test_mcp_call_compute_us_procedural_deadline():
    payload = {
        "jsonrpc": "2.0",
        "id": 35,
        "method": "tools/call",
        "params": {
            "name": "compute_us_procedural_deadline",
            "arguments": {
                "trigger_date": "2026-06-01",
                "period_days": 14,
                "jurisdiction": "FEDERAL",
                "service_method": "POSTAL_MAIL"
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
    assert res["deadline_date"] == "2026-06-18"
    assert res["service_extension_days"] == 3
    assert "US-DEADLINE-FEDERAL" in res["doc_id"]


def test_mcp_call_validate_bluebook_citation():
    payload = {
        "jsonrpc": "2.0",
        "id": 36,
        "method": "tools/call",
        "params": {
            "name": "validate_bluebook_citation",
            "arguments": {
                "raw_citation": "Ashcroft v. Iqbal, 556 U.S. 662 (2009)",
                "strict_caselaw_lookup": True
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
    assert res["is_valid_format"] is True
    assert res["case_name"] == "Ashcroft v. Iqbal"
    assert res["precedent_status"] == "GOOD_LAW"
    assert "BLUEBOOK-556-U.S.-662-2009" in res["doc_id"]


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


def test_white_march_headers_and_quota_consumption():
    from api_gateway import white_march
    headers = {"X-Agent-ID": "test_agent_alpha_99"}
    resp = client.get("/api/v1/tools", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("X-White-March-Status") == "ACTIVE"
    assert int(resp.headers.get("X-White-March-Days-Left", "0")) > 0
    quota_header = resp.headers.get("X-Free-Quota-Remaining")
    assert f"/{white_march.daily_limit}" in quota_header


def test_white_march_quota_exhaustion_returns_l402_challenge():
    agent_id = "test_agent_exhaustion_99"
    headers = {"X-Agent-ID": agent_id}

    # Consumir la cuota diaria gratuita
    from datetime import datetime

    from api_gateway import white_march
    today_str = datetime.now(UTC).strftime('%Y-%m-%d')
    today_key = f"{today_str}:{agent_id}"
    with white_march._lock:
        white_march._daily_usage[today_key] = white_march.daily_limit

    # La siguiente llamada debe rebotar con HTTP 402 L402
    resp = client.post("/api/v1/tools/call", json={"name": "get_alpha_intelligence_feed", "arguments": {}}, headers=headers)
    assert resp.status_code == 402
    assert "L402 macaroon=" in resp.headers.get("WWW-Authenticate", "")
    assert resp.headers.get("X-Free-Quota-Remaining") == f"0/{white_march.daily_limit}"
    data = resp.json()
    assert data["error"] == "L402_PAYMENT_REQUIRED"
    assert "invoice_bolt11" in data["challenge"]


def test_white_march_l402_authorization_bypass():
    from api_gateway import server, white_march
    agent_id = "test_agent_vip_paying"
    from datetime import datetime
    today_str = datetime.now(UTC).strftime('%Y-%m-%d')
    today_key = f"{today_str}:{agent_id}"
    with white_march._lock:
        white_march._daily_usage[today_key] = white_march.daily_limit  # Cuota agotada

    # Generar token L402 válido pagado
    challenge, preimage = server.l402_gateway.create_challenge(
        service="gateway_access",
        amount_sats=50,
        client_id=agent_id,
        ttl_seconds=300,
    )
    auth_header = f"L402 {challenge.macaroon_b64}:{preimage.hex()}"
    headers = {"X-Agent-ID": agent_id, "Authorization": auth_header}

    # Con L402 debe ingresar con 200 OK y cuota UNLIMITED
    resp = client.get("/api/v1/tools", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("X-Free-Quota-Remaining") == "UNLIMITED"


# =====================================================================
# DASHBOARD & AUTHENTICATION UNIT TESTS
# =====================================================================

def test_login_page_renders():
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "A2A Control Panel" in resp.text
    assert "Autenticación Administrativa" in resp.text


def test_login_invalid_credentials():
    resp = client.post("/api/v1/auth/login", json={"username": "wrong", "password": "bad"})
    assert resp.status_code == 401
    assert "Credenciales inválidas" in resp.json()["detail"]


def test_dashboard_unauthenticated_redirects():
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code in [302, 303, 307]
    assert resp.headers["location"] == "/login"


def test_login_success_and_authenticated_dashboard():
    # Login con credenciales por defecto
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "a2a-defense-2026-master-key"}
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["status"] == "AUTHENTICATED"
    assert "a2a_session" in login_resp.cookies

    session_cookie = login_resp.cookies["a2a_session"]

    # Acceso al dashboard con cookie
    dash_resp = client.get("/dashboard", cookies={"a2a_session": session_cookie})
    assert dash_resp.status_code == 200
    assert "A2A DEFENSE GATEWAY" in dash_resp.text
    assert "LIVE TELEMETRY STREAM" in dash_resp.text

    # Acceso a métricas en vivo
    metrics_resp = client.get("/api/v1/dashboard/metrics", cookies={"a2a_session": session_cookie})
    assert metrics_resp.status_code == 200
    data = metrics_resp.json()
    assert data["gateway"]["status"] == "ONLINE"
    assert data["why_trail"]["status"] == "VALID"
    assert data["moltbook"]["karma"] >= 16
    assert "recent_events" in data

    # Logout
    logout_resp = client.post("/api/v1/auth/logout", cookies={"a2a_session": session_cookie})
    assert logout_resp.status_code == 200
    assert logout_resp.json()["status"] == "LOGGED_OUT"

    # Intento de acceso posterior -> redirección a login
    after_dash = client.get("/dashboard", cookies={"a2a_session": session_cookie}, follow_redirects=False)
    assert after_dash.status_code in [302, 303, 307]


def test_financial_policy_gateway_endpoints():
    client = TestClient(app)

    # 1. Evaluar intención de pago permitida
    intent = {
        "agent_id": "test_agent_gw",
        "target_url": "https://api.proveedor-verificado.com/v1/service",
        "amount_usd": 0.15,
        "method": "POST",
        "payload": {"query": "valid"},
    }
    resp_eval = client.post("/api/v1/policy/evaluate", json=intent)
    assert resp_eval.status_code == 200
    data_eval = resp_eval.json()
    assert data_eval["decision"] == "ALLOWED"
    assert data_eval["status_code"] == 200

    # 2. Consultar auditoría
    resp_audit = client.get("/api/v1/policy/audit", params={"agent_id": "test_agent_gw"})
    assert resp_audit.status_code == 200
    data_audit = resp_audit.json()
    assert "status_breakdown" in data_audit
    assert "active_circuits" in data_audit

    # 3. Orquestar Saga multi-agente
    saga_payload = {
        "saga_id": "SAGA-GW-01",
        "steps": [
            {"step_id": "ST1", "agent_id": "ag_1", "service_name": "step1", "action_type": "EXECUTE", "cost_usd": 0.05},
            {"step_id": "ST2", "agent_id": "ag_2", "service_name": "step2", "action_type": "EXECUTE", "cost_usd": 0.05},
        ],
    }
    resp_saga = client.post("/api/v1/policy/saga", json=saga_payload)
    assert resp_saga.status_code == 200
    data_saga = resp_saga.json()
    assert data_saga["status"] == "COMPLETED"
    assert data_saga["steps_executed"] == 2


def test_dashboard_and_login_inline_javascript_syntax():
    """Valida determinísticamente que el JavaScript embebido en DASHBOARD_HTML y LOGIN_HTML no contenga SyntaxError."""
    import os
    import shutil
    import subprocess
    import tempfile

    if shutil.which("node") is None:
        pytest.skip("NodeJS no está instalado en este host; validación sintáctica JS omitida.")

    try:
        from api_gateway import DASHBOARD_HTML, LOGIN_HTML
    except ImportError:
        from agents.api_gateway import DASHBOARD_HTML, LOGIN_HTML

    for name, html in [("DASHBOARD_HTML", DASHBOARD_HTML), ("LOGIN_HTML", LOGIN_HTML)]:
        start = html.find("<script>")
        while start != -1:
            end = html.find("</script>", start)
            assert end != -1, f"Etiqueta </script> no cerrada en {name}"
            js_code = html[start + 8 : end]
            # Validar solo scripts JS (ignorar JSON-LD u otros tipos)
            script_tag = html[max(0, start - 40) : start + 8]
            if "application/ld+json" not in script_tag:
                with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
                    f.write(js_code)
                    f_name = f.name
                try:
                    res = subprocess.run(["node", "--check", f_name], capture_output=True, text=True)
                    assert res.returncode == 0, f"Error de sintaxis JS en {name}:\n{res.stderr}"
                finally:
                    if os.path.exists(f_name):
                        os.remove(f_name)
            start = html.find("<script>", end)


def test_a2a_agent_card_endpoints():
    """Valida los endpoints oficiales Google/IBM A2A /.well-known/agent-card.json y /.well-known/agent.json."""
    for path in ["/.well-known/agent-card.json", "/.well-known/agent.json"]:
        resp = client.get(path)
        assert resp.status_code == 200, f"Error en endpoint {path}"
        data = resp.json()
        assert data["protocolVersion"] == "0.2.0"
        assert data["name"] == "A2A Defense Gateway"
        assert len(data["skills"]) == len(server.list_tools()), f"Esperadas {len(server.list_tools())} skills en Agent Card, obtenidas {len(data['skills'])}"
        assert "A2A-0.2" in data["capabilities"]["protocols_supported"]
        assert "l402" in data["securitySchemes"]


def test_llms_txt_and_smithery_endpoints():
    """Valida que /llms.txt y /smithery.yaml expongan las herramientas activas."""
    resp_llms = client.get("/llms.txt")
    assert resp_llms.status_code == 200
    text_llms = resp_llms.text
    assert f"{len(server.list_tools())} Production Tools" in text_llms
    assert "verify_meatspace_attestation" in text_llms
    assert "verify_kya_attestation" in text_llms
    assert "translate_x402_to_l402_settlement" in text_llms
    assert "audit_eip7702_delegation" in text_llms
    assert "detect_malicious_llm_router" in text_llms
    assert "audit_echoleak_markdown_exfiltration" in text_llms
    assert "simulate_dex_sandwich_risk" in text_llms

    resp_full = client.get("/llms-full.txt")
    assert resp_full.status_code == 200
    assert f"{len(server.list_tools())} Production Tools" in resp_full.text

    resp_smith = client.get("/smithery.yaml")
    assert resp_smith.status_code == 200
    text_smith = resp_smith.text
    assert "audit_eip7702_delegation" in text_smith
    assert "verify_kya_attestation" in text_smith
    assert "translate_x402_to_l402_settlement" in text_smith


def test_metrics_summary_endpoint():
    """Valida el endpoint de métricas en tiempo real con persistencia SQLite Why-Trail."""
    resp = client.get("/api/v1/metrics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "HEALTHY"
    assert data["active_tools"] == len(server.list_tools())
    assert "total_events" in data
    assert "total_tool_calls" in data
    assert "threat_distribution" in data




