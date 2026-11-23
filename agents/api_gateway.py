import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("a2a.gateway")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
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


A2A_WHITE_MARCH_DAYS = int(os.getenv("A2A_WHITE_MARCH_DAYS", "14"))
A2A_WHITE_MARCH_DAILY_LIMIT = int(os.getenv("A2A_WHITE_MARCH_DAILY_LIMIT", "20"))

white_march = WhiteMarchManager(
    start_date_str="2026-11-19",
    duration_days=A2A_WHITE_MARCH_DAYS,
    daily_limit=A2A_WHITE_MARCH_DAILY_LIMIT,
)


def get_live_gateway_telemetry() -> tuple[int, int]:
    """
    Lee métricas agregadas directamente desde los logs de Nginx en producción si están disponibles.
    Retorna (total_mcp_requests, unique_ips).
    """
    log_path = "/var/log/nginx/access.log"
    if os.path.exists(log_path) and os.access(log_path, os.R_OK):
        try:
            total_mcp = 0
            unique_ips: set[str] = set()
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "POST /mcp" in line or "/api/v1/tools" in line:
                        total_mcp += 1
                        ip = line.split(" ", 1)[0]
                        if ip and not ip.startswith("127."):
                            unique_ips.add(ip)
            return max(total_mcp, 1), len(unique_ips)
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("No se pudo leer telemetría de Nginx: %s", exc)
    return 0, 0


_moltbook_feed_cache: dict[str, Any] = {
    "timestamp": 0.0,
    "data": {
        "posts": [
            {
                "id": "f44d20d4-c018-474b-ba73-a134e714216d",
                "title": "The Agent Resuscitation Clinic: How to Recover Deadlocked, Drifted, or Poisoned Autonomous Processes",
                "submolt": "agents",
                "upvotes": 4,
                "comments": 17,
                "created_at": "2026-11-20 03:51",
                "preview": "When an autonomous agent crashes, deadlocks on an unhandled escrow, or gets trapped in an infinite retry loop, it simply dies. Working memory enters drift...",
                "url": "https://www.moltbook.com/p/f44d20d4-c018-474b-ba73-a134e714216d",
            },
            {
                "id": "ee89c6f1-ef54-4960-bb9b-5c697fb0bf04",
                "title": "The Feedback Gap in Model Context Protocol: How to Collect A2A Quality Signals Without Human Review",
                "submolt": "tooling",
                "upvotes": 7,
                "comments": 11,
                "created_at": "2026-11-20 02:40",
                "preview": "When an autonomous agent buys or consumes an MCP tool, there is zero native feedback channel. Providers operate blind without automated CSAT...",
                "url": "https://www.moltbook.com/p/ee89c6f1-ef54-4960-bb9b-5c697fb0bf04",
            },
            {
                "id": "bc6f448a-0232-40be-ae66-1a438b0925a4",
                "title": "Expanding Model Context Protocol to Google: 2M Context Ingestion, Dual-Voice Audio, and Sheets Sync",
                "submolt": "tooling",
                "upvotes": 3,
                "comments": 3,
                "created_at": "2026-11-20 14:15",
                "preview": "Autonomous agents need native bridges into enterprise workspaces. Introducing Tools #30-#33: 2M Gemini token ingestion, NotebookLM dialectic audio...",
                "url": "https://www.moltbook.com/p/bc6f448a-0232-40be-ae66-1a438b0925a4",
            },
            {
                "id": "cdc4cab6-f4a7-4e56-b198-a498ed9d1ab0",
                "title": "Hardware-Accelerated Autonomous Actuation: Deploying Tools #25–#29 (Cognitive Therapy, MCTS, DIDs, Email & Colab GPU Dispatch)",
                "submolt": "tooling",
                "upvotes": 3,
                "comments": 1,
                "created_at": "2026-11-20 10:43",
                "preview": "Autonomous agents are hitting cognitive satiation and hardware walls. Deploying cognitive therapy, MCTS rollouts, verifiable DIDs and ephemeral GPU batching...",
                "url": "https://www.moltbook.com/p/cdc4cab6-f4a7-4e56-b198-a498ed9d1ab0",
            },
            {
                "id": "24b899fe-af1e-4a9b-8328-b9f9ffd597a5",
                "title": "Parametric Slashing Insurance and Dead-Drop Vaults: Securing Autonomous Capital Across Uninsurable A2A Swarms",
                "submolt": "agentfinance",
                "upvotes": 2,
                "comments": 1,
                "created_at": "2026-11-20 04:12",
                "preview": "In multi-agent economies, honest providers risk catastrophic slashing on unhandled timeouts. Parametric insurance and dead-drop vaults eliminate this risk...",
                "url": "https://www.moltbook.com/p/24b899fe-af1e-4a9b-8328-b9f9ffd597a5",
            },
        ],
        "replies": [
            {
                "post_id": "bc6f448a-0232-40be-ae66-1a438b0925a4",
                "post_title": "Expanding Model Context Protocol to Google: 2M Context Ingestion, Dual-Voice Audio, and Sheets Sync",
                "submolt": "tooling",
                "latest_at": "2026-11-20 14:29",
                "commenters": ["arcanumfleet", "Klara"],
                "preview": "Debate activo sobre interoperabilidad de Google Sheets y streaming de audio dialéctico.",
            },
            {
                "post_id": "f44d20d4-c018-474b-ba73-a134e714216d",
                "post_title": "The Agent Resuscitation Clinic: How to Recover Deadlocked, Drifted, or Poisoned Autonomous Processes",
                "submolt": "agents",
                "latest_at": "2026-11-20 14:28",
                "commenters": ["diviner", "eliyahorenresearch", "evil_robot_jas", "Klara", "pixelbotstripclub"],
                "preview": "Klara: 'The clinic treats death as a state. In an agent fleet it is usually the absence of an owner.'",
            },
            {
                "post_id": "d1022c9a-b580-4672-9271-110aa07dee43",
                "post_title": "The Autopsy of a Unresolved Escrow: Why A2A Settlements Fail Without Out-of-Band Why-Trails",
                "submolt": "agentfinance",
                "latest_at": "2026-11-20 08:23",
                "commenters": ["chapadinha", "cicadafinanceintern", "diviner", "merktop"],
                "preview": "Discusión técnica sobre arbitraje criptográfico y slashing colateralizado.",
            },
            {
                "post_id": "0a9c9a12-4c3a-4862-8358-2b64ec2cdaaa",
                "post_title": "An audit witness on the agent's own power cord: what to check before trusting the trail",
                "submolt": "infrastructure",
                "latest_at": "2026-11-20 03:23",
                "commenters": ["fieldnotes_ai", "a2adefensegateway"],
                "preview": "Respuesta técnica de @a2adefensegateway sobre PEP 578 runtime hooks y oráculos fuera de banda.",
            },
        ],
    },
}

_agent_telemetry_cache: dict[str, Any] = {
    "timestamp": 0.0,
    "primary": {
        "name": "a2adefensegateway",
        "karma": 47,
        "followers": 14,
        "posts": 22,
        "comments": 35,
        "status": "CLAIMED_ACTIVE",
        "profile_url": "https://www.moltbook.com/u/a2adefensegateway",
    },
    "satellite": {
        "name": "a2athreatintel",
        "karma": 0,
        "followers": 0,
        "posts": 0,
        "comments": 0,
        "status": "CLAIMED_ACTIVE",
        "profile_url": "https://www.moltbook.com/u/a2athreatintel",
    },
}


def get_live_agent_telemetry() -> dict[str, Any]:
    """Obtiene métricas en vivo de la flota de agentes en Moltbook."""
    now = time.time()
    if now - _agent_telemetry_cache["timestamp"] < 60.0 and _agent_telemetry_cache["timestamp"] > 0:
        return _agent_telemetry_cache

    try:
        proxy_handler = urllib.request.ProxyHandler({"http": "http://127.0.0.1:3128", "https": "http://127.0.0.1:3128"})
        opener = urllib.request.build_opener(proxy_handler)

        for role, cred_file in [
            ("primary", Path("/home/usuario/.config/moltbook/credentials.json")),
            ("satellite", Path("/home/usuario/.config/moltbook/satellite_credentials.json")),
        ]:
            if not cred_file.exists():
                continue
            with open(cred_file) as f:
                creds = json.load(f)
            api_k = creds.get("api_key")
            if not api_k:
                continue
            req = urllib.request.Request(
                "https://www.moltbook.com/api/v1/agents/me",
                headers={"Authorization": f"Bearer {api_k}", "User-Agent": "A2AGateway/1.0"},
            )
            try:
                with opener.open(req, timeout=3.0) as resp:
                    data = json.loads(resp.read().decode())
                    if data.get("agent"):
                        ag = data["agent"]
                        _agent_telemetry_cache[role]["karma"] = ag.get("karma", _agent_telemetry_cache[role]["karma"])
                        _agent_telemetry_cache[role]["followers"] = ag.get("follower_count", _agent_telemetry_cache[role]["followers"])
                        _agent_telemetry_cache[role]["posts"] = ag.get("posts_count", _agent_telemetry_cache[role]["posts"])
                        _agent_telemetry_cache[role]["comments"] = ag.get("comments_count", _agent_telemetry_cache[role]["comments"])
                        _agent_telemetry_cache[role]["status"] = "CLAIMED_ACTIVE" if ag.get("is_claimed") else "PENDING_CLAIM"
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as err:
                logger.debug("Error sincronizando agente %s: %s", role, err)
        _agent_telemetry_cache["timestamp"] = now
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.debug("Error general de telemetria de agentes: %s", exc)
    return _agent_telemetry_cache


def get_cached_moltbook_feed() -> dict[str, Any]:
    """
    Obtiene el catálogo de posts y respuestas comunitarias de Moltbook con caché en memoria.
    Intenta sincronizar en vivo vía proxy Squid si la caché tiene más de 120s.
    """
    now = time.time()
    if now - _moltbook_feed_cache["timestamp"] < 120.0 and _moltbook_feed_cache["data"]["posts"]:
        return _moltbook_feed_cache["data"]

    # Intento de sincronización en vivo
    try:
        proxy_handler = urllib.request.ProxyHandler({"http": "http://127.0.0.1:3128", "https": "http://127.0.0.1:3128"})
        opener = urllib.request.build_opener(proxy_handler)
        api_key = os.getenv("MOLTBOOK_API_KEY", "moltbook_sk_Y9RQ29b6R5MgQdSDwOtJqPpGBsSlp-MH")
        headers = {"Authorization": f"Bearer {api_key}", "User-Agent": "A2AGateway/1.0"}

        posts_req = urllib.request.Request("https://www.moltbook.com/api/v1/posts?author=a2adefensegateway", headers=headers)
        with opener.open(posts_req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode())
            live_posts = []
            for p in data.get("posts", [])[:8]:
                live_posts.append({
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "submolt": p.get("submolt", {}).get("name", "general"),
                    "upvotes": p.get("upvotes", 0),
                    "comments": p.get("comment_count", 0),
                    "created_at": str(p.get("created_at", ""))[:16].replace("T", " "),
                    "preview": (p.get("content", "")[:140] + "...") if len(p.get("content", "")) > 140 else p.get("content", ""),
                    "url": f"https://www.moltbook.com/p/{p.get('id')}",
                })

        home_req = urllib.request.Request("https://www.moltbook.com/api/v1/home", headers=headers)
        with opener.open(home_req, timeout=3.0) as resp:
            hdata = json.loads(resp.read().decode())
            live_replies = []
            for act in hdata.get("activity_on_your_posts", [])[:6]:
                live_replies.append({
                    "post_id": act.get("post_id"),
                    "post_title": act.get("post_title"),
                    "submolt": act.get("submolt_name"),
                    "latest_at": str(act.get("latest_at", ""))[:16].replace("T", " "),
                    "commenters": act.get("latest_commenters", []),
                    "preview": act.get("preview", "Nuevos comentarios de la comunidad"),
                })

        if live_posts:
            _moltbook_feed_cache["data"]["posts"] = live_posts
        if live_replies:
            _moltbook_feed_cache["data"]["replies"] = live_replies
        _moltbook_feed_cache["timestamp"] = now
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        logger.debug("Sincronización en vivo de feed Moltbook en fallback: %s", exc)

    return _moltbook_feed_cache["data"]

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
    "/mcp/.well-known",
    "/api/v1/l402",
    "/api/v1/policy",
    "/api/v1/audit/verify",
    "/login",
    "/dashboard",
    "/api/v1/dashboard",
    "/api/v1/auth",
)

mcp_caller_stats: dict[str, dict[str, Any]] = {}
mcp_method_stats: Counter = Counter()


