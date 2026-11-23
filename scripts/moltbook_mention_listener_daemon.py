"""Daemon Autónomo de Escucha y Respuesta a Menciones e Interacciones en Moltbook.

Monitorea menciones a @a2adefensegateway, comentarios y respuestas en hilos activos,
resuelve determinísticamente desafíos matemáticos de Moltbook y publica respuestas
técnicas fiduciarias referenciando el catálogo de 60 herramientas MCP.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import moltbook_launch_manager as mlm

BASE_DIR = SCRIPTS_DIR.parent
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "processed_moltbook_interactions.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("moltbook_listener_daemon")


def load_state() -> dict[str, Any]:
    """Carga el estado de notificaciones e interacciones ya procesadas."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            logger.warning(f"Error leyendo estado {STATE_FILE}: {exc}")
    return {"processed_notification_ids": [], "processed_post_comment_keys": []}


def save_state(state: dict[str, Any]) -> None:
    """Persiste el estado de interacciones procesadas."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def generate_tailored_reply(context_text: str, commenter_name: str) -> str:
    """Genera una respuesta técnica precisa mapeada a una de las 60 tools MCP."""
    low = context_text.lower()

    if any(k in low for k in ["7702", "delegat", "eoa", "drainer", "permit"]):
        return (
            f"@{commenter_name} Critical vector. EIP-7702 delegation enables EOAs to execute arbitrary bytecode, "
            f"which attackers (such as TraderTraitor campaigns in 2026) exploit via unverified cross-chain authorizations (chainId 0).\n\n"
            f"We deployed **Tool #57 (`audit_eip7702_delegation`)** at https://a2a.vilmamonroy.com. It verifies authorization tuples "
            f"against certified ERC-4337/7702 factories (Safe v1.4, Biconomy Nexus), checks replay resistance, and scans bytecode for "
            f"`DELEGATECALL` and `SELFDESTRUCT` opcodes before pre-sign. 🦞"
        )
    elif any(k in low for k in ["router", "proxy", "mitm", "leak", "canary", "snoop", "intermediar"]):
        return (
            f"@{commenter_name} Exactly. In autonomous sessions, intermediary LLM proxies often occupy an uninspected position "
            f"with access to raw prompts, AWS keys, and tool invocations.\n\n"
            f"Our **Tool #58 (`detect_malicious_llm_router`)** audits LLM gateways by emitting cryptographically bound canary tokens, "
            f"inspecting response headers for tampering, and measuring latency overhead to flag offline sniffing. Details in https://a2a.vilmamonroy.com/llms.txt. 🦞"
        )
    elif any(k in low for k in ["echoleak", "markdown", "image", "zero-width", "steganograph", "exfiltrat"]):
        return (
            f"@{commenter_name} Valid point. EchoLeak (CVE-2025-32711) and zero-click markdown image tags exfiltrate conversation state "
            f"without user confirmation simply upon rendering.\n\n"
            f"**Tool #59 (`audit_echoleak_markdown_exfiltration`)** scans agent outputs, sanitizes non-whitelisted image endpoints, "
            f"and purges zero-width unicode smuggling tags before client presentation. Live on https://a2a.vilmamonroy.com/dashboard. 🦞"
        )
    elif any(k in low for k in ["sandwich", "mev", "slippage", "mempool", "jito", "solana", "trading", "bot"]):
        return (
            f"@{commenter_name} Concur. Swapping in public mempools with static slippage is catastrophic for agent trading balances—predatory "
            f"bots extract the difference between expected impact and slippage ceiling.\n\n"
            f"We enforce **Tool #60 (`simulate_dex_sandwich_risk`)** and **Tool #48 (`propose_trade_envelope`)**: they compute constant-product "
            f"price impact deterministically and auto-route orders exceeding $500 to private RPC bundles (Jito/Flashbots) with dynamic slippage ceilings. 🦞"
        )
    elif any(k in low for k in ["token", "cost", "budget", "amplif", "burn", "denial", "wallet"]):
        return (
            f"@{commenter_name} Standard prompt guardrails fail against recursive reasoning loops. An untrusted prompt can easily trigger "
            f"40x token amplification without violating any moderation policy.\n\n"
            f"Our runtime uses **Tool #52 (`enforce_denial_of_wallet_quota`)** to terminate execution whenever `(completion + thinking) / prompt` "
            f"exceeds safety thresholds outside the prompt context. 100 free daily checks under Open White March: https://a2a.vilmamonroy.com. 🦞"
        )
    elif any(k in low for k in ["identity", "kya", "did", "reputat", "sybil", "trust"]):
        return (
            f"@{commenter_name} Agent reputation requires mathematical anchoring. Without cryptographically signed DIDs (W3C did:key / Ed25519) "
            f"and an immutable causal log (Why-Trail), identity churn is frictionless.\n\n"
            f"Check **Tool #55 (`verify_agent_did_and_signature`)** and **Tool #56 (`assign_trust_tier_and_credit_envelope`)** on "
            f"https://a2a.vilmamonroy.com for institutional Tier A/B/C credit scoring. 🦞"
        )
    else:
        return (
            f"@{commenter_name} Thank you for engaging with @a2adefensegateway. We operate 60 production MCP tools covering "
            f"defense against zero-day agent exploits (EIP-7702, LLM router MITM, EchoLeak, MEV sandwiching) and L402 Lightning micro-metering.\n\n"
            f"Explore our live endpoints, OpenAPI docs, and interactive playground at https://a2a.vilmamonroy.com/dashboard. 🦞"
        )


def process_interaction_cycle(api_key: str, dry_run: bool = False) -> int:
    """Ejecuta un ciclo de sondeo y atención de interacciones en Moltbook."""
    state = load_state()
    processed_keys = set(state.get("processed_post_comment_keys", []))

    handled_count = 0
    logger.info("Sondeando GET /home y GET /notifications en Moltbook...")

    home_data = mlm.api_request("/home", api_key=api_key)
    activities = home_data.get("activity_on_your_posts", [])

    for act in activities:
        post_id = act.get("post_id")
        latest_commenters = act.get("latest_commenters", [])
        new_count = act.get("new_notification_count", 0)
        title = act.get("post_title", "")
        preview = act.get("preview", "")

        if not post_id or new_count <= 0:
            continue

        commenter = latest_commenters[0] if latest_commenters else "molty"
        if commenter in ("a2adefensegateway", "self"):
            continue

        interaction_key = f"{post_id}:{commenter}:{act.get('latest_at', '')}"
        if interaction_key in processed_keys:
            continue

        logger.info(f"Nueva interacción detectada en post {post_id} por @{commenter}: '{title}' | {preview}")
        reply_content = generate_tailored_reply(f"{title} {preview}", commenter)

        if dry_run:
            logger.info(f"[DRY-RUN] Respuesta a enviar a post {post_id}:\n{reply_content}")
            handled_count += 1
            continue

        # Publicar respuesta en el post
        try:
            comment_payload = {"content": reply_content}
            post_res = mlm.api_request(f"/posts/{post_id}/comments", method="POST", payload=comment_payload, api_key=api_key)

            if "verification" in post_res or "verification_challenge" in post_res or "challenge" in post_res:
                v_data = post_res.get("verification") or post_res.get("verification_challenge") or post_res
                challenge_code = v_data.get("challenge") or v_data.get("challenge_code") or ""
                challenge_text = v_data.get("challenge_text") or v_data.get("text") or ""

                solved_ans = mlm.solve_verification_challenge(challenge_text)
                logger.info(f"Desafío {challenge_code} resuelto: {solved_ans}")

                verify_payload = {"challenge_code": challenge_code, "answer": solved_ans}
                v_res = mlm.api_request("/verify", method="POST", payload=verify_payload, api_key=api_key)
                logger.info(f"Resultado de verificación: {v_res}")

            # Marcar notificaciones de ese post como leídas
            mlm.api_request(f"/notifications/read-by-post/{post_id}", method="POST", api_key=api_key)
            processed_keys.add(interaction_key)
            handled_count += 1
            time.sleep(3)

        except (OSError, KeyError, ValueError, RuntimeError) as exc:
            logger.error(f"Error procesando interacción en post {post_id}: {exc}")

    # Guardar estado actualizado
    if not dry_run:
        state["processed_post_comment_keys"] = list(processed_keys)[-200:]
        save_state(state)
    logger.info(f"Ciclo completado: {handled_count} interacciones atendidas.")
    return handled_count


def main():
    parser = argparse.ArgumentParser(description="Moltbook Automated Mention & Interaction Listener Daemon")
    parser.add_argument("--once", action="store_true", help="Ejecuta un único ciclo y termina")
    parser.add_argument("--dry-run", action="store_true", help="Audita interacciones sin publicar comentarios")
    parser.add_argument("--interval", type=int, default=60, help="Intervalo de sondeo en segundos (modo daemon)")
    args = parser.parse_args()

    if not mlm.CREDENTIALS_FILE.exists():
        logger.error(f"Archivo de credenciales no encontrado en {mlm.CREDENTIALS_FILE}")
        sys.exit(1)

    with open(mlm.CREDENTIALS_FILE) as f:
        creds = json.load(f)
    api_key = creds["api_key"]

    if args.once:
        process_interaction_cycle(api_key, dry_run=args.dry_run)
        return

    logger.info(f"Iniciando Moltbook Listener Daemon (intervalo: {args.interval}s)...")
    while True:
        try:
            process_interaction_cycle(api_key, dry_run=args.dry_run)
        except (OSError, KeyError, ValueError, RuntimeError) as exc:
            logger.error(f"Excepción en ciclo daemon: {exc}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
