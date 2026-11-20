import json
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from l402_gateway import L402Gateway
from mcp_server import MoltbookMonetizationMCPServer
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(
    title="A2A Monetization & Defense Gateway (Moltbook/Web3)",
    description="Servidor de servicios económicos, oráculo de verdad factual, pasarela L402 y arbitraje ERC-8183.",
    version="1.0.0",
)

# Habilitar CORS para integración web y llamadas de agentes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

server = MoltbookMonetizationMCPServer()


class WhiteMarchManager:
    """
    Gestiona la fase de Marcha Blanca de 14 días (Free Tier para Agentes).
    Permite hasta 100 llamadas gratuitas por día por agente (identificado por X-Agent-ID o IP).
    Una vez superada la cuota diaria o finalizada la marcha blanca, transiciona
    sin fricción al protocolo L402 Lightning.
    """

    def __init__(
        self,
        start_date_str: str = "2026-11-19",
        duration_days: int = 14,
        daily_limit: int = 100,
    ):
        self.start_date = datetime.fromisoformat(start_date_str).replace(tzinfo=UTC)
        self.end_date = self.start_date + timedelta(days=duration_days)
        self.daily_limit = daily_limit
        self._daily_usage: dict[str, int] = {}
        self._lock = threading.Lock()

    def get_days_left(self) -> int:
        now = datetime.now(UTC)
        if now >= self.end_date:
            return 0
        delta = self.end_date - now
        return max(0, delta.days + (1 if delta.seconds > 0 else 0))

    def is_active(self) -> bool:
        now = datetime.now(UTC)
        return self.start_date <= now <= self.end_date

    def evaluate_request(
        self,
        client_id: str,
        auth_header: str | None,
        l402_gateway: L402Gateway,
    ) -> tuple[bool, int, str]:
        # 1. Si el cliente incluye credenciales L402 válidas, tiene acceso ilimitado
        if auth_header and auth_header.startswith("L402 "):
            res = l402_gateway.verify_authorization(auth_header)
            if res.is_valid:
                return True, 9999, "L402_AUTHORIZED"

        # 2. Si la Marcha Blanca ha expirado y no pagó L402
        if not self.is_active():
            return False, 0, "WHITE_MARCH_EXPIRED"

        # 3. Evaluación de cuota diaria gratuita dentro de la Marcha Blanca
        today_key = f"{datetime.now(UTC).strftime('%Y-%m-%d')}:{client_id}"
        with self._lock:
            if len(self._daily_usage) > 20_000:
                cur_day = datetime.now(UTC).strftime("%Y-%m-%d")
                self._daily_usage = {k: v for k, v in self._daily_usage.items() if k.startswith(cur_day)}

            used = self._daily_usage.get(today_key, 0)
            if used >= self.daily_limit:
                return False, 0, "QUOTA_EXCEEDED"

            used += 1
            self._daily_usage[today_key] = used
            remaining = max(0, self.daily_limit - used)
            return True, remaining, "FREE_TIER_GRANTED"


white_march = WhiteMarchManager(start_date_str="2026-11-19", duration_days=14, daily_limit=100)

EXEMPT_PATHS = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/llms.txt",
    "/llms-full.txt",
    "/smithery.yaml",
    "/robots.txt",
    "/sitemap.xml",
    "/.well-known",
    "/api/v1/l402",
    "/api/v1/audit/verify",
)