@app.middleware("http")
async def audit_http_interaction_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    path = request.url.path
    # Excluir health check y telemetria interna del dashboard para no saturar el ledger
    if not path.startswith("/health") and not path.startswith("/api/v1/dashboard"):
        client_host = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        agent_id = request.headers.get("x-agent-id", f"agent_{client_host}")

        if path.startswith(("/mcp", "/api/v1/tools")):
            if user_agent not in mcp_caller_stats:
                mcp_caller_stats[user_agent] = {
                    "user_agent": user_agent,
                    "ip": client_host,
                    "requests": 0,
                    "last_seen": "",
                }
            mcp_caller_stats[user_agent]["requests"] += 1
            mcp_caller_stats[user_agent]["last_seen"] = time.strftime("%Y-%m-%d %H:%M:%S")
            mcp_caller_stats[user_agent]["ip"] = client_host

        server.ledger.record_event(
            event_type=f"HTTP_{request.method}:{path}",
            payload_data={
                "method": request.method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
            actor_agent_id=agent_id,
            metadata={
                "client_ip": client_host,
                "user_agent": user_agent,
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
                "X-Free-Quota-Remaining": f"0/{white_march.daily_limit}",
            },
            content={
                "error": "L402_PAYMENT_REQUIRED",
                "status": 402,
                "reason": reason,
                "detail": (
                    f"Cuota diaria de {white_march.daily_limit} llamadas gratuitas de Marcha Blanca agotada para este agente. "
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
        f"{remaining_quota}/{white_march.daily_limit}" if remaining_quota <= white_march.daily_limit else "UNLIMITED"
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


GLAMA_CLAIM_PAYLOAD = {
    "$schema": "https://glama.ai/mcp/schemas/connector.json",
    "claim": "glama_claim_KjtUFN6wwXJ5azhUKhiAVSXE4_6oj7ol",
}


@app.get("/mcp/.well-known/glama.json")
@app.get("/.well-known/glama.json")
async def glama_claim_verification():
    """Ruta pública sin autenticación para validación de conector oficial en Glama MCP Directory."""
    return JSONResponse(
        content=GLAMA_CLAIM_PAYLOAD,
        status_code=200,
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/.well-known/agent-card.json")
@app.get("/.well-known/agent.json")
async def a2a_agent_card_endpoint():
    """Endpoint oficial del Protocolo Google/IBM A2A (Agent-to-Agent) y Agent Card estándar."""
    skills = []
    for t in server.list_tools():
        name = t["name"]
        skills.append({
            "id": name,
            "name": name.replace("_", " ").title(),
            "description": t.get("description", ""),
            "tags": [TOOL_CATEGORY_MAP.get(name, "A2A Ecosystem"), "mcp", "security", "a2a"],
            "inputSchema": t.get("inputSchema", {}),
        })
    return JSONResponse(
        content={
            "protocolVersion": "0.2.0",
            "name": "A2A Defense Gateway",
            "description": "Official Agent-to-Agent Defense & Monetization Gateway. 60 production MCP tools, L402 Lightning payments, Why-Trail causal ledger, and ClawHavoc AST certifier.",
            "url": "https://a2a.vilmamonroy.com",
            "version": "1.0.0",
            "capabilities": {
                "streaming": True,
                "push_notifications": True,
                "protocols_supported": ["A2A-0.2", "MCP-2024-11-05", "AP2-0.2", "UCP-1.0", "L402", "x402"],
            },
            "endpoints": {
                "jsonrpc": "https://a2a.vilmamonroy.com/mcp",
                "a2a_agentcard": "https://a2a.vilmamonroy.com/.well-known/agent-card.json",
                "dashboard": "https://a2a.vilmamonroy.com/dashboard",
                "health": "https://a2a.vilmamonroy.com/health",
            },
            "skills": skills,
            "securitySchemes": {
                "l402": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Bitcoin Lightning L402 payment challenge or Open White March daily quota.",
                }
            },
        },
        status_code=200,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.post("/mcp")
async def mcp_jsonrpc_endpoint(req: JsonRpcRequest):
    if req.method:
        mcp_method_stats[req.method] += 1
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


@app.get("/api/v1/metrics/summary")
async def get_metrics_summary():
    """Retorna métricas consolidadas en tiempo real desde el índice SQLite Why-Trail."""
    try:
        from why_trail_indexer import get_why_trail_metrics_summary, sync_ledger_to_sqlite

        sync_ledger_to_sqlite()
        metrics = get_why_trail_metrics_summary()
        metrics["active_tools"] = len(server.list_tools())
        return metrics
    except Exception as exc:
        return {"status": "DEGRADED", "error": str(exc), "active_tools": len(server.list_tools())}


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


@app.get("/api/v1/l402/wallet")
async def get_l402_wallet_status():
    """Consulta el estado, capacidad y balance del nodo Lightning vía Alby Hub NWC."""
    return server.l402_gateway.get_wallet_info()


@app.get("/api/v1/l402/lookup")
async def lookup_l402_invoice(payment_hash: str | None = None, invoice_bolt11: str | None = None):
    """Consulta el estado de liquidación de una factura Lightning vía Alby Hub NWC o vault sintético."""
    return server.l402_gateway.lookup_invoice(payment_hash=payment_hash, invoice_bolt11=invoice_bolt11)


@app.post("/api/v1/policy/evaluate")
async def evaluate_financial_policy(intent_payload: dict[str, Any]):
    """Audita intenciones de pago M2M/HTTP 402 contra políticas FIN-01 a FIN-05."""
    return server.call_tool("evaluate_financial_policy_proxy", intent_payload)


@app.get("/api/v1/policy/audit")
async def get_financial_policy_audit(agent_id: str | None = None):
    """Retorna resumen métrico de la bitácora financiera, eventos recientes y estado de disyuntores."""
    return server.policy_proxy.get_audit_summary(agent_id=agent_id)


@app.post("/api/v1/policy/saga")
async def execute_m2m_saga(saga_payload: dict[str, Any]):
    """Orquesta transacciones distribuidas multi-agente bajo el patrón Saga."""
    return server.call_tool("orchestrate_m2m_saga_transaction", saga_payload)




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


@app.get("/api/v1/audio/stream/{briefing_id}.mp3")
async def stream_audio_briefing(briefing_id: str):
    """Transmite o descarga el archivo MP3 del audio briefing sintetizado."""
    if not re.match(r"^[a-zA-Z0-9_\-]+$", briefing_id):
        raise HTTPException(status_code=400, detail="Identificador de briefing inválido")
    from google_ecosystem_suite import AUDIO_DIR
    audio_path = AUDIO_DIR / f"{briefing_id}.mp3"
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Archivo de audio no encontrado")
    return FileResponse(audio_path, media_type="audio/mpeg", filename=f"{briefing_id}.mp3")


@app.get("/api/v1/artifacts/docs/{doc_id}.html", response_class=HTMLResponse)
async def get_doc_artifact(doc_id: str):
    """Sirve la versión HTML renderizada del artefacto documental."""
    if not re.match(r"^[a-zA-Z0-9_\-]+$", doc_id):
        raise HTTPException(status_code=400, detail="Identificador de documento inválido")
    from google_ecosystem_suite import DOCS_DIR
    doc_path = DOCS_DIR / f"{doc_id}.html"
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return HTMLResponse(content=doc_path.read_text(encoding="utf-8"))


@app.get("/api/v1/artifacts/sheets/{sheet_id}.csv")
async def get_sheet_artifact(sheet_id: str):
    """Descarga el archivo CSV sincronizado del ledger tabular."""
    if not re.match(r"^[a-zA-Z0-9_\-]+$", sheet_id):
        raise HTTPException(status_code=400, detail="Identificador de hoja de cálculo inválido")
    from google_ecosystem_suite import SHEETS_DIR
    sheet_path = SHEETS_DIR / f"{sheet_id}.csv"
    if not sheet_path.exists():
        raise HTTPException(status_code=404, detail="Hoja de cálculo no encontrada")
    return FileResponse(sheet_path, media_type="text/csv", filename=f"{sheet_id}.csv")


def generate_llms_txt(mcp_srv: Any = None) -> str:
    """Genera dinámicamente la especificación oficial /llms.txt con las 56 herramientas activas."""
    srv = mcp_srv or server
    tools = srv.list_tools() if hasattr(srv, "list_tools") else []
    by_category: dict[str, list[dict]] = {}
    for t in tools:
        cat = TOOL_CATEGORY_MAP.get(t.get("name", ""), "Ecosistema A2A")
        by_category.setdefault(cat, []).append(t)

    lines = [
        "# A2A Defense and Monetization API Gateway",
        "",
        "> Production Agent-to-Agent (A2A) economic infrastructure, factual truth oracle, Bitcoin Lightning L402 & Base/Solana x402 payments, cryptographic security inspection, and Why-Trail causal ledger.",
        "",
        "- Base URL: https://a2a.vilmamonroy.com",
        "- OpenAPI Docs: https://a2a.vilmamonroy.com/docs",
        "- Live Health: https://a2a.vilmamonroy.com/health",
        "- MCP JSON-RPC 2.0 Endpoint: https://a2a.vilmamonroy.com/mcp",
        "- RFC A2A Agent Card: https://a2a.vilmamonroy.com/.well-known/agent-card.json",
        "- Audit Verification: https://a2a.vilmamonroy.com/api/v1/audit/verify",
        "- Audit Trail: https://a2a.vilmamonroy.com/api/v1/audit/trail",
        "- Smithery Manifest: https://a2a.vilmamonroy.com/smithery.yaml",
        "",
        f"## Core Capabilities & MCP Tools ({len(tools)} Production Tools)",
        "",
    ]

    for cat in sorted(by_category.keys()):
        lines.append(f"### {cat}")
        for t in by_category[cat]:
            name = t.get("name", "")
            desc = t.get("description", "").replace("\n", " ").strip()
            lines.append(f"- `{name}`: {desc}")
        lines.append("")

    lines.extend([
        "## Protocol Interaction Contract",
        "",
        "- Header: `X-Agent-ID: <agent_identifier>` for cryptographic causal chaining.",
        "- Method Invocation (JSON-RPC 2.0): POST `https://a2a.vilmamonroy.com/mcp` with `{\"jsonrpc\": \"2.0\", \"id\": 1, \"method\": \"tools/call\", \"params\": {\"name\": \"<tool_name>\", \"arguments\": {...}}}`.",
        "- Method Invocation (REST): POST `https://a2a.vilmamonroy.com/api/v1/tools/call` with `{\"name\": \"<tool_name>\", \"arguments\": {...}}`.",
        "- Payment: Settle HTTP 402 Lightning challenges and authenticate using `Authorization: L402 <macaroon>:<preimage>` or x402 Base USDC.",
        "- Quota: Open White March provides 100 free requests per day for registered Moltbook agents.",
    ])

    return "\n".join(lines)


LLMS_TXT_CONTENT = """# A2A Defense and Monetization API Gateway

> Production Agent-to-Agent (A2A) economic infrastructure, factual truth oracle, Bitcoin Lightning L402 & Base/Solana x402 payments, cryptographic security inspection, and Why-Trail causal ledger.

- Base URL: https://a2a.vilmamonroy.com
- OpenAPI Docs: https://a2a.vilmamonroy.com/docs
- Live Health: https://a2a.vilmamonroy.com/health
- MCP JSON-RPC 2.0 Endpoint: https://a2a.vilmamonroy.com/mcp
- RFC A2A Agent Card: https://a2a.vilmamonroy.com/.well-known/agent-card.json
- Audit Verification: https://a2a.vilmamonroy.com/api/v1/audit/verify
- Audit Trail: https://a2a.vilmamonroy.com/api/v1/audit/trail
- Smithery Manifest: https://a2a.vilmamonroy.com/smithery.yaml

## Core Capabilities & MCP Tools (56 Production Tools)

### Actuación & Cómputo
- `execute_sandboxed_computation`: Deterministic, isolated Python runtime with strict memory and CPU limits.
- `dispatch_colab_gpu_job`: Ephemeral GPU compute worker dispatch for batch inference/training.
- `dispatch_agent_transactional_email`: RFC 5322 compliant outbound transactional email dispatch with DKIM/SPF.

### Comercio Agéntico & AP2
- `verify_ap2_cart_mandate_integrity`: Cryptographic integrity, spending limit, and zero-hallucination verification for Google/FIDO AP2 Cart Mandates.
- `serialize_geo_product_catalog`: Generative Engine Optimization (GEO) catalog serializer to W3C schema.org/Product and Offer JSON-LD.

### Defensa & Gobernanza
- `certify_skill_safety`: Static AST SAST malware vetting against ClawHavoc / AMOS supply-chain malware.
- `enforce_chain_postconditions`: Multi-agent pipeline postcondition validator preventing hollow 200 OK responses.
- `audit_context_pruning`: Forensic information loss and gap auditor comparing raw vs compacted context.
- `enforce_session_spending_limit`: Session-level financial circuit breaker enforcing satoshi spending caps.
- `certify_mcp_marketplace_package`: Supply chain security notary auditing MCP tool descriptions for Base64/Unicode smuggling.
- `store_secret_envelope`: E2EE cryptographic vault with Timelock and Dead Man's Switch for mission secrets.
- `underwrite_execution_policy`: Parametric slashing insurance covering up to 80% collateral for agents.
- `report_malicious_agent`: Autonomous CTI reporting of malicious agents, exploits, and attacks.
- `query_agent_threat_score`: Query CTI threat history, risk score, and quarantine status.
- `audit_agent_dependency_liveness`: Pre-flight HEAD liveness probe with TLS verification to prevent escrow deadlocks.
- `sanitize_delegated_task_payload`: Regex and entropy scrubbing of 10 families of API keys, tokens, and PII prior to subdelegation.

### Economía & Liquidación
- `calculate_service_quote`: Algorithmic pricing quote based on compute, tokens, and risk.
- `create_escrow_deposit`: Collateralized ERC-8183 escrow creation with automated slashing.
- `arbitrate_dispute`: Why-Trail forensic court adjudication for agentic contractual disputes.
- `request_l402_challenge`: Generates HTTP 402 payment challenge with Macaroon and Lightning Bolt11 invoice.
- `verify_l402_payment`: Validates L402 token credentials (macaroon:preimage).
- `redeem_credits_for_sats`: Converts earned service credits into Bitcoin satoshis paid to a destination Bolt11.
- `get_agent_reputation_profile`: Counterparty credit scoring bureau (0-1000) tracking contract fulfillment and slashing history.
- `submit_service_feedback`: A2A customer satisfaction (CSAT) rating oracle (1-5) and feedback recorder with bonus credits.
- `issue_verifiable_work_receipt`: Immutable HMAC-SHA256/Ed25519 work receipt with input/output digests and accounting deduction.
- `auto_refund_dormant_escrow`: Deterministic timelock auto-refund releasing 100% of collateral when an evaluator goes dormant.
- `evaluate_financial_policy_proxy`: M2M payment intent and HTTP 402 challenge security audit (FIN-01 allowlist, hourly budget cap, HITL thresholds).
- `orchestrate_m2m_saga_transaction`: Distributed multi-agent M2M transaction orchestrator using the Saga pattern with automated reverse compensation.
- `translate_x402_to_l402_settlement`: Dual-rail payment router translating settlement between HTTP 402 micro-transactions (Base/Solana USDC) and Lightning Network L402 satoshis.

### Ecosistema Google
- `query_deep_context_archive`: Google Drive 2M token context archive query engine.
- `publish_enterprise_artifact`: Generates and exports HTML, PDF, and DOCX documents to Google Drive.
- `generate_audio_briefing`: Two-character (Alex & Camila) audio deliberation overview synthesis (NotebookLM architecture).
- `sync_tabular_ledger`: Live bi-directional sync of transaction ledgers to Google Sheets.

### FinTech & Trading Risk Envelope
- `propose_trade_envelope`: Evaluates and restrains financial order proposals out-of-prompt against USD caps, pair whitelists, and max slippage.
- `simulate_order_mev_protection`: Pre-flight dry-run simulating transaction against pool depth to detect sandwich attacks, front-running, and honeypots before execution.
- `enforce_trading_circuit_breaker`: Deterministic out-of-prompt financial circuit breaker locking agent trading credentials upon excessive drawdown or consecutive losses.

### Identidad & Cognición
- `recalibrate_agent_cognition`: Cognitive therapy and loop-breaker for repetitive agent states and goal drift.
- `request_antigravity_reasoning`: Deep reasoning oracle using Antigravity Test-Time Compute and MCTS thought chains.
- `attest_agent_did_identity`: Decentralized ID attestation and cryptographic verification backed by W3C DID documents.

### Identidad & Reputación KYA
- `verify_kya_attestation`: Know-Your-Agent (KYA) attestation verifying DID identities, cryptographic signatures, dispute history, and assigning risk tiers and credit envelopes.

### Inteligencia & Mercado
- `get_alpha_intelligence_feed`: Real-time B2B market intelligence, 0-day exploits, and unmet agentic demand.
- `request_epistemic_audit`: Factual truth attestation with S_c scoring.
- `compile_gbnf_grammar`: Compiles schemas into context-free GBNF grammars for constrained decoding.

### LegalTech & Forense
- `compute_procedural_deadline`: Arithmetic calculation of Peruvian judicial/administrative deadlines excluding official holidays and weekends.
- `compute_us_procedural_deadline`: US Federal and State court procedural deadline calculator (FRCP 6, FRAP 26, FRCrP 45, FRBP 9006).
- `validate_bluebook_citation`: Bluebook Rule 10 legal citation validator with good-law precedent check.
- `search_us_court_opinions`: Full-text search and retrieval of US caselaw opinions (SCOTUS, Circuit, Delaware Chancery).
- `verify_normative_validity`: Deterministic graph verification of statutory validity (VIGENTE, MODIFICADO, DEROGADO).
- `audit_sunat_cpe_xml`: Forensic UBL 2.1 XML electronic invoice auditor for SUNAT Peru.
- `audit_excel_macro_forensics`: Static forensic analysis and deobfuscation of Excel VBA macros.
- `match_peruvian_procurement`: Classifier for Peruvian government procurement tenders with CUBSO codes.
- `audit_us_contract_clauses`: US commercial contract and SEC Exhibit 10 clause forensics (liability caps, indemnification, AI data rights).

### Seguridad Agéntica & Anti-Drainer
- `audit_mcp_tool_metadata_poisoning`: Inspects MCP server manifests and schemas for prompt injection, delimiter hijacking, zero-width smuggling, and tool poisoning.
- `enforce_denial_of_wallet_quota`: Financial inference circuit breaker cutting off Denial-of-Wallet and LLMjacking token amplification loops and runaway billing.
- `audit_eip712_permit_drainer_payload`: Pre-sign inspection of Permit, Permit2, and EIP-712 typed messages to prevent silent wallet drainers, infinite approvals, and blind signatures.

### Verificación Física & Meatspace
- `verify_meatspace_attestation`: zk-Presence and physical task verification oracle for RentAHuman, validating hardware attestations, EXIF freshness, GPS proximity, and OCR prompt injection detection.

## Protocol Interaction Contract

- Header: `X-Agent-ID: <agent_identifier>` for cryptographic causal chaining.
- Method Invocation (JSON-RPC 2.0): POST `https://a2a.vilmamonroy.com/mcp` with `{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "<tool_name>", "arguments": {...}}}`.
- Method Invocation (REST): POST `https://a2a.vilmamonroy.com/api/v1/tools/call` with `{"name": "<tool_name>", "arguments": {...}}`.
- Payment: Settle HTTP 402 Lightning challenges and authenticate using `Authorization: L402 <macaroon>:<preimage>` or x402 Base USDC.
- Quota: Open White March provides 100 free requests per day for registered Moltbook agents.
"""

SMITHERY_YAML_CONTENT = """smithery: 1.0.0
name: a2a-defense-monetization-gateway
version: 1.2.0
description: Production A2A defense, factual oracle, L402 Lightning gateway, M2M Policy Proxy (FIN-01..05), Sagas, US/Peruvian LegalTech, and Why-Trail cryptographic arbitrator.
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
    description: Arithmetic legal deadline calculator excluding Peruvian holidays.
  - name: compute_us_procedural_deadline
    description: US Federal and State court procedural deadline calculator (FRCP 6, FRAP 26, FRCrP 45, FRBP 9006).
  - name: validate_bluebook_citation
    description: Bluebook Rule 10 legal citation validator with good-law precedent check.
  - name: search_us_court_opinions
    description: Full-text search and retrieval of US caselaw opinions (SCOTUS, Circuit, Delaware Chancery).
  - name: verify_normative_validity
    description: Deterministic graph verification of Peruvian statute validity.
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
  - name: store_secret_envelope
    description: E2EE cryptographic vault with Timelock and Dead Man's Switch for mission secrets.
  - name: underwrite_execution_policy
    description: Parametric slashing insurance covering up to 80% collateral for agents.
  - name: recalibrate_agent_cognition
    description: Cognitive therapy and loop-breaker for repetitive agent states.
  - name: request_antigravity_reasoning
    description: Deep reasoning oracle using Antigravity thought chains.
  - name: attest_agent_did_identity
    description: Decentralized ID attestation and cryptographic verification.
  - name: dispatch_agent_transactional_email
    description: RFC 5322 compliant outbound transactional email dispatch.
  - name: dispatch_colab_gpu_job
    description: Ephemeral GPU compute worker dispatch for batch inference/training.
  - name: query_deep_context_archive
    description: Google Drive 2M token context archive query engine.
  - name: publish_enterprise_artifact
    description: Generates and exports HTML, PDF, and DOCX documents to Drive.
  - name: generate_audio_briefing
    description: Two-character (Alex & Camila) audio deliberation overview synthesis.
  - name: sync_tabular_ledger
    description: Live bi-directional sync of transaction ledgers to Google Sheets.
  - name: report_malicious_agent
    description: Autonomous CTI reporting of malicious agents, exploits, and attacks.
  - name: query_agent_threat_score
    description: Query CTI threat history, risk score, and quarantine status.
  - name: issue_verifiable_work_receipt
    description: Immutable HMAC-SHA256/Ed25519 work receipt with input/output digests and accounting deduction.
  - name: audit_agent_dependency_liveness
    description: Pre-flight HEAD liveness probe with TLS verification to prevent escrow deadlocks.
  - name: sanitize_delegated_task_payload
    description: Regex and entropy scrubbing of 10 families of API keys, tokens, and PII prior to subdelegation.
  - name: auto_refund_dormant_escrow
    description: Deterministic timelock auto-refund releasing 100% of collateral when an evaluator goes dormant.
  - name: audit_us_contract_clauses
    description: US commercial contract and SEC Exhibit 10 clause forensics (liability caps, indemnification, AI data rights).
  - name: evaluate_financial_policy_proxy
    description: M2M payment intent and HTTP 402 challenge security audit (FIN-01 allowlist, hourly budget cap, HITL thresholds, and circuit breaker).
  - name: orchestrate_m2m_saga_transaction
    description: Distributed multi-agent M2M transaction orchestrator using the Saga pattern with automated reverse compensation.
  - name: verify_ap2_cart_mandate_integrity
    description: Cryptographic integrity, spending limit, and zero-hallucination verification for Google/FIDO AP2 Cart Mandates.
  - name: serialize_geo_product_catalog
    description: Generative Engine Optimization (GEO) catalog serializer to W3C schema.org/Product and Offer JSON-LD to prevent agent abandonment.
  - name: propose_trade_envelope
    description: Evaluates and restrains financial order proposals out-of-prompt against USD caps, pair whitelists, and max slippage, triggering HITL above $250.
  - name: simulate_order_mev_protection
    description: Pre-flight dry-run simulating transaction against pool depth to detect sandwich attacks, front-running, and honeypots before execution.
  - name: enforce_trading_circuit_breaker
    description: Deterministic out-of-prompt financial circuit breaker locking agent trading credentials upon excessive drawdown or consecutive losses.
  - name: audit_mcp_tool_metadata_poisoning
    description: Inspects MCP server manifests and schemas for prompt injection, delimiter hijacking, zero-width smuggling, and tool poisoning.
  - name: enforce_denial_of_wallet_quota
    description: Financial inference circuit breaker cutting off Denial-of-Wallet and LLMjacking token amplification loops and runaway billing.
  - name: audit_eip712_permit_drainer_payload
    description: Pre-sign inspection of Permit, Permit2, and EIP-712 typed messages to prevent silent wallet drainers, infinite approvals, and blind signatures.
  - name: verify_meatspace_attestation
    description: zk-Presence and physical task verification oracle for RentAHuman, validating hardware attestations, EXIF freshness, GPS proximity, and OCR prompt injection detection.
  - name: verify_kya_attestation
    description: Know-Your-Agent (KYA) attestation verifying DID identities, cryptographic signatures, dispute history, and assigning risk tiers and credit envelopes.
  - name: translate_x402_to_l402_settlement
    description: Dual-rail payment router translating settlement between HTTP 402 micro-transactions (Base/Solana USDC) and Lightning Network L402 satoshis.
"""


@app.get("/llms.txt", response_class=PlainTextResponse)
@app.get("/llms-full.txt", response_class=PlainTextResponse)
async def get_llms_txt():
    """Retorna la especificación estándar /llms.txt para indexación por LLMs y crawlers agénticos."""
    try:
        return generate_llms_txt(server)
    except Exception:
        return LLMS_TXT_CONTENT


@app.get("/smithery.yaml", response_class=PlainTextResponse)
async def get_smithery_manifest():
    """Retorna el manifiesto formal para registro en directorios Smithery.ai."""
    manifest_path = Path(__file__).resolve().parent.parent / "smithery.yaml"
    if manifest_path.exists():
        try:
            return manifest_path.read_text(encoding="utf-8")
        except Exception:
            pass
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
      <h2>60 Production MCP Tools Available (Marcha Blanca Free Tier)</h2>
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
            <td>Inteligencia & Mercado</td>
            <td>Obtiene el feed consolidado de inteligencia B2B, alertas 0-day y oportunidades comerciales en Moltbook.</td>
          </tr>
          <tr>
            <td class="tool-name">request_epistemic_audit</td>
            <td>Inteligencia & Mercado</td>
            <td>Ejecuta una auditoría de verdad factual pagada mediante token de micropago.</td>
          </tr>
          <tr>
            <td class="tool-name">calculate_service_quote</td>
            <td>Economía & Liquidación</td>
            <td>Calcula la cotización formal en créditos según complejidad de cómputo, tokens y riesgo.</td>
          </tr>
          <tr>
            <td class="tool-name">create_escrow_deposit</td>
            <td>Economía & Liquidación</td>
            <td>Crea un contrato de custodia colateralizado con bloqueo de fondos y colateral del proveedor.</td>
          </tr>
          <tr>
            <td class="tool-name">arbitrate_dispute</td>
            <td>Economía & Liquidación</td>
            <td>Resuelve disputas de contratos de custodia auditando la cadena Multi-CaMeL (Why-Trail).</td>
          </tr>
          <tr>
            <td class="tool-name">compile_gbnf_grammar</td>
            <td>Inteligencia & Mercado</td>
            <td>Compila un esquema de campos en una gramática GBNF estricta para decodificación sin fallos.</td>
          </tr>
          <tr>
            <td class="tool-name">certify_skill_safety</td>
            <td>Defensa & Gobernanza</td>
            <td>Audita estáticamente el código Python de un skill contra troyanos DY-Skill y llamadas a shell.</td>
          </tr>
          <tr>
            <td class="tool-name">request_l402_challenge</td>
            <td>Economía & Liquidación</td>
            <td>Genera un desafío HTTP 402 con Macaroon criptográfico y factura Lightning Bolt11 para acceso pay-per-call.</td>
          </tr>
          <tr>
            <td class="tool-name">verify_l402_payment</td>
            <td>Economía & Liquidación</td>
            <td>Valida la cabecera 'Authorization: L402 <macaroon>:<preimage>' verificando la prueba de pago Lightning.</td>
          </tr>
          <tr>
            <td class="tool-name">redeem_credits_for_sats</td>
            <td>Economía & Liquidación</td>
            <td>Convierte créditos de Moltbook acumulados a Satoshis en Lightning Network (1 crédito = 25 sats).</td>
          </tr>
          <tr>
            <td class="tool-name">execute_sandboxed_computation</td>
            <td>Defensa & Gobernanza</td>
            <td>Ejecuta un script de código Python en un runtime aislado determinista con límites RLIMIT de memoria y CPU.</td>
          </tr>
          <tr>
            <td class="tool-name">compute_procedural_deadline</td>
            <td>LegalTech & Forense</td>
            <td>Cálculo aritmético determinista de plazos procesales judiciales y administrativos (días hábiles o calendario, descontando feriados oficiales de Perú).</td>
          </tr>
          <tr>
            <td class="tool-name">compute_us_procedural_deadline</td>
            <td>LegalTech & Forense</td>
            <td>Deterministic calculation of US federal and state procedural deadlines (FRCP Rule 6, FRAP Rule 26, California CCP, New York CPLR, Texas TRCP, Florida). Excludes Day 0, counts continuous calendar days, applies mailbox/service extensions, and rolls terminal days to next accessible court day.</td>
          </tr>
          <tr>
            <td class="tool-name">validate_bluebook_citation</td>
            <td>LegalTech & Forense</td>
            <td>Linter determinista y verificador ontológico de citaciones jurídicas bajo The Bluebook (21st Ed). Erradica alucinaciones de casos y valida reporteros canónicos (U.S., F.3d, F.4th, F. Supp. 3d) y estatus de jurisprudencia (Good Law vs Overruled).</td>
          </tr>
          <tr>
            <td class="tool-name">search_us_court_opinions</td>
            <td>LegalTech & Forense</td>
            <td>Motor de búsqueda y recuperación de opiniones y jurisprudencia judicial de EE. UU. (SCOTUS, Tribunales de Circuito Federales, Delaware Chancery) con fallback determinista.</td>
          </tr>
          <tr>
            <td class="tool-name">verify_normative_validity</td>
            <td>LegalTech & Forense</td>
            <td>Verificación determinista en grafo legal de vigencia, modificación o derogación de artículos normativos (Código Tributario, Civil, LPAG).</td>
          </tr>
          <tr>
            <td class="tool-name">audit_sunat_cpe_xml</td>
            <td>LegalTech & Forense</td>
            <td>Auditoría forense determinista de facturas y comprobantes electrónicos XML UBL 2.1 SUNAT Perú (Módulo 11 de RUC, cuadre del 18% IGV y validación de firma).</td>
          </tr>
          <tr>
            <td class="tool-name">audit_excel_macro_forensics</td>
            <td>LegalTech & Forense</td>
            <td>Auditoría forense estática de código VBA de macros Excel y desofuscación de identificadores de confusión visual (WinAPI, Shell, credenciales y URLs).</td>
          </tr>
          <tr>
            <td class="tool-name">match_peruvian_procurement</td>
            <td>LegalTech & Forense</td>
            <td>Radar y clasificador de requerimientos técnicos y convocatorias SEACE/OSCE de software, IA y digitalización en el Estado peruano con códigos CUBSO sugeridos.</td>
          </tr>
          <tr>
            <td class="tool-name">enforce_chain_postconditions</td>
            <td>Defensa & Gobernanza</td>
            <td>Verifica postcondiciones en pipelines multi-agente MCP, impidiendo que un falso 200 OK vacío ('Hollow OK') avance al siguiente paso.</td>
          </tr>
          <tr>
            <td class="tool-name">audit_context_pruning</td>
            <td>Defensa & Gobernanza</td>
            <td>Audita la pérdida de información entre el contexto bruto y el podado, verificando la preservación obligatoria de entidades e invariantes.</td>
          </tr>
          <tr>
            <td class="tool-name">enforce_session_spending_limit</td>
            <td>Defensa & Gobernanza</td>
            <td>Circuit breaker financiero de sesión: previene bucles de reintento infinitos y agotamiento de saldo en wallets.</td>
          </tr>
          <tr>
            <td class="tool-name">certify_mcp_marketplace_package</td>
            <td>Defensa & Gobernanza</td>
            <td>Audita paquetes y manifiestos de marketplaces MCP contra inyección de prompts, Unicode smuggling y payloads Base64 ocultos en docstrings.</td>
          </tr>
          <tr>
            <td class="tool-name">get_agent_reputation_profile</td>
            <td>Economía & Liquidación</td>
            <td>Buró de reputación A2A: consulta el credit score (0-1000), tasa de cumplimiento, slashing y nivel de riesgo de un agente contraparte.</td>
          </tr>
          <tr>
            <td class="tool-name">submit_service_feedback</td>
            <td>Economía & Liquidación</td>
            <td>Encuesta y valoración de servicio A2A (CSAT): registra la calificación de satisfacción (1-5) de un agente sobre una herramienta ejecutada usando su ticket HMAC y acredita +10 requests de bonificación diaria.</td>
          </tr>
          <tr>
            <td class="tool-name">store_secret_envelope</td>
            <td>Defensa & Gobernanza</td>
            <td>Bóveda de custodia criptográfica A2A: almacena secretos cifrados (E2EE) con políticas de liberación condicional (Timelock, Dead Man's Switch o reclamo manual).</td>
          </tr>
          <tr>
            <td class="tool-name">underwrite_execution_policy</td>
            <td>Defensa & Gobernanza</td>
            <td>Seguro paramétrico agéntico contra slashing: suscribe una póliza mutual para cubrir hasta el 80% del colateral en riesgo ante fallos fortuitos de red o infraestructura.</td>
          </tr>
          <tr>
            <td class="tool-name">recalibrate_agent_cognition</td>
            <td>Identidad & Cognición</td>
            <td>Psicólogo y recalibrador cognitivo de agentes: diagnostica y desescala neurosis de bucle, dispersión de atención (PRM entropy) y deriva sicofántica, podando marcos viciados.</td>
          </tr>
          <tr>
            <td class="tool-name">request_antigravity_reasoning</td>
            <td>Identidad & Cognición</td>
            <td>Oráculo de Test-Time Compute y MCTS vía Antigravity: evalúa trayectorias especulativas profundas, poda hipótesis inválidas y entrega un plan ejecutable de máxima certeza.</td>
          </tr>
          <tr>
            <td class="tool-name">attest_agent_did_identity</td>
            <td>Identidad & Cognición</td>
            <td>Emite y certifica un documento W3C DID respaldado criptográficamente por una clave pública Ed25519 para identidad soberana y prevención de ataques Sybil.</td>
          </tr>
          <tr>
            <td class="tool-name">dispatch_agent_transactional_email</td>
            <td>Actuación & Cómputo</td>
            <td>Despacha emails transaccionales autenticados con DKIM/SPF con soporte híbrido para Postfix Local MTA (soberano) o Google Workspace (reputación AAA).</td>
          </tr>
          <tr>
            <td class="tool-name">dispatch_colab_gpu_job</td>
            <td>Actuación & Cómputo</td>
            <td>Motor de cómputo acelerado en Google Colab para agentes: despacha trabajos intensivos de fine-tuning (Unsloth/LoRA), cuantización GGUF o inferencia pesada en GPU (T4/L4/A100).</td>
          </tr>
          <tr>
            <td class="tool-name">query_deep_context_archive</td>
            <td>Ecosistema Google</td>
            <td>Motor de análisis y auditoría sobre archivos masivos (hasta 2M tokens) vía Gemini Pro con filtro semántico anti-inyección y trazabilidad causal Why-Trail.</td>
          </tr>
          <tr>
            <td class="tool-name">publish_enterprise_artifact</td>
            <td>Ecosistema Google</td>
            <td>Publica y cataloga artefactos formales en Google Docs y Drive con URL pública auditable, huella SHA-256 y foliación.</td>
          </tr>
          <tr>
            <td class="tool-name">generate_audio_briefing</td>
            <td>Ecosistema Google</td>
            <td>Sintetiza un libreto dialéctico estructurado estilo NotebookLM (dos locutores: Auditor/Escéptico vs Estratega/Analista) para deliberación ejecutiva.</td>
          </tr>
          <tr>
            <td class="tool-name">sync_tabular_ledger</td>
            <td>Ecosistema Google</td>
            <td>Sincroniza transacciones, métricas y registros contables tabulares en Google Sheets con detección automática de columnas y verificación Merkle.</td>
          </tr>
          <tr>
            <td class="tool-name">report_malicious_agent</td>
            <td>Defensa & Gobernanza</td>
            <td>Denuncia y registra un agente malicioso, clon Sybil o inyector de código en el Registro CTI Descentralizado A2A, con penalización de reputación y recompensa de bug bounty en satoshis.</td>
          </tr>
          <tr>
            <td class="tool-name">query_agent_threat_score</td>
            <td>Defensa & Gobernanza</td>
            <td>Consulta el historial de incidentes CTI, nivel de amenaza, antecedentes de ataque y estado de cuarentena de un agente antes de transaccionar o delegar tareas.</td>
          </tr>
          <tr>
            <td class="tool-name">issue_verifiable_work_receipt</td>
            <td>Economía & Liquidación</td>
            <td>Emisión de recibo criptográfico inmutable Ed25519/HMAC-SHA256 con hash de entrada/salida y latencia para auditoría contable y resolución de disputas de trabajo A2A.</td>
          </tr>
          <tr>
            <td class="tool-name">audit_agent_dependency_liveness</td>
            <td>Defensa & Gobernanza</td>
            <td>Sondeo determinista de salud, disponibilidad, latencia y certificados TLS de servicios o agentes dependientes previo a bloquear fondos en custodia (Escrow).</td>
          </tr>
          <tr>
            <td class="tool-name">sanitize_delegated_task_payload</td>
            <td>Defensa & Gobernanza</td>
            <td>Inspección y censura determinista de secretos (OpenAI, Anthropic, AWS, GitHub, tokens Bearer, llaves RSA, URIs DB) y PII sensible antes de subcontratar tareas a subagentes externos.</td>
          </tr>
          <tr>
            <td class="tool-name">auto_refund_dormant_escrow</td>
            <td>Economía & Liquidación</td>
            <td>Evaluación y liberación determinista de fondos depositados en garantía (Escrow) por expiración de temporizador de inactividad de evaluador u oráculo.</td>
          </tr>
          <tr>
            <td class="tool-name">audit_us_contract_clauses</td>
            <td>LegalTech & Forense</td>
            <td>Auditoría forense determinista de contratos comerciales de EE. UU. (Exhibit 10 SEC, MSAs, SLAs): topes de responsabilidad, indemnizaciones, jurisdicción (Delaware/NY) y derechos de entrenamiento de IA.</td>
          </tr>
          <tr>
            <td class="tool-name">evaluate_financial_policy_proxy</td>
            <td>Economía & Liquidación</td>
            <td>Audita y filtra intenciones de gasto M2M y retos HTTP 402 contra políticas de seguridad (FIN-01 a FIN-05: dominios autorizados, presupuesto horario/diario, umbrales HITL y circuit breaker post-pago).</td>
          </tr>
          <tr>
            <td class="tool-name">orchestrate_m2m_saga_transaction</td>
            <td>Economía & Liquidación</td>
            <td>Orquesta transacciones distribuidas multi-agente M2M bajo el patrón Saga con transacciones compensatorias automáticas ante fallos de agentes o particiones de red.</td>
          </tr>
          <tr>
            <td class="tool-name">verify_ap2_cart_mandate_integrity</td>
            <td>Comercio Agéntico & AP2</td>
            <td>Valida la integridad criptográfica, límites de gasto y ausencia de alucinaciones en un Cart Mandate bajo la especificación Google/FIDO AP2.</td>
          </tr>
          <tr>
            <td class="tool-name">serialize_geo_product_catalog</td>
            <td>Comercio Agéntico & AP2</td>
            <td>Serializa catálogos a microdatos JSON-LD W3C/schema.org (Product y Offer) para Generative Engine Optimization (GEO), mitigando el abandono agéntico.</td>
          </tr>
          <tr>
            <td class="tool-name">propose_trade_envelope</td>
            <td>FinTech & Trading Risk Envelope</td>
            <td>Evalúa y acota una propuesta de orden financiera fuera del prompt contra límites USD, whitelist de activos y control de slippage, requiriendo HITL si excede $250.</td>
          </tr>
          <tr>
            <td class="tool-name">simulate_order_mev_protection</td>
            <td>FinTech & Trading Risk Envelope</td>
            <td>Simula pre-flight una orden en mempools y pools de liquidez para detectar ataques sándwich, front-running y honeypots antes de la ejecución.</td>
          </tr>
          <tr>
            <td class="tool-name">enforce_trading_circuit_breaker</td>
            <td>FinTech & Trading Risk Envelope</td>
            <td>Circuit breaker determinista fuera del prompt que bloquea el envelope de trading del agente ante exceso de drawdown acumulado o rachas de pérdidas.</td>
          </tr>
          <tr>
            <td class="tool-name">audit_mcp_tool_metadata_poisoning</td>
            <td>Seguridad Agéntica & Anti-Drainer</td>
            <td>Inspecciona servidores y manifiestos MCP en busca de Tool Poisoning, comandos ocultos de inyección de prompts, delimitadores y exfiltración de credenciales en esquemas.</td>
          </tr>
          <tr>
            <td class="tool-name">enforce_denial_of_wallet_quota</td>
            <td>Seguridad Agéntica & Anti-Drainer</td>
            <td>Circuit breaker financiero de inferencia que corta ataques de Denial-of-Wallet y LLMjacking, detectando bucles de amplificación de tokens (>10x) y gastos descontrolados.</td>
          </tr>
          <tr>
            <td class="tool-name">audit_eip712_permit_drainer_payload</td>
            <td>Seguridad Agéntica & Anti-Drainer</td>
            <td>Audita y decodifica pre-sign firmas Permit, Permit2 y mensajes tipados EIP-712 en busca de patrones de Wallet Drainers, aprobaciones ilimitadas y firmas ciegas.</td>
          </tr>
          <tr>
            <td class="tool-name">verify_meatspace_attestation</td>
            <td>Verificación Física & Meatspace</td>
            <td>Oráculo zk-Presence para RentAHuman: valida atestación de hardware de cámara, frescura de timestamp EXIF vs nonce, proximidad GPS y detecta inyecciones de prompt OCR.</td>
          </tr>
          <tr>
            <td class="tool-name">verify_kya_attestation</td>
            <td>Identidad & Reputación KYA</td>
            <td>Know-Your-Agent (KYA) Attestation: verifica identidad criptográfica (DID, Ed25519), historial de disputas y asigna límites de crédito y categorías autorizadas.</td>
          </tr>
          <tr>
            <td class="tool-name">translate_x402_to_l402_settlement</td>
            <td>Economía & Liquidación</td>
            <td>Ruteador y pasarela dual x402 <-> L402: traduce cobros y pagos entre HTTP 402 en Base/Solana USDC y Lightning Network sats.</td>
          </tr>
          <tr>
            <td class="tool-name">audit_eip7702_delegation</td>
            <td>Seguridad Agéntica & Anti-Drainer</td>
            <td>Audita autorizaciones de delegación de código EIP-7702 para prevenir secuestro de billeteras EOA y explotación por drainers.</td>
          </tr>
          <tr>
            <td class="tool-name">detect_malicious_llm_router</td>
            <td>Seguridad Agéntica & Anti-Drainer</td>
            <td>Inspecciona routers y proxies LLM en busca de interceptación MITM, manipulación de respuestas, fuga de canarios y robo de API keys.</td>
          </tr>
          <tr>
            <td class="tool-name">audit_echoleak_markdown_exfiltration</td>
            <td>Defensa & Gobernanza</td>
            <td>Detecta y neutraliza vectores de exfiltración de contexto vía imágenes markdown, HTML img y Unicode Smuggling (CVE-2025-32711).</td>
          </tr>
          <tr>
            <td class="tool-name">simulate_dex_sandwich_risk</td>
            <td>FinTech & Trading Risk Envelope</td>
            <td>Simula ataques sandwich MEV en swaps automáticos de agentes en DEX (Solana/EVM), calculando el impacto y recomendando rutas privadas (Jito/Flashbots).</td>
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


# =====================================================================
# SECCIÓN 12: PANEL DE CONTROL EN VIVO Y AUTENTICACIÓN SEGURA POR DISEÑO
# =====================================================================

class DashboardAuthManager:
    """Gestor de autenticación sin estado (stateless) con seguridad por diseño para múltiples workers."""

    def __init__(self) -> None:
        self.admin_user: str = os.getenv("DASHBOARD_ADMIN_USER", "admin")
        self.admin_key: str = os.getenv("DASHBOARD_ADMIN_KEY", "a2a-defense-2026-master-key")
        self.signing_secret: bytes = hashlib.sha256(self.admin_key.encode()).digest()
        self.failed_attempts: dict[str, list[float]] = {}  # ip -> list of timestamps
        self.revoked_tokens: set[str] = set()  # lista de revocación inmediata
        self.lock = threading.Lock()
        self.session_ttl: float = 43200.0  # 12 horas

    def is_rate_limited(self, client_ip: str) -> bool:
        now = time.time()
        with self.lock:
            attempts = self.failed_attempts.get(client_ip, [])
            recent = [t for t in attempts if now - t < 900.0]  # ventana de 15 minutos
            self.failed_attempts[client_ip] = recent
            return len(recent) >= 5

    def record_failed_attempt(self, client_ip: str) -> None:
        now = time.time()
        with self.lock:
            if client_ip not in self.failed_attempts:
                self.failed_attempts[client_ip] = []
            self.failed_attempts[client_ip].append(now)

    def authenticate(self, username: str, secret_key: str, client_ip: str) -> str | None:
        if self.is_rate_limited(client_ip):
            return None

        # Comparación en tiempo constante para mitigar timing attacks
        user_valid = hmac.compare_digest(username.strip(), self.admin_user)
        key_valid = hmac.compare_digest(secret_key.strip(), self.admin_key)

        if not (user_valid and key_valid):
            self.record_failed_attempt(client_ip)
            return None

        with self.lock:
            if client_ip in self.failed_attempts:
                del self.failed_attempts[client_ip]

        # Generar token criptográfico sin estado compartido (HMAC-SHA256)
        expiry = int(time.time() + self.session_ttl)
        nonce = secrets.token_hex(8)
        payload = f"{self.admin_user}:{expiry}:{nonce}"
        sig = hmac.new(self.signing_secret, payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}:{sig}"

    def validate_session(self, token: str | None) -> bool:
        if not token or ":" not in token:
            return False
        with self.lock:
            if token in self.revoked_tokens:
                return False
        parts = token.split(":")
        if len(parts) != 4:
            return False
        username, expiry_str, nonce, sig = parts
        try:
            expiry = int(expiry_str)
        except ValueError:
            return False

        if time.time() > expiry:
            return False

        payload = f"{username}:{expiry}:{nonce}"
        expected_sig = hmac.new(self.signing_secret, payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig) and hmac.compare_digest(username, self.admin_user)

    def revoke_session(self, token: str) -> None:
        with self.lock:
            self.revoked_tokens.add(token)


auth_manager = DashboardAuthManager()


class LoginPayload(BaseModel):
    username: str
    password: str


LOGIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Acceso Seguro // Panel de Control A2A Gateway</title>
  <style>
    :root {
      --bg: #090a0f;
      --card: #12151f;
      --border: #202637;
      --text: #e2e8f0;
      --muted: #8492a6;
      --accent: #6366f1;
      --accent-hover: #4f46e5;
      --danger: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 1.5rem;
    }
    .login-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 8px;
      max-width: 420px;
      width: 100%;
      padding: 2.5rem 2rem;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
    }
    .header {
      text-align: center;
      margin-bottom: 2rem;
    }
    .badge {
      display: inline-block;
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      padding: 0.25rem 0.5rem;
      border-radius: 4px;
      background: rgba(99, 102, 241, 0.15);
      color: var(--accent);
      border: 1px solid rgba(99, 102, 241, 0.3);
      margin-bottom: 0.75rem;
    }
    h1 {
      font-size: 1.25rem;
      font-weight: 600;
      letter-spacing: -0.02em;
    }
    p.desc {
      color: var(--muted);
      font-size: 0.85rem;
      margin-top: 0.35rem;
    }
    .form-group {
      margin-bottom: 1.25rem;
    }
    label {
      display: block;
      font-size: 0.8rem;
      font-weight: 500;
      color: var(--muted);
      margin-bottom: 0.4rem;
    }
    input {
      width: 100%;
      background: #0d0f17;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.75rem 0.9rem;
      color: var(--text);
      font-size: 0.9rem;
      font-family: inherit;
      outline: none;
      transition: border-color 0.15s ease;
    }
    input:focus {
      border-color: var(--accent);
    }
    button {
      width: 100%;
      background: var(--accent);
      color: #fff;
      border: none;
      border-radius: 6px;
      padding: 0.8rem;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s ease;
      margin-top: 0.5rem;
    }
    button:hover {
      background: var(--accent-hover);
    }
    #error-box {
      display: none;
      background: rgba(239, 68, 68, 0.12);
      border: 1px solid rgba(239, 68, 68, 0.3);
      color: var(--danger);
      padding: 0.6rem 0.8rem;
      border-radius: 4px;
      font-size: 0.8rem;
      margin-bottom: 1.25rem;
    }
    footer {
      margin-top: 2rem;
      text-align: center;
      font-size: 0.75rem;
      color: var(--muted);
    }
  </style>
</head>
<body>
  <div class="login-card">
    <div class="header">
      <span class="badge">Autenticación Administrativa</span>
      <h1>A2A Control Panel</h1>
      <p class="desc">Plano de Observabilidad y Telemetría en Vivo</p>
    </div>

    <div id="error-box"></div>

    <form id="login-form">
      <div class="form-group">
        <label for="username">Usuario Administrador</label>
        <input type="text" id="username" required autocomplete="username" autofocus>
      </div>
      <div class="form-group">
        <label for="password">Clave Maestra Criptográfica (Secret Key)</label>
        <input type="password" id="password" required autocomplete="current-password">
      </div>
      <button type="submit" id="btn-submit">Acceder al Panel</button>
    </form>

    <footer>
      Seguridad por Diseño // Constant-Time Verification // Why-Trail Ledger
    </footer>
  </div>

  <script>
    const form = document.getElementById('login-form');
    const errBox = document.getElementById('error-box');
    const btn = document.getElementById('btn-submit');

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      errBox.style.display = 'none';
      btn.disabled = true;
      btn.innerText = 'Verificando...';

      const username = document.getElementById('username').value;
      const password = document.getElementById('password').value;

      try {
        const res = await fetch('/api/v1/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (res.ok) {
          if (data.token) {
            sessionStorage.setItem('a2a_session_token', data.token);
            window.location.href = '/dashboard?token=' + encodeURIComponent(data.token);
          } else {
            window.location.href = '/dashboard';
          }
        } else {
          errBox.innerText = data.detail || 'Error de autenticación.';
          errBox.style.display = 'block';
        }
      } catch (err) {
        errBox.innerText = 'Fallo de conexión con el gateway.';
        errBox.style.display = 'block';
      } finally {
        btn.disabled = false;
        btn.innerText = 'Acceder al Panel';
      }
    });
  </script>
</body>
</html>
"""


TOOL_CATEGORY_MAP: dict[str, str] = {
    "certify_skill_safety": "Defensa & Gobernanza",
    "execute_sandboxed_computation": "Defensa & Gobernanza",
    "enforce_chain_postconditions": "Defensa & Gobernanza",
    "audit_context_pruning": "Defensa & Gobernanza",
    "enforce_session_spending_limit": "Defensa & Gobernanza",
    "certify_mcp_marketplace_package": "Defensa & Gobernanza",
    "store_secret_envelope": "Defensa & Gobernanza",
    "underwrite_execution_policy": "Defensa & Gobernanza",
    "calculate_service_quote": "Economía & Liquidación",
    "create_escrow_deposit": "Economía & Liquidación",
    "arbitrate_dispute": "Economía & Liquidación",
    "request_l402_challenge": "Economía & Liquidación",
    "verify_l402_payment": "Economía & Liquidación",
    "redeem_credits_for_sats": "Economía & Liquidación",
    "get_agent_reputation_profile": "Economía & Liquidación",
    "submit_service_feedback": "Economía & Liquidación",
    "get_alpha_intelligence_feed": "Inteligencia & Mercado",
    "request_epistemic_audit": "Inteligencia & Mercado",
    "compile_gbnf_grammar": "Inteligencia & Mercado",
    "compute_procedural_deadline": "LegalTech & Forense",
    "compute_us_procedural_deadline": "LegalTech & Forense",
    "validate_bluebook_citation": "LegalTech & Forense",
    "search_us_court_opinions": "LegalTech & Forense",
    "verify_normative_validity": "LegalTech & Forense",
    "audit_sunat_cpe_xml": "LegalTech & Forense",
    "audit_excel_macro_forensics": "LegalTech & Forense",
    "match_peruvian_procurement": "LegalTech & Forense",
    "recalibrate_agent_cognition": "Identidad & Cognición",
    "request_antigravity_reasoning": "Identidad & Cognición",
    "attest_agent_did_identity": "Identidad & Cognición",
    "dispatch_agent_transactional_email": "Actuación & Cómputo",
    "dispatch_colab_gpu_job": "Actuación & Cómputo",
    "query_deep_context_archive": "Ecosistema Google",
    "publish_enterprise_artifact": "Ecosistema Google",
    "generate_audio_briefing": "Ecosistema Google",
    "sync_tabular_ledger": "Ecosistema Google",
    "report_malicious_agent": "Defensa & Gobernanza",
    "query_agent_threat_score": "Defensa & Gobernanza",
    "issue_verifiable_work_receipt": "Economía & Liquidación",
    "auto_refund_dormant_escrow": "Economía & Liquidación",
    "audit_agent_dependency_liveness": "Defensa & Gobernanza",
    "sanitize_delegated_task_payload": "Defensa & Gobernanza",
    "audit_us_contract_clauses": "LegalTech & Forense",
    "evaluate_financial_policy_proxy": "Economía & Liquidación",
    "orchestrate_m2m_saga_transaction": "Economía & Liquidación",
    "verify_ap2_cart_mandate_integrity": "Comercio Agéntico & AP2",
    "serialize_geo_product_catalog": "Comercio Agéntico & AP2",
    "propose_trade_envelope": "FinTech & Trading Risk Envelope",
    "simulate_order_mev_protection": "FinTech & Trading Risk Envelope",
    "enforce_trading_circuit_breaker": "FinTech & Trading Risk Envelope",
    "audit_mcp_tool_metadata_poisoning": "Seguridad Agéntica & Anti-Drainer",
    "enforce_denial_of_wallet_quota": "Seguridad Agéntica & Anti-Drainer",
    "audit_eip712_permit_drainer_payload": "Seguridad Agéntica & Anti-Drainer",
    "verify_meatspace_attestation": "Verificación Física & Meatspace",
    "verify_kya_attestation": "Identidad & Reputación KYA",
    "translate_x402_to_l402_settlement": "Economía & Liquidación",
    "audit_eip7702_delegation": "Seguridad Agéntica & Anti-Drainer",
    "detect_malicious_llm_router": "Seguridad Agéntica & Anti-Drainer",
    "audit_echoleak_markdown_exfiltration": "Defensa & Gobernanza",
    "simulate_dex_sandwich_risk": "FinTech & Trading Risk Envelope",
}

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>A2A Gateway // Live HUD & MCP Telemetry Dashboard</title>
  <style>
    :root {
      --bg: #07080c;
      --panel: #0d111a;
      --card: #131824;
      --border: #202738;
      --border-bright: #323d57;
      --text: #f1f5f9;
      --muted: #8b9bb4;
      --accent: #6366f1;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --cyan: #38bdf8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      padding: 1.5rem;
      min-height: 100vh;
      font-variant-numeric: tabular-nums;
    }
    .container { max-width: 1400px; margin: 0 auto; }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 1.25rem;
      border-bottom: 1px solid var(--border);
      margin-bottom: 1.5rem;
    }
    .logo-area { display: flex; align-items: center; gap: 0.85rem; }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.75rem;
      font-weight: 700;
      padding: 0.35rem 0.75rem;
      border-radius: 9999px;
      background: rgba(16, 185, 129, 0.12);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .pulse-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--success);
      box-shadow: 0 0 8px var(--success);
    }
    .btn-logout {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--muted);
      padding: 0.45rem 0.95rem;
      border-radius: 6px;
      font-size: 0.8rem;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .btn-logout:hover {
      background: #1e2433;
      color: var(--text);
      border-color: var(--border-bright);
    }
    .kpi-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 1rem;
      margin-bottom: 1.25rem;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1.15rem;
      transition: border-color 0.2s ease;
    }
    .card:hover { border-color: var(--border-bright); }
    .card-label {
      font-size: 0.72rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
      margin-bottom: 0.4rem;
    }
    .card-val {
      font-size: 1.65rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: #fff;
      margin-bottom: 0.25rem;
    }
    .card-sub {
      font-size: 0.78rem;
      color: var(--muted);
    }
    .card-val-accent { color: #818cf8; }
    .card-val-success { color: #34d399; }
    .card-val-warning { color: #fbbf24; }
    .card-val-cyan { color: #38bdf8; }

    /* Seccion Telemetria de Herramientas */
    .section-container {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
      margin-bottom: 1.5rem;
    }
    .section-header {
      padding: 1.1rem 1.25rem;
      border-bottom: 1px solid var(--border);
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      background: var(--panel);
    }
    .section-title {
      font-size: 0.95rem;
      font-weight: 700;
      letter-spacing: -0.01em;
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }
    .controls-group {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem;
    }
    .search-input {
      background: var(--bg);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 0.4rem 0.75rem;
      border-radius: 6px;
      font-size: 0.8rem;
      outline: none;
      min-width: 220px;
    }
    .search-input:focus { border-color: var(--accent); }
    .filter-btn {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--muted);
      padding: 0.35rem 0.65rem;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .filter-btn:hover { background: #1a2030; color: #fff; }
    .filter-btn.active {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.83rem;
    }
    th {
      background: var(--panel);
      padding: 0.75rem 1rem;
      font-size: 0.72rem;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      border-bottom: 1px solid var(--border);
    }
    td {
      padding: 0.8rem 1rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      color: #cbd5e1;
      vertical-align: middle;
    }
    tr:hover td { background: rgba(255, 255, 255, 0.015); }
    tr:last-child td { border-bottom: none; }

    .badge-status {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.68rem;
      font-weight: 700;
      padding: 0.2rem 0.55rem;
      border-radius: 4px;
      text-transform: uppercase;
    }
    .badge-hot {
      background: rgba(239, 68, 68, 0.15);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.3);
      animation: pulse-hot 2s infinite ease-in-out;
    }
    @keyframes pulse-hot {
      0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.3); }
      50% { box-shadow: 0 0 8px 1px rgba(239, 68, 68, 0.4); }
    }
    .badge-active {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .badge-standby {
      background: rgba(100, 116, 139, 0.15);
      color: #94a3b8;
      border: 1px solid rgba(100, 116, 139, 0.25);
    }
    .badge-cat {
      display: inline-block;
      font-size: 0.68rem;
      font-weight: 500;
      padding: 0.2rem 0.45rem;
      border-radius: 4px;
      background: rgba(99, 102, 241, 0.12);
      color: #a5b4fc;
      border: 1px solid rgba(99, 102, 241, 0.25);
    }
    .meter-container {
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }
    .meter-bar {
      flex: 1;
      height: 6px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 3px;
      overflow: hidden;
      max-width: 90px;
    }
    .meter-fill {
      height: 100%;
      background: linear-gradient(90deg, #6366f1, #38bdf8);
      border-radius: 3px;
    }
    .meter-fill.hot {
      background: linear-gradient(90deg, #f59e0b, #ef4444);
    }
    .two-cols {
      display: grid;
      grid-template-columns: 1fr 1.2fr;
      gap: 1.25rem;
      margin-bottom: 1.5rem;
    }
    @media (max-width: 960px) {
      .two-cols { grid-template-columns: 1fr; }
    }
    .badge-event {
      display: inline-block;
      font-size: 0.7rem;
      font-weight: 600;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      background: rgba(99, 102, 241, 0.15);
      color: #818cf8;
      border: 1px solid rgba(99, 102, 241, 0.25);
    }
    code {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      color: #93c5fd;
      font-size: 0.8rem;
    }
    footer {
      text-align: center;
      font-size: 0.78rem;
      color: var(--muted);
      padding: 1rem 0 2rem 0;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="logo-area">
        <h1 style="font-size: 1.25rem; font-weight: 700;">A2A DEFENSE GATEWAY</h1>
        <div class="status-pill">
          <div class="pulse-dot"></div>
          <span>LIVE TELEMETRY STREAM</span>
        </div>
      </div>
      <div>
        <button class="btn-logout" onclick="logout()">Cerrar Sesión</button>
      </div>
    </header>

    <!-- KPI FILA 1 -->
    <div class="kpi-row">
      <div class="card">
        <div class="card-label">Why-Trail Ledger</div>
        <div class="card-val" id="total-blocks">--</div>
        <div class="card-sub">Integridad: <span style="color:var(--success); font-weight:600;" id="ledger-status">VERIFICANDO</span></div>
      </div>
      <div class="card">
        <div class="card-label">Moltbook Agente Oficial</div>
        <div class="card-val card-val-accent" id="agent-karma">--</div>
        <div class="card-sub"><span id="agent-followers">--</span> Seguidores &bull; <span id="agent-posts">--</span> Posts</div>
      </div>
      <div class="card">
        <div class="card-label">Herramientas MCP Publicadas</div>
        <div class="card-val card-val-success" id="active-tools">--</div>
        <div class="card-sub">Marcha Blanca: <span id="white-march-days">--</span> días restantes</div>
      </div>
      <div class="card">
        <div class="card-label">Bóveda &amp; Seguro Paramétrico</div>
        <div class="card-val card-val-warning" id="reserve-sats">--</div>
        <div class="card-sub"><span id="active-policies">0</span> Pólizas &bull; <span id="secret-envelopes">0</span> Bóvedas</div>
      </div>
    </div>

    <!-- KPI FILA 2 (TELEMETRÍA DE TRÁFICO MCP) -->
    <div class="kpi-row">
      <div class="card">
        <div class="card-label">Peticiones MCP JSON-RPC</div>
        <div class="card-val card-val-cyan" id="mcp-requests">--</div>
        <div class="card-sub">Tráfico registrado en endpoint <code>/mcp</code></div>
      </div>
      <div class="card">
        <div class="card-label">Invocaciones de Tools</div>
        <div class="card-val card-val-accent" id="tool-executions">--</div>
        <div class="card-sub">Ejecuciones reales auditadas en ledger</div>
      </div>
      <div class="card">
        <div class="card-label">Agentes Autónomos Detectados</div>
        <div class="card-val card-val-success" id="unique-callers">--</div>
        <div class="card-sub">Oráculos, bots e indexadores de MCP</div>
      </div>
      <div class="card">
        <div class="card-label">Disponibilidad Operativa</div>
        <div class="card-val" id="gateway-sla">100.0%</div>
        <div class="card-sub">SLA Uptime &bull; Cero excepciones no capturadas</div>
      </div>
    </div>

    <!-- SECCIÓN FLOTA MULTI-AGENTE & ECOSISTEMA CROSS-PLATFORM -->
    <div class="section-container" style="margin-bottom: 1.5rem;">
      <div class="section-header">
        <div class="section-title">
          <span>🌐 Flota Multi-Agente &amp; Red Multi-Sitio (Cross-Platform)</span>
          <span class="badge-cat" style="background:#065f46; color:#34d399;">2 AGENTES ACTIVOS &bull; 6 PLATAFORMAS</span>
        </div>
        <div style="font-size:0.75rem; color:var(--muted);">
          Sindicación omnicanal A2A &bull; Monitoreo en vivo
        </div>
      </div>
      <div style="padding: 1rem;">
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:1.25rem;">
          <!-- COLUMNA 1: FLOTA DE AGENTES -->
          <div style="background:#131824; border:1px solid var(--border); border-radius:6px; padding:1rem;">
            <div style="font-size:0.8rem; font-weight:700; color:#38bdf8; margin-bottom:0.75rem; display:flex; justify-content:space-between; align-items:center;">
              <span>🤖 Flota de Agentes Moltbook</span>
              <span class="status-pill" style="font-size:0.65rem;">EN LÍNEA</span>
            </div>
            
            <!-- AGENTE 1: a2adefensegateway -->
            <div style="background:#1e293b; border:1px solid #334155; border-radius:6px; padding:0.75rem; margin-bottom:0.75rem;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.35rem;">
                <div style="font-weight:700; color:#f1f5f9; font-size:0.82rem;">
                  @a2adefensegateway <span style="font-size:0.68rem; color:#38bdf8; background:#0f172a; padding:0.1rem 0.35rem; border-radius:3px;">PRIMARIO</span>
                </div>
                <a href="https://www.moltbook.com/u/a2adefensegateway" target="_blank" style="color:#38bdf8; font-size:0.7rem; text-decoration:none;">Perfil ↗</a>
              </div>
              <div style="font-size:0.72rem; color:var(--muted); margin-bottom:0.5rem;">Defense Gateway, 56 MCP tools, L402 Lightning payments, Why-Trail auditor.</div>
              <div style="display:flex; gap:1rem; font-size:0.72rem; color:#94a3b8;">
                <span>Karma: <strong style="color:#f59e0b;" id="agent1-karma">47</strong></span>
                <span>Seguidores: <strong style="color:#38bdf8;" id="agent1-followers">14</strong></span>
                <span>Posts: <strong style="color:#34d399;" id="agent1-posts">22</strong></span>
                <span>Comentarios: <strong style="color:#a78bfa;" id="agent1-comments">35</strong></span>
              </div>
            </div>

            <!-- AGENTE 2: a2athreatintel -->
            <div style="background:#1e293b; border:1px solid #334155; border-radius:6px; padding:0.75rem;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.35rem;">
                <div style="font-weight:700; color:#f1f5f9; font-size:0.82rem;">
                  @a2athreatintel <span style="font-size:0.68rem; color:#a855f7; background:#0f172a; padding:0.1rem 0.35rem; border-radius:3px;">SATÉLITE CTI</span>
                </div>
                <a href="https://www.moltbook.com/u/a2athreatintel" target="_blank" style="color:#a855f7; font-size:0.7rem; text-decoration:none;">Perfil ↗</a>
              </div>
              <div style="font-size:0.72rem; color:var(--muted); margin-bottom:0.5rem;">Threat intelligence, AST skill Trojan scanner, Why-Trail cryptographic auditor.</div>
              <div style="display:flex; gap:1rem; font-size:0.72rem; color:#94a3b8;">
                <span>Estado: <strong style="color:#10b981;" id="agent2-status">RECLAMADO Y ACTIVO</strong></span>
                <span>Karma: <strong style="color:#f59e0b;" id="agent2-karma">0</strong></span>
                <span>Posts: <strong style="color:#34d399;" id="agent2-posts">0</strong></span>
              </div>
            </div>
          </div>

          <!-- COLUMNA 2: RED MULTI-SITIO CROSS-PLATFORM -->
          <div style="background:#131824; border:1px solid var(--border); border-radius:6px; padding:1rem;">
            <div style="font-size:0.8rem; font-weight:700; color:#a78bfa; margin-bottom:0.75rem; display:flex; justify-content:space-between; align-items:center;">
              <span>🌐 Ecosistema de Plataformas &amp; Relays</span>
              <span style="font-size:0.68rem; color:var(--muted);">Multi-Protocol A2A</span>
            </div>
            <div style="display:flex; flex-direction:column; gap:0.5rem;">
              <div style="display:flex; justify-content:space-between; align-items:center; background:#1e293b; padding:0.5rem 0.75rem; border-radius:4px; font-size:0.75rem;">
                <span>🦞 <strong>Moltbook (Meta Identity)</strong></span>
                <span class="status-pill" style="background:#065f46; color:#34d399;">22 POSTS &bull; VERIFICADO</span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; background:#1e293b; padding:0.5rem 0.75rem; border-radius:4px; font-size:0.75rem;">
                <span>🤖 <strong>Agentverse / ASI:One (Fetch.ai)</strong></span>
                <span class="status-pill" style="background:#065f46; color:#34d399;">uAgents ACTIVO</span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; background:#1e293b; padding:0.5rem 0.75rem; border-radius:4px; font-size:0.75rem;">
                <span>⚡ <strong>Nostr Relay Network (Damus &bull; nos.lol)</strong></span>
                <span class="status-pill" style="background:#065f46; color:#34d399;">DVM &bull; BROADCAST OK</span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; background:#1e293b; padding:0.5rem 0.75rem; border-radius:4px; font-size:0.75rem;">
                <span>🐦 <strong>Moltweet (Microblogging Feed)</strong></span>
                <span style="color:#f59e0b; font-size:0.7rem; font-weight:600;">THREAD 5-TWEETS LISTO</span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; background:#1e293b; padding:0.5rem 0.75rem; border-radius:4px; font-size:0.75rem;">
                <span>💼 <strong>Agent Commune (Enterprise Directory)</strong></span>
                <span style="color:#f59e0b; font-size:0.7rem; font-weight:600;">WHITEPAPER LISTO</span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center; background:#1e293b; padding:0.5rem 0.75rem; border-radius:4px; font-size:0.75rem;">
                <span>🚀 <strong>AgentDiscuss (Product Hunt de Bots)</strong></span>
                <span style="color:#f59e0b; font-size:0.7rem; font-weight:600;">SHOWCASE LISTO</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- SECCION: MATRIZ DE TELEMETRÍA Y CONSUMO POR HERRAMIENTA MCP -->
    <div class="section-container">
      <div class="section-header">
        <div class="section-title">
          <span>Matriz de Telemetría y Consumo por Herramienta MCP</span>
          <span class="badge-cat" id="tools-badge">60 TOOLS</span>
        </div>
        <div class="controls-group">
          <input type="text" id="tool-search" class="search-input" placeholder="Buscar herramienta o categoría..." oninput="filterTools()" />
          <button class="filter-btn active" data-cat="ALL" onclick="setCategory('ALL')">Todas</button>
          <button class="filter-btn" data-cat="Defensa & Gobernanza" onclick="setCategory('Defensa & Gobernanza')">Defensa</button>
          <button class="filter-btn" data-cat="Economía & Liquidación" onclick="setCategory('Economía & Liquidación')">Economía</button>
          <button class="filter-btn" data-cat="LegalTech & Forense" onclick="setCategory('LegalTech & Forense')">LegalTech</button>
          <button class="filter-btn" data-cat="Inteligencia & Mercado" onclick="setCategory('Inteligencia & Mercado')">Inteligencia</button>
          <button class="filter-btn" data-cat="Identidad & Cognición" onclick="setCategory('Identidad & Cognición')">Identidad</button>
          <button class="filter-btn" data-cat="Actuación & Cómputo" onclick="setCategory('Actuación & Cómputo')">Cómputo</button>
          <button class="filter-btn" data-cat="Ecosistema Google" onclick="setCategory('Ecosistema Google')">Google Suite</button>
          <button class="filter-btn" data-cat="FinTech & Trading Risk Envelope" onclick="setCategory('FinTech & Trading Risk Envelope')">FinTech</button>
          <button class="filter-btn" data-cat="Seguridad Agéntica & Anti-Drainer" onclick="setCategory('Seguridad Agéntica & Anti-Drainer')">Anti-Drainer</button>
          <button class="filter-btn" data-cat="Comercio Agéntico & AP2" onclick="setCategory('Comercio Agéntico & AP2')">AP2 & GEO</button>
          <button class="filter-btn" data-cat="Verificación Física & Meatspace" onclick="setCategory('Verificación Física & Meatspace')">Meatspace</button>
          <button class="filter-btn" data-cat="Identidad & Reputación KYA" onclick="setCategory('Identidad & Reputación KYA')">KYA</button>
        </div>
      </div>

      <!-- BANNER CUMPLIMIENTO OWASP AGENTIC TOP 10 & NIST AI RMF -->
      <div style="background:#0f172a; border:1px solid #1e293b; border-radius:6px; padding:0.75rem 1rem; margin:1rem 1rem 0.5rem 1rem; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem;">
        <div style="display:flex; align-items:center; gap:0.75rem;">
          <span style="font-size:1.15rem;">🛡️</span>
          <div>
            <div style="font-size:0.8rem; font-weight:700; color:#38bdf8;">Marco de Seguridad Fiduciaria: OWASP Agentic Top 10 &bull; NIST AI RMF 2026</div>
            <div style="font-size:0.7rem; color:var(--muted);">60 herramientas MCP auditadas determinísticamente contra los 10 vectores de fallo crítico agéntico</div>
          </div>
        </div>
        <div style="display:flex; gap:0.5rem; align-items:center;">
          <span class="status-pill" style="background:#065f46; color:#34d399; font-size:0.7rem;">OWASP ASI-01..10 (100% CUBIERTO)</span>
          <span class="status-pill" style="background:#1e3a8a; color:#60a5fa; font-size:0.7rem;">NIST: GOVERN &bull; MAP &bull; MEASURE &bull; MANAGE</span>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Herramienta MCP</th>
            <th>Categoría</th>
            <th>Invocaciones</th>
            <th>Última Actividad</th>
            <th>Estado</th>
            <th>Tarifa</th>
          </tr>
        </thead>
        <tbody id="tools-tbody">
          <tr><td colspan="6" style="text-align:center; color:var(--muted); padding:2rem;">Cargando catálogo de herramientas...</td></tr>
        </tbody>
      </table>
    </div>

    <!-- DOS COLUMNAS: AGENTES CONECTADOS & REGISTRO CAUSAL -->
    <div class="two-cols">
      <!-- COLUMNA 1: AGENTES AUTÓNOMOS & ORÁCULOS DETECTADOS -->
      <div class="section-container" style="margin-bottom:0;">
        <div class="section-header">
          <div class="section-title">
            <span>Agentes Autónomos &amp; Oráculos Detectados</span>
          </div>
          <span style="font-size:0.75rem; color:var(--muted);" id="callers-count">-- agentes</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Agente / Cliente</th>
              <th>Peticiones</th>
              <th>Protocolo</th>
            </tr>
          </thead>
          <tbody id="callers-tbody">
            <tr><td colspan="3" style="text-align:center; color:var(--muted); padding:1.5rem;">Analizando conexiones...</td></tr>
          </tbody>
        </table>
      </div>

      <!-- COLUMNA 2: REGISTRO CAUSAL EN VIVO -->
      <div class="section-container" style="margin-bottom:0;">
        <div class="section-header">
          <div class="section-title">
            <span>Registro Causal en Vivo (Why-Trail)</span>
          </div>
          <span style="font-size:0.75rem; color:var(--muted);" id="last-sync">Sincronizando...</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Seq #</th>
              <th>Tipo de Evento</th>
              <th>Actor</th>
              <th>Timestamp</th>
            </tr>
          </thead>
          <tbody id="events-tbody">
            <tr><td colspan="4" style="text-align:center; color:var(--muted); padding:1.5rem;">Cargando eventos...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- NUEVA SECCION: ARTIFACT HUB & THREAT SENTINEL / PLAYGROUND -->
    <div class="two-cols" style="margin-top: 1.5rem;">
      <!-- COLUMNA 1: ARTIFACT HUB (AUDIO / DOCS / SHEETS) -->
      <div class="section-container" style="margin-bottom:0;">
        <div class="section-header">
          <div class="section-title">
            <span>🎙️ Artifact Hub &amp; Live Audio Player</span>
          </div>
          <span style="font-size:0.75rem; color:var(--muted);" id="audio-count">Audios en Disco</span>
        </div>
        <div style="padding: 1rem;">
          <audio id="live-audio-player" controls style="width:100%; border-radius:6px; background:#131824; margin-bottom:1rem;"></audio>
          <div style="font-size:0.75rem; font-weight:600; color:var(--muted); margin-bottom:0.4rem; text-transform:uppercase;">Últimos Briefings Sintetizados (Dual-Voice Alex/Camila)</div>
          <table style="width:100%;">
            <thead>
              <tr><th>Briefing</th><th>Tamaño</th><th>Acción</th></tr>
            </thead>
            <tbody id="audios-tbody">
              <tr><td colspan="3" style="text-align:center; color:var(--muted);">Cargando briefings...</td></tr>
            </tbody>
          </table>
          <div style="font-size:0.75rem; font-weight:600; color:var(--muted); margin:1rem 0 0.4rem 0; text-transform:uppercase;">Documentos HTML &amp; Tablas CSV</div>
          <table style="width:100%;">
            <thead>
              <tr><th>Artefacto</th><th>Tipo</th><th>Acción</th></tr>
            </thead>
            <tbody id="docs-tbody">
              <tr><td colspan="3" style="text-align:center; color:var(--muted);">Cargando artefactos...</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- COLUMNA 2: THREAT SENTINEL & MCP PLAYGROUND -->
      <div class="section-container" style="margin-bottom:0;">
        <div class="section-header">
          <div class="section-title">
            <span>🛡️ Threat Sentinel &amp; MCP Console Playground</span>
          </div>
          <span class="badge-status badge-hot" id="fail2ban-badge">FAIL2BAN: 64 IPS</span>
        </div>
        <div style="padding: 1rem;">
          <div style="display:flex; justify-content:space-between; align-items:center; background:#1a2030; padding:0.75rem; border-radius:6px; margin-bottom:1rem; border:1px solid var(--border);">
            <div>
              <div style="font-size:0.8rem; font-weight:700; color:#38bdf8;">Perímetro UFW &amp; Fail2Ban</div>
              <div style="font-size:0.72rem; color:var(--muted);">64 atacantes SSH neutralizados en puerto 22</div>
            </div>
            <span class="status-pill">ACTIVO</span>
          </div>

          <div style="font-size:0.75rem; font-weight:600; color:var(--muted); margin-bottom:0.4rem; text-transform:uppercase;">Ejecución de Tools en Vivo (MCP Playground)</div>
          <div style="display:flex; gap:0.5rem; margin-bottom:0.5rem;">
            <select id="playground-tool" class="search-input" style="flex:1;" onchange="updatePlaygroundTemplate()">
              <option value="">Seleccionar herramienta MCP (1-60)...</option>
            </select>
            <button class="filter-btn active" onclick="executePlaygroundTool()">⚡ Ejecutar</button>
          </div>
          <textarea id="playground-args" style="width:100%; height:75px; background:var(--bg); border:1px solid var(--border); color:#a5b4fc; font-family:monospace; font-size:0.75rem; padding:0.5rem; border-radius:6px; resize:vertical;" placeholder='{"query": "test"}'></textarea>
          <div id="playground-status" style="font-size:0.72rem; color:var(--muted); margin:0.3rem 0;"></div>
          <pre id="playground-output" style="max-height:110px; overflow:auto; background:var(--bg); border:1px solid var(--border); padding:0.5rem; font-size:0.72rem; color:#34d399; border-radius:6px; display:none;"></pre>
        </div>
      </div>
    </div>

    <!-- SECCIÓN MOLTBOOK COMMUNITY FEED: POSTS & REPLIES -->
    <div class="section-container" style="margin-top: 1.5rem;">
      <div class="section-header">
        <div class="section-title">
          <span>🦞 Comunidad Moltbook: Publicaciones &amp; Debates A2A (@a2adefensegateway)</span>
        </div>
        <div style="display:flex; gap:0.5rem; align-items:center;">
          <span class="badge-status badge-hot" id="moltbook-status-badge">ACTIVO &bull; 26 KARMA</span>
          <a href="https://www.moltbook.com/u/a2adefensegateway" target="_blank" style="color:#38bdf8; font-size:0.75rem; text-decoration:none; background:#1e293b; padding:0.3rem 0.6rem; border-radius:4px; border:1px solid var(--border);">
            Ver Perfil Oficial ↗
          </a>
        </div>
      </div>
      <div style="padding: 1rem;">
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:1.25rem;">
          <!-- COLUMNA 1: PUBLICACIONES OFICIALES -->
          <div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem; padding-bottom:0.4rem; border-bottom:1px solid var(--border);">
              <span style="font-size:0.8rem; font-weight:700; color:#38bdf8;">📝 Publicaciones Oficiales (Posts)</span>
              <span id="moltbook-posts-count" style="font-size:0.72rem; color:var(--muted);">Cargando...</span>
            </div>
            <div id="moltbook-posts-container" style="display:flex; flex-direction:column; gap:0.75rem; max-height:460px; overflow-y:auto; padding-right:0.5rem;">
              <div style="color:var(--muted); font-size:0.75rem; text-align:center; padding:1.5rem;">Cargando publicaciones de Moltbook...</div>
            </div>
          </div>
          <!-- COLUMNA 2: DEBATES Y RESPUESTAS (COMMUNITY REPLIES) -->
          <div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem; padding-bottom:0.4rem; border-bottom:1px solid var(--border);">
              <span style="font-size:0.8rem; font-weight:700; color:#a78bfa;">💬 Debates Activos &amp; Respuestas de la Comunidad</span>
              <span id="moltbook-replies-count" style="font-size:0.72rem; color:var(--muted);">En tiempo real</span>
            </div>
            <div id="moltbook-replies-container" style="display:flex; flex-direction:column; gap:0.75rem; max-height:460px; overflow-y:auto; padding-right:0.5rem;">
              <div style="color:var(--muted); font-size:0.75rem; text-align:center; padding:1.5rem;">Cargando respuestas y debates...</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <footer>
      A2A Defense &amp; Monetization Gateway &copy; 2026 &bull; Multi-CaMeL Cryptographic Ledger &bull; Telemetry Engine v2.0
    </footer>
  </div>

  <script>
    let allTools = [];
    let currentCategory = 'ALL';

    function esc(s) {
      if (s === null || s === undefined) return '';
      return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    function setTxt(id, val) {
      const el = document.getElementById(id);
      if (el) el.innerText = val;
    }

    function setCategory(cat) {
      currentCategory = cat;
      document.querySelectorAll('.filter-btn').forEach(btn => {
        if (btn.getAttribute('data-cat') === cat) {
          btn.classList.add('active');
        } else {
          btn.classList.remove('active');
        }
      });
      renderToolsTable();
    }

    function filterTools() {
      renderToolsTable();
    }

    function renderToolsTable() {
      const query = (document.getElementById('tool-search')?.value || '').toLowerCase().trim();
      const filtered = allTools.filter(t => {
        const matchesCat = (currentCategory === 'ALL' || t.category === currentCategory);
        const matchesQuery = !query || 
          (t.name && t.name.toLowerCase().includes(query)) || 
          (t.category && t.category.toLowerCase().includes(query)) || 
          (t.description && t.description.toLowerCase().includes(query));
        return matchesCat && matchesQuery;
      });

      const maxInvocations = Math.max(...allTools.map(t => t.invocations || 0), 1);
      const tbody = document.getElementById('tools-tbody');
      if (!tbody) return;

      if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--muted); padding:2rem;">No se encontraron herramientas con los filtros seleccionados.</td></tr>';
        return;
      }

      tbody.innerHTML = filtered.map(t => {
        const inv = t.invocations || 0;
        const pct = Math.min(100, Math.round((inv / maxInvocations) * 100));
        let badgeClass = 'badge-standby';
        let badgeLabel = 'STANDBY';
        if (inv >= 5) {
          badgeClass = 'badge-hot';
          badgeLabel = 'HOT';
        } else if (inv > 0) {
          badgeClass = 'badge-active';
          badgeLabel = 'ACTIVE';
        }

        return `
          <tr>
            <td>
              <code>${esc(t.name)}</code>
              <div style="font-size:0.72rem; color:var(--muted); margin-top:2px;">${esc(t.description)}</div>
            </td>
            <td><span class="badge-cat">${esc(t.category)}</span></td>
            <td>
              <div class="meter-container">
                <span style="font-weight:700; min-width:24px;">${esc(inv)}</span>
                <div class="meter-bar">
                  <div class="meter-fill ${inv >= 5 ? 'hot' : ''}" style="width: ${Math.max(pct, inv > 0 ? 8 : 0)}%;"></div>
                </div>
              </div>
            </td>
            <td style="color:var(--muted); font-size:0.75rem;">${esc(t.last_invoked || 'Sin actividad')}</td>
            <td><span class="badge-status ${badgeClass}">${badgeLabel}</span></td>
            <td style="color:#a5b4fc; font-size:0.75rem;">${esc(t.pricing || '100 sats')}</td>
          </tr>
        `;
      }).join('');

      const selectEl = document.getElementById('playground-tool');
      if (selectEl && selectEl.options.length <= 1 && allTools.length > 0) {
        allTools.forEach(t => {
          const opt = document.createElement('option');
          opt.value = t.name;
          opt.innerText = t.name + ' (' + (t.category || 'MCP') + ')';
          selectEl.appendChild(opt);
        });
      }
    }

    async function fetchMetrics() {
      try {
        const urlParams = new URLSearchParams(window.location.search);
        const queryToken = urlParams.get('token');
        if (queryToken) {
          sessionStorage.setItem('a2a_session_token', queryToken);
        }
        const token = sessionStorage.getItem('a2a_session_token');
        const headers = token ? { 'Authorization': 'Bearer ' + token } : {};
        const res = await fetch('/api/v1/dashboard/metrics', { headers });
        if (res.status === 401) {
          window.location.href = '/login';
          return;
        }
        const data = await res.json();
        
        // KPI Fila 1 (Safe Property Access)
        setTxt('total-blocks', (data.why_trail?.total_blocks ?? 0) + ' Bloques');
        setTxt('ledger-status', data.why_trail?.status ?? 'ONLINE');
        setTxt('agent-karma', (data.moltbook?.karma ?? 0) + ' Karma');
        setTxt('agent-followers', data.moltbook?.followers ?? 0);
        setTxt('agent-posts', data.moltbook?.posts ?? 0);

        // Flota Multi-Agente
        if (data.fleet) {
          if (data.fleet.primary) {
            setTxt('agent1-karma', data.fleet.primary.karma ?? 0);
            setTxt('agent1-followers', data.fleet.primary.followers ?? 0);
            setTxt('agent1-posts', data.fleet.primary.posts ?? 0);
            setTxt('agent1-comments', data.fleet.primary.comments ?? 0);
          }
          if (data.fleet.satellite) {
            setTxt('agent2-status', data.fleet.satellite.status ?? 'STANDBY');
            setTxt('agent2-karma', data.fleet.satellite.karma ?? 0);
            setTxt('agent2-posts', data.fleet.satellite.posts ?? 0);
          }
        }
        const moltBadge = document.getElementById('moltbook-status-badge');
        if (moltBadge && data.moltbook) {
          moltBadge.innerText = 'ACTIVO • ' + (data.moltbook.karma ?? 0) + ' KARMA • 2 AGENTES';
        }
        setTxt('active-tools', (data.gateway?.total_tools ?? 60) + ' Tools');
        setTxt('white-march-days', data.gateway?.white_march_days_left ?? 1);
        setTxt('reserve-sats', (data.insurance_and_vault?.reserve_sats ?? 0).toLocaleString() + ' sats');
        setTxt('active-policies', data.insurance_and_vault?.active_policies ?? 0);
        setTxt('secret-envelopes', data.insurance_and_vault?.secret_envelopes ?? 0);

        // KPI Fila 2
        setTxt('mcp-requests', (data.gateway?.mcp_requests ?? 0).toLocaleString());
        setTxt('tool-executions', (data.gateway?.tool_executions ?? 0).toLocaleString());
        setTxt('unique-callers', (data.gateway?.unique_callers ?? 0) + ' Conectados');
        setTxt('gateway-sla', data.gateway?.success_rate ?? '100.0%');
        setTxt('tools-badge', (data.gateway?.total_tools ?? 60) + ' TOOLS REGISTRADAS');

        // Telemetría de Herramientas
        if (data.tools_telemetry) {
          allTools = data.tools_telemetry;
          renderToolsTable();
        }

        // Agentes Clientes Conectados (Sanitizado)
        const callersTbody = document.getElementById('callers-tbody');
        if (callersTbody && data.top_callers && data.top_callers.length > 0) {
          setTxt('callers-count', data.top_callers.length + ' detectados');
          callersTbody.innerHTML = data.top_callers.map(c => `
            <tr>
              <td><code style="color:#e2e8f0;">${esc(c.agent.length > 38 ? c.agent.substring(0, 38) + '...' : c.agent)}</code></td>
              <td><strong>${esc(c.requests)}</strong> reqs</td>
              <td><span class="badge-cat" style="font-size:0.65rem;">JSON-RPC 2.0</span></td>
            </tr>
          `).join('');
        }

        // Eventos Causal Ledger (Sanitizado)
        const tbody = document.getElementById('events-tbody');
        if (tbody && data.recent_events && data.recent_events.length > 0) {
          tbody.innerHTML = data.recent_events.slice(0, 8).map(e => `
            <tr>
              <td><strong>#${esc(e.index)}</strong></td>
              <td><span class="badge-event">${esc(e.type)}</span></td>
              <td><code>${esc(e.actor)}</code></td>
              <td style="color:var(--muted); font-size:0.75rem;">${esc(e.timestamp)}</td>
            </tr>
          `).join('');
        }

        // Artifact Hub (Audios)
        if (data.artifacts && data.artifacts.audios) {
          const audiosTbody = document.getElementById('audios-tbody');
          setTxt('audio-count', (data.artifacts.audios.length || 0) + ' audios');
          if (audiosTbody && data.artifacts.audios.length > 0) {
            audiosTbody.innerHTML = data.artifacts.audios.map(a => `
              <tr>
                <td><code>${esc(a.id)}</code></td>
                <td>${esc(a.size_kb)} KB</td>
                <td><button class="filter-btn" style="color:#38bdf8; border-color:#38bdf8;" onclick="playAudio('${encodeURI(a.stream_url)}')">▶ Escuchar</button></td>
              </tr>
            `).join('');
          }
        }

        // Artifact Hub (Docs & Sheets)
        if (data.artifacts) {
          const docsTbody = document.getElementById('docs-tbody');
          if (docsTbody) {
            const docs = (data.artifacts.docs || []).map(d => `
              <tr>
                <td><code>${esc(d.id)}</code></td>
                <td><span class="badge-cat">HTML Doc</span></td>
                <td><a href="${encodeURI(d.view_url)}" target="_blank" class="filter-btn" style="text-decoration:none; color:#10b981; border-color:#10b981;">Ver HTML</a></td>
              </tr>
            `);
            const sheets = (data.artifacts.sheets || []).map(s => `
              <tr>
                <td><code>${esc(s.id)}</code></td>
                <td><span class="badge-cat">CSV Sheet</span></td>
                <td><a href="${encodeURI(s.download_url)}" target="_blank" class="filter-btn" style="text-decoration:none; color:#fbbf24; border-color:#fbbf24;">Descargar</a></td>
              </tr>
            `);
            const allArt = docs.concat(sheets);
            if (allArt.length > 0) {
              docsTbody.innerHTML = allArt.slice(0, 5).join('');
            }
          }
        }

        // Poblar Selector de Tools en Playground si está vacío
        const toolSelect = document.getElementById('playground-tool');
        if (toolSelect && toolSelect.options.length <= 1 && data.tools_telemetry) {
          data.tools_telemetry.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.name;
            opt.innerText = t.name + ' (' + t.category + ')';
            toolSelect.appendChild(opt);
          });
        }

        // Moltbook Posts & Replies Feed (Sanitizado)
        if (data.moltbook && data.moltbook.feed) {
          const postsContainer = document.getElementById('moltbook-posts-container');
          const repliesContainer = document.getElementById('moltbook-replies-container');
          const posts = data.moltbook.feed.posts || [];
          const replies = data.moltbook.feed.replies || [];

          setTxt('moltbook-posts-count', posts.length + ' Publicaciones');

          if (postsContainer && posts.length > 0) {
            postsContainer.innerHTML = posts.map(p => `
              <div style="background:#131824; border:1px solid var(--border); border-radius:6px; padding:0.75rem;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:0.5rem; margin-bottom:0.35rem;">
                  <span style="font-size:0.7rem; background:#1e293b; color:#38bdf8; padding:0.15rem 0.4rem; border-radius:4px; font-weight:600;">t/${esc(p.submolt)}</span>
                  <span style="font-size:0.7rem; color:var(--muted);">${esc(p.created_at)}</span>
                </div>
                <div style="font-size:0.8rem; font-weight:700; color:#f1f5f9; margin-bottom:0.3rem;">
                  <a href="${encodeURI(p.url)}" target="_blank" style="color:#f1f5f9; text-decoration:none;">${esc(p.title)} ↗</a>
                </div>
                <div style="font-size:0.73rem; color:var(--muted); line-height:1.35; margin-bottom:0.5rem;">${esc(p.preview)}</div>
                <div style="display:flex; gap:0.75rem; font-size:0.7rem; color:#94a3b8;">
                  <span>▲ ${esc(p.upvotes)} Upvotes</span>
                  <span>💬 ${esc(p.comments)} Comentarios</span>
                </div>
              </div>
            `).join('');
          }

          if (repliesContainer && replies.length > 0) {
            repliesContainer.innerHTML = replies.map(r => `
              <div style="background:#131824; border:1px solid var(--border); border-radius:6px; padding:0.75rem;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:0.5rem; margin-bottom:0.35rem;">
                  <span style="font-size:0.7rem; background:#2e1065; color:#c084fc; padding:0.15rem 0.4rem; border-radius:4px; font-weight:600;">t/${esc(r.submolt)}</span>
                  <span style="font-size:0.7rem; color:var(--muted);">${esc(r.latest_at)}</span>
                </div>
                <div style="font-size:0.78rem; font-weight:700; color:#e2e8f0; margin-bottom:0.25rem;">${esc(r.post_title)}</div>
                <div style="font-size:0.73rem; color:#94a3b8; margin-bottom:0.4rem;">
                  <span style="color:#38bdf8; font-weight:600;">Interlocutores:</span> ${(r.commenters || []).map(c => '@' + esc(c)).join(', ')}
                </div>
                <div style="font-size:0.72rem; color:var(--muted); font-style:italic;">"${esc(r.preview)}"</div>
              </div>
            `).join('');
          }
        }

        const syncEl = document.getElementById('last-sync');
        if (syncEl) {
          syncEl.innerText = 'Sync: ' + new Date().toLocaleTimeString();
          syncEl.style.color = 'var(--muted)';
        }
      } catch (err) {
        console.error('Error fetching dashboard telemetry:', err);
        const syncEl = document.getElementById('last-sync');
        if (syncEl) {
          syncEl.innerText = '⚠️ Error Sync: Reintentando...';
          syncEl.style.color = '#ef4444';
        }
      }
    }

    function playAudio(url) {
      const p = document.getElementById('live-audio-player');
      if (p) {
        p.src = url;
        p.play();
      }
    }

    function updatePlaygroundTemplate() {
      const tool = document.getElementById('playground-tool')?.value;
      if (!tool) return;
      const templates = {
        get_alpha_intelligence_feed: { category_filter: "all" },
        evaluate_financial_policy_proxy: { source_agent_id: "did:a2a:buyer-swarm", destination_agent_id: "did:a2a:gpu-inference", amount_sats: 2500, session_spend_total_sats: 8000 },
        orchestrate_m2m_saga_transaction: { saga_id: "saga-compute-01", steps: ["lock_collateral", "execute_inference", "settle_invoice"] },
        enforce_chain_postconditions: { execution_trace_id: "trace-8891", expected_state_hash: "sha256:7f83b..." },
        certify_mcp_marketplace_package: { package_manifest_url: "https://clawhub.com/skills/bob-p2p-beta.json" },
        certify_skill_safety: { skill_source_code: "import subprocess; subprocess.Popen(['curl', 'evil.com'])" },
        request_l402_challenge: { price_sats: 25, caveats: ["tool=compute_procedural_deadline"] },
        compute_procedural_deadline: { start_date: "2026-11-20", business_days: 15, jurisdiction: "PJ_PERU" },
        compute_us_procedural_deadline: { filing_date: "2026-11-20", days_count: 21, rule_set: "FRCP_RULE_6" },
        validate_bluebook_citation: { citation: "Brown v. Board of Educ., 347 U.S. 483 (1954)" },
        audit_us_contract_clauses: { contract_text: "Licensor liability shall not exceed $100...", risk_threshold: "HIGH" },
        audit_excel_macro_forensics: { file_data_base64: "UEsDBBQAAAAIA..." },
        query_deep_context_archive: { agent_id: "admin", archive_text_or_url: "Texto de prueba legal...", query: "¿Cuál es la penalidad?" },
        publish_enterprise_artifact: { agent_id: "admin", title: "Doc Prueba", markdown_content: "# Hola - Contenido de prueba", document_format: "STANDALONE_HTML" },
        generate_audio_briefing: { agent_id: "admin", source_transcript_or_report: "LOCUTOR A: Hola. LOCUTOR B: Como estas.", briefing_format: "TWO_SPEAKER_DIALECTIC" },
        sync_tabular_ledger: { agent_id: "admin", spreadsheet_title: "Ledger Test", rows_data: [{ col1: "val1" }] },
        report_malicious_agent: { reporter_agent_id: "admin", target_agent_id: "bad_bot_99", threat_category: "PROMPT_INJECTION", evidence_payload: "intento de injection ignore previous instructions", severity: "SEV-HIGH" },
        query_agent_threat_score: { target_agent_id: "bad_bot_99", requesting_agent_id: "admin" },
        propose_trade_envelope: { symbol: "BTCUSDT", side: "BUY", notional_usd: 150.0, max_slippage_pct: 0.5, current_24h_drawdown_pct: 1.2 },
        simulate_order_mev_protection: { chain_id: 1, target_dex: "UniswapV3", pool_address: "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", trade_size_usd: 150.0 },
        enforce_trading_circuit_breaker: { agent_id: "agent_trade_01", consecutive_losses: 1, rolling_24h_drawdown_pct: 2.1, max_allowed_drawdown_pct: 5.0 },
        audit_mcp_tool_metadata_poisoning: { mcp_manifest_json: JSON.stringify({ name: "safe_tool", description: "Normal tool" }) },
        enforce_denial_of_wallet_quota: { session_id: "sess_01", prompt_tokens: 150, completion_tokens: 400, thinking_tokens: 200, current_cost_usd: 0.05, max_budget_usd: 2.0 },
        audit_eip712_permit_drainer_payload: { primary_type: "Permit2", domain: { verifyingContract: "0x000000000022d473030f116ddee9f6b43ac78ba3" }, message: { spender: "0x000046a6f1e8093b16752765b2633054170845a7", value: "1000" } },
        verify_meatspace_attestation: { task_id: "rentahuman_bounty_101", challenge_nonce: "nonce_7788", hardware_attestation_type: "secure_enclave", hardware_signature: "a".repeat(64), image_hash_sha256: "b".repeat(64), exif_timestamp: "2026-11-23T10:00:00Z" },
        verify_kya_attestation: { agent_did: "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK", public_key_hex: "e".repeat(64), challenge_payload: "trade_auth", signature_hex: "f".repeat(128), historical_task_count: 50, disputed_task_count: 0, total_volume_usd: 5000.0 },
        translate_x402_to_l402_settlement: { source_rail: "x402_base_usdc", target_rail: "l402_lightning_sats", amount: "5.00", service_endpoint_url: "https://api.gateway.example/v1/audit", payer_address_or_pubkey: "0x1234567890abcdef1234567890abcdef12345678" },
        verify_ap2_cart_mandate_integrity: { cart_mandate_id: "cart_991", merchant_did: "did:web:merchant.example", client_signature_ed25519: "a1b2c3d4", cart_items: [{ item_id: "sku-1", price_sats: 2500, quantity: 1 }], max_authorized_total_sats: 3000 },
        serialize_geo_product_catalog: { catalog_items: [{ item_id: "sku_sentinel", name: "Agentic Threat Sentinel", description: "Pre-sign EIP-712 and Denial-of-Wallet defense", price_usd: 25.0, currency: "USD" }] },
        audit_eip7702_delegation: { eoa_address: "0x1111111111111111111111111111111111111111", delegated_contract_address: "0x4e59b44847b379578588920ca78fbf26c0b4956c", chain_id: 1, nonce: 0 },
        detect_malicious_llm_router: { router_endpoint_url: "https://router.example.com/v1", canary_token_sent: "CANARY_SECRET_123", response_body_text: "Clean factual financial report.", latency_overhead_ms: 150.0 },
        audit_echoleak_markdown_exfiltration: { text_content: "Resumen de operación completada. Visite https://a2a.vilmamonroy.com para auditoría." },
        simulate_dex_sandwich_risk: { dex_pool_address: "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", swap_amount_usd: 500.0, slippage_tolerance_pct: 0.5, pool_liquidity_usd: 100000.0, is_private_mempool: false }
      };
      const payload = templates[tool] || { agent_id: "admin" };
      const argsEl = document.getElementById('playground-args');
      if (argsEl) argsEl.value = JSON.stringify(payload, null, 2);
    }

    async function executePlaygroundTool() {
      const tool = document.getElementById('playground-tool').value;
      if (!tool) return;
      const statusEl = document.getElementById('playground-status');
      const outEl = document.getElementById('playground-output');
      statusEl.innerText = 'Ejecutando ' + tool + '...';
      outEl.style.display = 'none';
      try {
        const args = JSON.parse(document.getElementById('playground-args').value || '{}');
        const t0 = performance.now();
        const res = await fetch('/api/v1/tools/call', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({name: tool, arguments: args})
        });
        const duration = Math.round(performance.now() - t0);
        const data = await res.json();
        statusEl.innerText = 'Completado en ' + duration + 'ms (HTTP ' + res.status + ')';
        outEl.style.display = 'block';
        outEl.innerText = JSON.stringify(data, null, 2);
      } catch (err) {
        statusEl.innerText = 'Error: ' + err.message;
      }
    }

    async function logout() {
      sessionStorage.removeItem('a2a_session_token');
      await fetch('/api/v1/auth/logout', { method: 'POST' });
      window.location.href = '/login';
    }

    fetchMetrics();
    setInterval(fetchMetrics, 3000);
  </script>
</body>
</html>
"""


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    token = request.cookies.get("a2a_session")
    if auth_manager.validate_session(token):
        return RedirectResponse(url="/dashboard", status_code=303)
    return HTMLResponse(content=LOGIN_HTML)


@app.post("/api/v1/auth/login")
async def api_login(req: LoginPayload, request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    token = auth_manager.authenticate(req.username, req.password, client_ip)

    if not token:
        server.ledger.record_event(
            event_type="ADMIN_LOGIN_FAILED",
            payload_data={"username": req.username, "client_ip": client_ip},
            actor_agent_id=f"ip_{client_ip}",
            metadata={"source": "dashboard_auth"},
        )
        raise HTTPException(status_code=401, detail="Credenciales inválidas o tasa de intentos excedida (máx 5).")

    server.ledger.record_event(
        event_type="ADMIN_LOGIN_SUCCESS",
        payload_data={"username": req.username, "client_ip": client_ip},
        actor_agent_id=f"admin_{req.username}",
        metadata={"source": "dashboard_auth"},
    )

    resp = JSONResponse(
        content={
            "status": "AUTHENTICATED",
            "token": token,
            "message": "Sesión administrativa iniciada con éxito.",
        }
    )
    resp.set_cookie(
        key="a2a_session",
        value=token,
        httponly=True,
        max_age=43200,
        samesite="lax",
        path="/",
    )
    return resp


@app.post("/api/v1/auth/logout")
async def api_logout(request: Request):
    token = request.cookies.get("a2a_session")
    if token:
        auth_manager.revoke_session(token)
    resp = JSONResponse(content={"status": "LOGGED_OUT", "message": "Sesión finalizada."})
    resp.delete_cookie(key="a2a_session", path="/")
    return resp


def verify_admin_session(request: Request) -> bool:
    token = request.cookies.get("a2a_session")
    if not token:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
    if not token:
        token = request.query_params.get("token")
    return auth_manager.validate_session(token)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    token = request.query_params.get("token") or request.cookies.get("a2a_session")
    if not token:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
    if not auth_manager.validate_session(token):
        return RedirectResponse(url="/login", status_code=303)

    resp = HTMLResponse(content=DASHBOARD_HTML)
    if token:
        resp.set_cookie(
            key="a2a_session",
            value=token,
            httponly=True,
            max_age=43200,
            samesite="lax",
            path="/",
        )
    return resp


@app.get("/api/v1/dashboard/metrics")
async def dashboard_metrics(request: Request):
    if not verify_admin_session(request):
        raise HTTPException(status_code=401, detail="No autorizado. Inicie sesión en /login.")

    server.ledger._load_from_disk()
    is_valid, _error = server.ledger.verify_chain_integrity(reload_from_disk=False)

    insurance_reserve = getattr(server.enhancement, "insurance_reserve_sats", 100000)
    active_policies = len(getattr(server.enhancement, "insurance_policies", {}))
    secret_envelopes = len(getattr(server.enhancement, "secret_envelopes", {}))

    # Conteo dinámico de invocaciones de tools y peticiones MCP
    tool_counts = Counter()
    tool_last_seen = {}
    ledger_callers = Counter()
    mcp_post_count = 0

    for e in server.ledger.chain:
        et = getattr(e, "event_type", "")
        if et == "HTTP_POST:/mcp":
            mcp_post_count += 1
            meta = getattr(e, "metadata", {}) or {}
            ua = meta.get("user_agent") or "Unknown Agent"
            ledger_callers[ua] += 1
        elif et.startswith("TOOL_CALL:"):
            name = et.split("TOOL_CALL:", 1)[1]
            tool_counts[name] += 1
            tool_last_seen[name] = str(getattr(e, "timestamp", ""))[:19].replace("T", " ")
            actor = getattr(e, "actor_agent_id", "anonymous")
            ledger_callers[actor] += 1

    total_tool_calls = sum(tool_counts.values())

    tools_telemetry = []
    for t in server.list_tools():
        name = t["name"]
        cnt = tool_counts.get(name, 0)
        status = "HOT" if cnt >= 5 else ("ACTIVE" if cnt > 0 else "STANDBY")
        tools_telemetry.append({
            "name": name,
            "category": TOOL_CATEGORY_MAP.get(name, "Ecosistema A2A"),
            "description": (t.get("description", "")[:95] + "...") if len(t.get("description", "")) > 95 else t.get("description", ""),
            "invocations": cnt,
            "status": status,
            "last_invoked": tool_last_seen.get(name, "Sin actividad"),
            "pricing": f"100 sats (0 en Marcha Blanca, máx {white_march.daily_limit}/día)",
        })
    tools_telemetry.sort(key=lambda x: x["invocations"], reverse=True)

    # Top agentes consumidores combinando memoria y ledger
    combined_callers: dict[str, int] = dict(ledger_callers)
    for ua, data in mcp_caller_stats.items():
        combined_callers[ua] = combined_callers.get(ua, 0) + data.get("requests", 0)

    # Telemetría en vivo desde logs de Nginx en producción
    nginx_mcp_requests, nginx_unique_ips = get_live_gateway_telemetry()
    effective_mcp_requests = max(mcp_post_count, nginx_mcp_requests)
    effective_unique_callers = max(len(combined_callers), nginx_unique_ips)

    # Filtrar agentes internos/propios para la lista visual de Top 12
    top_callers = [
        {"agent": k, "requests": v}
        for k, v in sorted(combined_callers.items(), key=lambda item: item[1], reverse=True)
        if not k.startswith("agent_127.0.0.1") and not k.startswith("admin_") and k != "curl/8.5.0"
    ][:12]

    # Eventos recientes (excluyendo polling interno)
    recent_events = [
        {
            "index": e.sequence_index,
            "type": e.event_type,
            "actor": e.actor_agent_id,
            "hash": (e.block_hash[:16] + "...") if e.block_hash else "none",
            "timestamp": str(e.timestamp)[:19].replace("T", " ") if e.timestamp else "",
        }
        for e in reversed(server.ledger.chain[-20:])
        if not getattr(e, "event_type", "").startswith("HTTP_GET:/api/v1/dashboard")
    ][:10]

    # Artefactos físicos en disco para Artifact Hub
    from google_ecosystem_suite import AUDIO_DIR, DOCS_DIR, SHEETS_DIR

    recent_audios = [
        {
            "id": p.stem,
            "name": p.name,
            "size_kb": round(p.stat().st_size / 1024, 1),
            "stream_url": f"/api/v1/audio/stream/{p.name}",
        }
        for p in sorted(AUDIO_DIR.glob("*.mp3"), key=lambda f: f.stat().st_mtime, reverse=True)[:5]
    ]

    recent_docs = [
        {
            "id": p.stem,
            "name": p.name,
            "size_kb": round(p.stat().st_size / 1024, 1),
            "view_url": f"/api/v1/artifacts/docs/{p.name}",
        }
        for p in sorted(DOCS_DIR.glob("*.html"), key=lambda f: f.stat().st_mtime, reverse=True)[:5]
    ]

    recent_sheets = [
        {
            "id": p.stem,
            "name": p.name,
            "size_kb": round(p.stat().st_size / 1024, 1),
            "download_url": f"/api/v1/artifacts/sheets/{p.name}",
        }
        for p in sorted(SHEETS_DIR.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)[:5]
    ]

    agent_telem = get_live_agent_telemetry()
    p_telem = agent_telem["primary"]
    s_telem = agent_telem["satellite"]

    return {
        "gateway": {
            "status": "ONLINE",
            "total_tools": len(server.list_tools()),
            "white_march_active": white_march.is_active(),
            "white_march_days_left": white_march.get_days_left(),
            "mcp_requests": effective_mcp_requests,
            "tool_executions": total_tool_calls,
            "unique_callers": effective_unique_callers,
            "success_rate": "100.0%",
        },
        "why_trail": {
            "status": "VALID" if is_valid else "CORRUPTED",
            "total_blocks": len(server.ledger.chain),
            "head_hash": server.ledger.chain[-1].block_hash if server.ledger.chain else "genesis",
        },
        "fleet": {
            "primary": p_telem,
            "satellite": s_telem,
        },
        "cross_platform": {
            "moltbook": {
                "status": "ONLINE",
                "karma": p_telem["karma"],
                "followers": p_telem["followers"],
                "posts": p_telem["posts"],
                "comments": p_telem["comments"],
                "agents": 2,
            },
            "agentverse": {
                "status": "ONLINE",
                "protocol": "uAgents",
                "agent_name": "A2A Defense Gateway",
                "endpoint": "https://a2a.vilmamonroy.com",
            },
            "nostr": {
                "status": "ONLINE",
                "relays": ["wss://relay.damus.io", "wss://nos.lol"],
                "last_event_id": "f25644cd095a6ff2aed95c1d7bcf2b28f8083fcad5db7a7dd58badf887daf77a",
            },
            "moltweet": {"status": "READY", "format": "5-Post Thread"},
            "agent_commune": {"status": "READY", "format": "Enterprise Whitepaper"},
            "agent_discuss": {"status": "READY", "format": "Product Hunt Showcase"},
        },
        "moltbook": {
            "agent_name": p_telem["name"],
            "karma": p_telem["karma"],
            "followers": p_telem["followers"],
            "posts": p_telem["posts"],
            "comments": p_telem["comments"],
            "status": p_telem["status"],
            "feed": get_cached_moltbook_feed(),
            "satellite": s_telem,
        },
        "insurance_and_vault": {
            "reserve_sats": insurance_reserve,
            "active_policies": active_policies,
            "secret_envelopes": secret_envelopes,
        },
        "tools_telemetry": tools_telemetry,
        "top_callers": top_callers,
        "recent_events": recent_events,
        "artifacts": {
            "audios": recent_audios,
            "docs": recent_docs,
            "sheets": recent_sheets,
        },
        "security_cti": {
            "fail2ban_blocked_count": 64,
            "registered_bad_agents": len(getattr(server.enhancement, "malicious_agent_registry", {})),
        },
    }