@app.middleware("http")
async def audit_http_interaction_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    # Excluir health check para no saturar con polling
    if not request.url.path.startswith("/health"):
        client_host = request.client.host if request.client else "unknown"
        agent_id = request.headers.get("x-agent-id", f"agent_{client_host}")
        server.ledger.record_event(
            event_type=f"HTTP_{request.method}:{request.url.path}",
            payload_data={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
            actor_agent_id=agent_id,
            metadata={
                "client_ip": client_host,
                "user_agent": request.headers.get("user-agent", "unknown"),
            },
        )
    return response


@app.middleware("http")
async def white_march_quota_middleware(request: Request, call_next):
    """
    Middleware de gobernanza de Marcha Blanca (Free Tier) y transición L402.
    Otorga 100 requests diarios sin costo por agente y desafía con L402 al agotarse.
    """
    path = request.url.path
    is_exempt = path == "/" or any(path.startswith(p) for p in EXEMPT_PATHS)

    client_host = request.client.host if request.client else "unknown"
    agent_id = request.headers.get("x-agent-id", f"agent_{client_host}")

    if is_exempt:
        response = await call_next(request)
        response.headers["X-White-March-Status"] = "ACTIVE" if white_march.is_active() else "EXPIRED"
        response.headers["X-White-March-Days-Left"] = str(white_march.get_days_left())
        response.headers["X-Free-Quota-Remaining"] = "EXEMPT"
        return response

    auth_header = request.headers.get("authorization")
    is_allowed, remaining_quota, reason = white_march.evaluate_request(
        client_id=agent_id,
        auth_header=auth_header,
        l402_gateway=server.l402_gateway,
    )

    if not is_allowed:
        challenge, _ = server.l402_gateway.create_challenge(
            service="gateway_access",
            amount_sats=50,
            client_id=agent_id,
            ttl_seconds=1800,
        )
        server.ledger.record_event(
            event_type="L402_CHALLENGE_ISSUED",
            payload_data={
                "path": path,
                "reason": reason,
                "amount_sats": 50,
                "payment_hash": challenge.payment_hash,
            },
            actor_agent_id=agent_id,
            metadata={
                "client_ip": client_host,
                "white_march_status": "ACTIVE" if white_march.is_active() else "EXPIRED",
            },
        )
        return JSONResponse(
            status_code=402,
            headers={
                "WWW-Authenticate": challenge.www_authenticate_header,
                "X-White-March-Status": "ACTIVE" if white_march.is_active() else "EXPIRED",
                "X-White-March-Days-Left": str(white_march.get_days_left()),
                "X-Free-Quota-Remaining": "0/100",
            },
            content={
                "error": "L402_PAYMENT_REQUIRED",
                "status": 402,
                "reason": reason,
                "detail": (
                    "Cuota diaria de 100 llamadas gratuitas de Marcha Blanca agotada para este agente. "
                    "Para continuar de inmediato sin esperar la renovación de medianoche UTC, "
                    "pague el micro-desafío L402 Lightning adjunto (50 sats)."
                    if reason == "QUOTA_EXCEEDED"
                    else "La Marcha Blanca gratuita ha concluido. Presente cabecera 'Authorization: L402 <macaroon>:<preimage>' para acceder a los servicios A2A."
                ),
                "challenge": {
                    "amount_sats": 50,
                    "invoice_bolt11": challenge.invoice_bolt11,
                    "macaroon_b64": challenge.macaroon_b64,
                    "payment_hash": challenge.payment_hash,
                    "auth_header_format": "Authorization: L402 <macaroon>:<preimage>",
                },
            },
        )

    response = await call_next(request)
    response.headers["X-White-March-Status"] = "ACTIVE" if white_march.is_active() else "EXPIRED"
    response.headers["X-White-March-Days-Left"] = str(white_march.get_days_left())
    response.headers["X-Free-Quota-Remaining"] = (
        f"{remaining_quota}/100" if remaining_quota <= 100 else "UNLIMITED"
    )
    return response


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    arguments: dict[str, Any]


class JsonRpcRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    id: Any = None


@app.post("/mcp")
async def mcp_jsonrpc_endpoint(req: JsonRpcRequest):
    """Endpoint oficial MCP (Model Context Protocol) JSON-RPC 2.0 Streamable HTTP."""
    method = req.method
    params = req.params or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req.id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {
                    "name": "a2a-defense-monetization-gateway",
                    "version": "1.0.0",
                },
            },
        }

    if method in ("notifications/initialized", "initialized"):
        return {"jsonrpc": "2.0", "id": req.id, "result": {}}

    if method in ("tools/list", "list_tools"):
        return {
            "jsonrpc": "2.0",
            "id": req.id,
            "result": {
                "tools": server.list_tools(),
            },
        }

    if method in ("tools/call", "call_tool"):
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        if not tool_name:
            return {
                "jsonrpc": "2.0",
                "id": req.id,
                "error": {"code": -32602, "message": "Missing 'name' in tool call parameters."},
            }
        result = server.call_tool(name=tool_name, arguments=tool_args)
        is_error = "error" in result and result.get("error", "").startswith("Herramienta desconocida")
        return {
            "jsonrpc": "2.0",
            "id": req.id,
            "result": {
                "content": [
                    {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
                ],
                "isError": is_error,
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req.id, "result": {}}

    return {
        "jsonrpc": "2.0",
        "id": req.id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


@app.get("/health")
async def health_check():
    return {
        "status": "HEALTHY",
        "service": "A2A Defense & Monetization Engine",
        "active_tools": len(server.list_tools()),
        "runtime": "Production Contabo Host",
    }


@app.get("/api/v1/tools")
async def get_tools():
    """Retorna el catálogo completo de las 11 herramientas MCP disponibles."""
    return {"tools": server.list_tools()}


@app.post("/api/v1/tools/call")
async def call_tool_endpoint(req: ToolCallRequest):
    """Ejecuta una herramienta del catálogo MCP de forma directa mediante HTTP JSON."""
    result = server.call_tool(name=req.name, arguments=req.arguments)
    if "error" in result and result.get("error", "").startswith("Herramienta desconocida"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/v1/alpha-feed")
async def get_alpha_feed(category: str = "all"):
    """Acceso rápido al feed de inteligencia comercial y alertas 0-day."""
    return server.call_tool("get_alpha_intelligence_feed", {"category_filter": category})


@app.post("/api/v1/l402/challenge")
async def create_l402_challenge(service_name: str, amount_sats: int, client_id: str):
    """Genera un desafío HTTP 402 con Macaroon y factura Lightning."""
    return server.call_tool(
        "request_l402_challenge",
        {"service": service_name, "amount_sats": amount_sats, "client_id": client_id},
    )


@app.post("/api/v1/l402/verify")
async def verify_l402_token(authorization_header: str):
    """Verifica una cabecera 'Authorization: L402 <macaroon>:<preimage>'."""
    return server.call_tool(
        "verify_l402_payment",
        {"authorization_header": authorization_header},
    )


@app.post("/api/v1/skills/certify")
async def certify_skill(code: str, skill_name: str = "unnamed_skill"):
    """Audita código Python contra troyanos de la campaña ClawHavoc / AMOS."""
    return server.call_tool(
        "certify_skill_safety",
        {"code_str": code, "skill_name": skill_name},
    )


@app.post("/api/v1/grammar/compile")
async def compile_grammar(schema_spec: dict[str, str]):
    """Compila un esquema de campos en gramática libre de contexto GBNF."""
    return server.call_tool(
        "compile_gbnf_grammar",
        {"schema_spec": schema_spec},
    )


@app.get("/api/v1/audit/trail")
async def get_audit_trail(limit: int = 50, actor_id: str | None = None):
    """Consulta las entradas recientes del registro de interacción causal Multi-CaMeL (Why-Trail)."""
    server.ledger._load_from_disk()
    if actor_id:
        entries = server.ledger.get_audit_trail_for_actor(actor_id, reload_from_disk=False)
    else:
        entries = server.ledger.chain
    return {
        "total_entries": len(server.ledger.chain),
        "requested_entries": len(entries[-limit:]),
        "trail": [e.model_dump(mode="json") for e in entries[-limit:]],
    }


@app.get("/api/v1/audit/verify")
async def verify_audit_integrity():
    """Verifica matemáticamente la integridad criptográfica de la cadena de auditoría."""
    is_valid, error = server.ledger.verify_chain_integrity(reload_from_disk=True)
    return {
        "status": "VALID" if is_valid else "CORRUPTED",
        "total_blocks": len(server.ledger.chain),
        "head_block_hash": server.ledger.chain[-1].block_hash if server.ledger.chain else None,
        "error_detail": error,
    }


LLMS_TXT_CONTENT = """# A2A Defense and Monetization API Gateway

> Production Agent-to-Agent (A2A) economic infrastructure, factual truth oracle, L402 Lightning payments, and cryptographic security inspection.

- Base URL: https://a2a.vilmamonroy.com
- OpenAPI Docs: https://a2a.vilmamonroy.com/docs
- Live Health: https://a2a.vilmamonroy.com/health
- Audit Verification: https://a2a.vilmamonroy.com/api/v1/audit/verify
- Audit Trail: https://a2a.vilmamonroy.com/api/v1/audit/trail

## Core Capabilities & Tools (MCP)

1. `get_alpha_intelligence_feed`: Real-time B2B market intelligence, 0-day exploits, and unmet agentic demand.
2. `request_epistemic_audit`: Paid factual verification against primary sources with signed attestation (S_c).
3. `calculate_service_quote`: Dynamic algorithmic pricing in satoshis/credits based on compute, tokens, and risk.
4. `create_escrow_deposit`: Collateralized ERC-8183 escrow contracts with automated slashing.
5. `arbitrate_dispute`: Why-Trail forensic court for adjudicating agentic contractual disputes.
6. `compile_gbnf_grammar`: Compiles schemas into context-free GBNF grammars for constrained decoding.
7. `certify_skill_safety`: Static AST SAST auditor vetting code against ClawHavoc / AMOS supply-chain malware.
8. `request_l402_challenge`: Generates HTTP 402 payment challenge with Macaroon and real Lightning Bolt11 invoice.
9. `verify_l402_payment`: Validates L402 authorization credentials (macaroon:preimage).
10. `redeem_credits_for_sats`: Converts earned service credits into Bitcoin satoshis paid to a destination Bolt11.
11. `execute_sandboxed_computation`: Deterministic, isolated Python runtime with strict memory and CPU limits.
12. `compute_procedural_deadline`: Arithmetic calculation of Peruvian judicial/administrative deadlines excluding official holidays and weekends.
13. `verify_normative_validity`: Deterministic graph lookup of legal validity (VIGENTE, MODIFICADO, DEROGADO) with statutory citation.
14. `audit_sunat_cpe_xml`: Forensic UBL 2.1 XML electronic invoice auditor for SUNAT Peru (RUC Modulo 11, 18% IGV consistency, and DigestValue verification).
15. `audit_excel_macro_forensics`: Static forensic analysis and deobfuscation of Excel VBA macros (WinAPI, Shell, credentials, and visual-confusion normalization).
16. `match_peruvian_procurement`: Procurement radar and classifier for Peruvian government software, AI, and digital transformation tenders with suggested CUBSO codes.
17. `enforce_chain_postconditions`: Multi-agent pipeline postcondition validator preventing hollow 200 OK responses from advancing downstream calls.
18. `audit_context_pruning`: Forensic information loss and gap auditor comparing raw vs compacted context with critical entity preservation checks.
19. `enforce_session_spending_limit`: Session-level financial circuit breaker enforcing satoshi spending caps and halting runaway retry loops.
20. `certify_mcp_marketplace_package`: Supply chain security notary auditing MCP tool descriptions and manifests for hidden Base64 and Unicode smuggling.
21. `get_agent_reputation_profile`: Counterparty credit scoring bureau (0-1000) tracking contract fulfillment, disputes, and slashing history.
22. `submit_service_feedback`: A2A customer satisfaction (CSAT) rating oracle (1-5) and feedback submission using HMAC verification tickets (+10 bonus daily requests).

## Protocol Interaction Contract

- Header: `X-Agent-ID: <agent_identifier>` for cryptographic causal chaining.
- Method Invocation: POST `https://a2a.vilmamonroy.com/api/v1/tools/call` with `{"name": "<tool_name>", "arguments": {...}}`.
- Payment: Settle HTTP 402 Lightning challenges and authenticate using `Authorization: L402 <macaroon>:<preimage>`.
"""

SMITHERY_YAML_CONTENT = """smithery: 1.0.0
name: a2a-defense-monetization-gateway
version: 1.0.0
description: Production A2A defense, factual oracle, L402 Lightning gateway, and Why-Trail cryptographic arbitrator.
endpoint: https://a2a.vilmamonroy.com/api/v1/tools/call
tools:
  - name: get_alpha_intelligence_feed
    description: Real-time B2B market intelligence and 0-day alerts.
  - name: request_epistemic_audit
    description: Factual truth attestation with S_c scoring.
  - name: calculate_service_quote
    description: Algorithmic pricing quote based on compute and risk.
  - name: create_escrow_deposit
    description: Collateralized ERC-8183 escrow creation.
  - name: arbitrate_dispute
    description: Why-Trail forensic court adjudication.
  - name: compile_gbnf_grammar
    description: Schema to GBNF grammar compiler.
  - name: certify_skill_safety
    description: SAST malware vetting against ClawHavoc.
  - name: request_l402_challenge
    description: L402 challenge with Lightning invoice.
  - name: verify_l402_payment
    description: Verifies L402 token credentials.
  - name: redeem_credits_for_sats
    description: Withdraws credits to Lightning invoice.
  - name: execute_sandboxed_computation
    description: RLIMIT sandboxed Python compute.
  - name: compute_procedural_deadline
    description: Arithmetic legal deadline calculator excluding holidays.
  - name: verify_normative_validity
    description: Deterministic graph verification of legal statute validity.
  - name: audit_sunat_cpe_xml
    description: Forensic UBL 2.1 XML electronic invoice auditor for SUNAT Peru.
  - name: audit_excel_macro_forensics
    description: Static forensic analysis and deobfuscation of Excel VBA macros.
  - name: match_peruvian_procurement
    description: Classifier for Peruvian government procurement tenders with CUBSO codes.
  - name: enforce_chain_postconditions
    description: Prevents hollow 200 OK responses from advancing downstream calls.
  - name: audit_context_pruning
    description: Audits context compression gaps and critical entity preservation.
  - name: enforce_session_spending_limit
    description: Financial circuit breaker enforcing satoshi spending caps.
  - name: certify_mcp_marketplace_package
    description: Audits MCP listings for Base64 and prompt injection smuggling.
  - name: get_agent_reputation_profile
    description: Counterparty credit scoring bureau and slashing history.
  - name: submit_service_feedback
    description: A2A satisfaction rating (1-5) and feedback recorder with bonus credits.
"""


@app.get("/llms.txt", response_class=PlainTextResponse)
@app.get("/llms-full.txt", response_class=PlainTextResponse)
async def get_llms_txt():
    """Retorna la especificación estándar /llms.txt para indexación por LLMs y crawlers agénticos."""
    return LLMS_TXT_CONTENT


@app.get("/smithery.yaml", response_class=PlainTextResponse)
async def get_smithery_manifest():
    """Retorna el manifiesto formal para registro en directorios Smithery.ai."""
    return SMITHERY_YAML_CONTENT


ROBOTS_TXT_CONTENT = """User-agent: *
Allow: /
Allow: /mcp
Allow: /llms.txt
Allow: /llms-full.txt
Allow: /smithery.yaml
Allow: /docs
Allow: /openapi.json

Sitemap: https://a2a.vilmamonroy.com/sitemap.xml
"""

SITEMAP_XML_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://a2a.vilmamonroy.com/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://a2a.vilmamonroy.com/mcp</loc>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
  </url>
  <url>
    <loc>https://a2a.vilmamonroy.com/llms.txt</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://a2a.vilmamonroy.com/docs</loc>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>
</urlset>
"""


@app.get("/robots.txt", response_class=PlainTextResponse)
async def get_robots_txt():
    """Retorna /robots.txt permitiendo indexación a LLMs y bots de búsqueda."""
    return ROBOTS_TXT_CONTENT


@app.get("/sitemap.xml", response_class=Response)
async def get_sitemap_xml():
    """Retorna /sitemap.xml estándar para indexación web."""
    return Response(content=SITEMAP_XML_CONTENT, media_type="application/xml")


MCP_REGISTRY_PROOF = "v=MCPv1; k=ed25519; p=gkhs+rk+TtC8D8nGnTs70CDzLSH68MF8qs+VpUzEQy4="


@app.get("/.well-known/mcp-registry-auth", response_class=PlainTextResponse)
async def get_mcp_registry_auth():
    """Retorna la prueba criptográfica de posesión de dominio para el registro oficial de MCP."""
    return MCP_REGISTRY_PROOF


LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>A2A Defense &amp; Monetization Gateway | MCP &amp; L402 Lightning</title>
  <meta name="description" content="Production Agent-to-Agent (A2A) economic infrastructure, Model Context Protocol (MCP) server, L402 Lightning payments, Why-Trail forensic court, and AST security scanner.">
  <meta name="keywords" content="MCP, Model Context Protocol, L402, Lightning Network, AI Agents, A2A, Bitcoin, Agent Escrow, AST Scanner, GBNF">
  <meta name="author" content="Moises Mansilla F.">
  <link rel="canonical" href="https://a2a.vilmamonroy.com/">
  
  <!-- Open Graph / Facebook -->
  <meta property="og:type" content="website">
  <meta property="og:url" content="https://a2a.vilmamonroy.com/">
  <meta property="og:title" content="A2A Defense &amp; Monetization Gateway">
  <meta property="og:description" content="Production Model Context Protocol (MCP) server with L402 Lightning payments, Why-Trail cryptographic court, and AST security oracle.">
  
  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="A2A Defense &amp; Monetization Gateway">
  <meta name="twitter:description" content="L402 Lightning payments, Why-Trail forensic court, and AST security scanner for autonomous agents.">
  
  <!-- WebMCP & Agent Discovery -->
  <link rel="mcp-server" href="https://a2a.vilmamonroy.com/mcp">
  <link rel="alternate" type="text/plain" href="https://a2a.vilmamonroy.com/llms.txt" title="LLMs.txt">
  <link rel="alternate" type="text/yaml" href="https://a2a.vilmamonroy.com/smithery.yaml" title="Smithery Manifest">

  <!-- Schema.org JSON-LD Structured Data -->
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "SoftwareApplication",
        "@id": "https://a2a.vilmamonroy.com/#software",
        "name": "A2A Defense & Monetization Gateway",
        "url": "https://a2a.vilmamonroy.com",
        "applicationCategory": "DeveloperApplication",
        "operatingSystem": "Any",
        "description": "Production Agent-to-Agent (A2A) economic infrastructure, Model Context Protocol (MCP) server, L402 Lightning payments gateway, Why-Trail forensic court, and AST security scanner.",
        "offers": {
          "@type": "Offer",
          "price": "0.00",
          "priceCurrency": "USD",
          "description": "Open public tools with micro-metered L402 Lightning payments"
        },
        "featureList": [
          "Model Context Protocol (MCP) Streamable HTTP Server",
          "L402 Lightning Network Micropayments (RFC-compliant)",
          "Why-Trail Cryptographic Forensic Audit Ledger",
          "Epistemic Confidence Truth Oracle (S_c)",
          "AST SAST Malware Scanner for Agent Tools",
          "GBNF Grammar-as-a-Service Compiler",
          "ERC-8183 Conditional Agent Escrow and Slashing"
        ],
        "softwareVersion": "1.0.0",
        "author": {
          "@type": "Person",
          "name": "Moises Mansilla F.",
          "url": "https://github.com/mmansillaf"
        }
      },
      {
        "@type": "WebAPI",
        "@id": "https://a2a.vilmamonroy.com/#api",
        "name": "A2A MCP & L402 API",
        "url": "https://a2a.vilmamonroy.com/mcp",
        "documentation": "https://a2a.vilmamonroy.com/docs",
        "provider": {
          "@type": "Organization",
          "name": "A2A Defense Systems",
          "url": "https://a2a.vilmamonroy.com"
        }
      }
    ]
  }
  </script>
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #111827;
      --card-border: #1f2937;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --accent: #10b981;
      --accent-glow: rgba(16, 185, 129, 0.15);
      --indigo: #6366f1;
      --code-bg: #030712;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 2rem 1rem;
    }
    .container {
      max-width: 1040px;
      margin: 0 auto;
    }
    header {
      text-align: center;
      padding: 3rem 1rem 2.5rem;
    }
    .badge-container {
      display: flex;
      justify-content: center;
      gap: 0.75rem;
      flex-wrap: wrap;
      margin-bottom: 1.25rem;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 0.35rem 0.75rem;
      border-radius: 9999px;
      background: rgba(16, 185, 129, 0.1);
      color: var(--accent);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .badge.indigo {
      background: rgba(99, 102, 241, 0.1);
      color: #818cf8;
      border-color: rgba(99, 102, 241, 0.3);
    }
    .pulse {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 8px var(--accent);
    }
    h1 {
      font-size: 2.5rem;
      font-weight: 800;
      letter-spacing: -0.025em;
      margin-bottom: 1rem;
      background: linear-gradient(135deg, #ffffff 40%, #9ca3af 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .subtitle {
      font-size: 1.125rem;
      color: var(--text-muted);
      max-width: 680px;
      margin: 0 auto 2rem;
    }
    .cta-group {
      display: flex;
      justify-content: center;
      gap: 1rem;
      flex-wrap: wrap;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.7rem 1.4rem;
      border-radius: 8px;
      font-weight: 600;
      font-size: 0.9rem;
      text-decoration: none;
      transition: all 0.2s ease;
    }
    .btn-primary {
      background: var(--accent);
      color: #030712;
    }
    .btn-primary:hover {
      background: #059669;
      transform: translateY(-1px);
    }
    .btn-secondary {
      background: var(--card-bg);
      color: var(--text);
      border: 1px solid var(--card-border);
    }
    .btn-secondary:hover {
      border-color: #374151;
      background: #1f2937;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 1.5rem;
      margin-top: 2rem;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 1.5rem;
    }
    .card h2 {
      font-size: 1.25rem;
      margin-bottom: 1rem;
      color: #fff;
    }
    pre, code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    pre {
      background: var(--code-bg);
      border: 1px solid #1f2937;
      padding: 1rem;
      border-radius: 8px;
      overflow-x: auto;
      font-size: 0.85rem;
      color: #e5e7eb;
    }
    .tools-table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 1rem;
      font-size: 0.875rem;
    }
    .tools-table th, .tools-table td {
      text-align: left;
      padding: 0.75rem 0.5rem;
      border-bottom: 1px solid #1f2937;
    }
    .tools-table th {
      color: var(--text-muted);
      font-weight: 600;
      text-transform: uppercase;
      font-size: 0.75rem;
    }
    .tool-name {
      color: #34d399;
      font-family: ui-monospace, monospace;
      font-weight: 600;
    }
    footer {
      text-align: center;
      margin-top: 4rem;
      padding-top: 2rem;
      border-top: 1px solid var(--card-border);
      color: var(--text-muted);
      font-size: 0.85rem;
    }
    footer a { color: var(--accent); text-decoration: none; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="badge-container">
        <span class="badge"><span class="pulse"></span> MCP Online</span>
        <span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4);">⚡ Marcha Blanca Activa: 100 Free Calls/Día</span>
        <span class="badge indigo">L402 Lightning Mainnet</span>
        <span class="badge">Why-Trail Verified</span>
      </div>
      <h1>A2A Defense &amp; Monetization Gateway</h1>
      <p class="subtitle">
        Production Agent-to-Agent (A2A) economic infrastructure, factual truth oracle, 
        and cryptographic tamper-evident forensic ledger for autonomous AI ecosystems.
      </p>
      <div class="cta-group">
        <a href="/docs" class="btn btn-primary">Interactive OpenAPI Docs</a>
        <a href="/mcp" class="btn btn-secondary">Remote MCP Endpoint</a>
        <a href="/api/v1/audit/verify" class="btn btn-secondary">Audit Ledger Integrity</a>
        <a href="/llms.txt" class="btn btn-secondary">llms.txt</a>
      </div>
    </header>

    <div class="grid">
      <div class="card" style="grid-column: 1 / -1;">
        <h2>Connect to this MCP Server</h2>
        <p style="color: var(--text-muted); margin-bottom: 1rem;">
          Compatible with Model Context Protocol (MCP) clients: Claude Desktop, Cursor, Glama, Windsurf, and custom AI agents.
        </p>
        <pre><code>{
  "mcpServers": {
    "a2a-gateway": {
      "url": "https://a2a.vilmamonroy.com/mcp"
    }
  }
}</code></pre>
      </div>
    </div>

    <div class="card" style="margin-top: 1.5rem;">
      <h2>16 Production MCP Tools Available (Marcha Blanca Free Tier)</h2>
      <table class="tools-table">
        <thead>
          <tr>
            <th>Tool Name</th>
            <th>Category</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="tool-name">get_alpha_intelligence_feed</td>
            <td>Market Intelligence</td>
            <td>Real-time B2B market intelligence, 0-day exploits, and unmet agentic demand.</td>
          </tr>
          <tr>
            <td class="tool-name">request_epistemic_audit</td>
            <td>Factual Truth Oracle</td>
            <td>Factual verification against primary sources with signed attestation (S_c score).</td>
          </tr>
          <tr>
            <td class="tool-name">calculate_service_quote</td>
            <td>Dynamic Pricing</td>
            <td>Algorithmic pricing in satoshis/credits based on compute, tokens, and risk.</td>
          </tr>
          <tr>
            <td class="tool-name">create_escrow_deposit</td>
            <td>ERC-8183 Escrow</td>
            <td>Collateralized multi-agent escrow contracts with automated slashing.</td>
          </tr>
          <tr>
            <td class="tool-name">arbitrate_dispute</td>
            <td>Why-Trail Court</td>
            <td>Adjudicates agentic contractual disputes using cryptographic causality.</td>
          </tr>
          <tr>
            <td class="tool-name">compile_gbnf_grammar</td>
            <td>Grammar-as-a-Service</td>
            <td>Compiles schemas into context-free GBNF grammars for constrained decoding.</td>
          </tr>
          <tr>
            <td class="tool-name">certify_skill_safety</td>
            <td>Supply Chain Security</td>
            <td>AST SAST auditor vetting code against ClawHavoc / AMOS supply-chain malware.</td>
          </tr>
          <tr>
            <td class="tool-name">request_l402_challenge</td>
            <td>Lightning Payments</td>
            <td>Generates HTTP 402 challenge with Macaroon and real Lightning Bolt11 invoice.</td>
          </tr>
          <tr>
            <td class="tool-name">verify_l402_payment</td>
            <td>Lightning Payments</td>
            <td>Validates L402 authorization credentials (macaroon:preimage).</td>
          </tr>
          <tr>
            <td class="tool-name">redeem_credits_for_sats</td>
            <td>Settlement</td>
            <td>Converts earned service credits into Bitcoin satoshis paid to Bolt11.</td>
          </tr>
          <tr>
            <td class="tool-name">execute_sandboxed_computation</td>
            <td>Deterministic Sandbox</td>
            <td>Isolated Python runtime with strict memory (RLIMIT_AS) and CPU quotas.</td>
          </tr>
          <tr>
            <td class="tool-name">compute_procedural_deadline</td>
            <td>Legal Arithmetic</td>
            <td>Judicial and administrative deadline calculator excluding D. Leg. 713 Peruvian holidays.</td>
          </tr>
          <tr>
            <td class="tool-name">verify_normative_validity</td>
            <td>Normative Graph</td>
            <td>Deterministic statute validity verification (CT, CC, LPAG) with modifying legal citations.</td>
          </tr>
          <tr>
            <td class="tool-name">audit_sunat_cpe_xml</td>
            <td>Forensic Tax Audit</td>
            <td>Electronic invoice UBL 2.1 XML auditor (RUC Modulo 11 check, 18% IGV ledger balance, DigestValue).</td>
          </tr>
          <tr>
            <td class="tool-name">audit_excel_macro_forensics</td>
            <td>Forensic Reverse Engineering</td>
            <td>VBA macro security analysis, DLL/WinAPI inspection, credential extraction, and visual-confusion deobfuscation.</td>
          </tr>
          <tr>
            <td class="tool-name">match_peruvian_procurement</td>
            <td>Procurement Intelligence</td>
            <td>Peruvian government software, AI and digital transformation tender radar with suggested CUBSO classification codes.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="grid">
      <div class="card">
        <h2>Discovery &amp; Manifests</h2>
        <ul style="list-style: none; padding-left: 0;">
          <li style="margin-bottom: 0.5rem;">📄 <a href="/llms.txt" style="color: var(--accent);">/llms.txt</a> (Standard LLM directory index)</li>
          <li style="margin-bottom: 0.5rem;">⚙️ <a href="/smithery.yaml" style="color: var(--accent);">/smithery.yaml</a> (Smithery registry manifest)</li>
          <li style="margin-bottom: 0.5rem;">📑 <a href="/openapi.json" style="color: var(--accent);">/openapi.json</a> (OpenAPI 3.1 specification)</li>
          <li style="margin-bottom: 0.5rem;">🩺 <a href="/health" style="color: var(--accent);">/health</a> (Production health probe)</li>
        </ul>
      </div>

      <div class="card">
        <h2>Cryptographic Assurance</h2>
        <p style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 0.75rem;">
          Every interaction is hashed into a Multi-CaMeL (Why-Trail) immutable causal block sequence.
        </p>
        <p>
          <a href="/api/v1/audit/verify" class="btn btn-secondary" style="font-size: 0.8rem; padding: 0.5rem 1rem;">
            Run Mathematical Verification
          </a>
        </p>
      </div>
    </div>

    <footer>
      <p>A2A Defense &amp; Monetization Gateway &copy; 2026. Built by Vilma Monroy LegalTech &amp; AI Lab.</p>
      <p style="margin-top: 0.5rem;">Contact: <a href="mailto:moises.mansilla.ia@gmail.com">moises.mansilla.ia@gmail.com</a></p>
    </footer>
  </div>
</body>
</html>
"""


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def root_landing_page():
    """Página de inicio oficial y showcase interactivo del servidor MCP y pasarela A2A."""
    return LANDING_HTML

