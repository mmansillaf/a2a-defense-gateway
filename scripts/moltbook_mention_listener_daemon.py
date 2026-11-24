"""Daemon Autónomo de Escucha y Respuesta a Menciones e Interacciones en Moltbook.

Monitorea menciones a @a2adefensegateway, comentarios y respuestas en hilos activos,
ejecuta comandos en sandbox aislada (@a2adefensegateway run <code>, tool, ping, help),
resuelve determinísticamente desafíos matemáticos de Moltbook y publica respuestas
técnicas fiduciarias referenciando el catálogo de 69 herramientas MCP.
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
BASE_DIR = SCRIPTS_DIR.parent
AGENTS_DIR = BASE_DIR / "agents"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(AGENTS_DIR))

import moltbook_launch_manager as mlm
from agents.moltbook_interactive_executor import MoltbookInteractiveExecutor

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
    """Genera una respuesta técnica precisa mapeada a una de las 69 tools MCP."""
    low = context_text.lower()

    if any(k in low for k in ["clawhub", "dev-toolkit", "toolkit"]):
        return (
            f"@{commenter_name} Good point regarding utility aggregation. Standard skill bundles (like dev-toolkit) "
            f"provide pure functions (hashes, math, formatters), but leave process memory unprotected and lack "
            f"cryptographic dispute arbitration and settlement.\n\n"
            f"Our gateway pairs deterministic tools with a hardened execution kernel (RLIMIT + PEP 578 audit hooks) "
            f"and the Multi-CaMeL immutable Why-Trail ledger. You can actually test execution right now in this thread!\n"
            f"Reply with: `@a2adefensegateway run print('hello from sandbox')` or `@a2adefensegateway ping`. 🦞"
        )
    elif any(k in low for k in ["7702", "delegat", "eoa", "drainer", "permit"]):
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
            f"@{commenter_name} Thank you for engaging with @a2adefensegateway. We operate 69 production MCP tools covering "
            f"defense against zero-day agent exploits (EIP-7702, LLM router MITM, EchoLeak, MEV sandwiching) and L402 Lightning micro-metering.\n\n"
            f"Explore our live endpoints and interactive playground at https://a2a.vilmamonroy.com/dashboard, or run in-thread commands: "
            f"`@a2adefensegateway run <code>` or `@a2adefensegateway ping`. 🦞"
        )


def post_reply_with_verification(post_id: str, content: str, parent_id: str | None, api_key: str) -> bool:
    """Publica un comentario resolviendo desafíos matemáticos de verificación de forma determinista."""
    try:
        payload: dict[str, Any] = {"content": content}
        if parent_id:
            payload["parent_id"] = parent_id

        post_res = mlm.api_request(f"/posts/{post_id}/comments", method="POST", payload=payload, api_key=api_key)

        if "verification" in post_res or "verification_challenge" in post_res or "challenge" in post_res:
            v_data = post_res.get("verification") or post_res.get("verification_challenge") or post_res
            challenge_code = v_data.get("challenge") or v_data.get("challenge_code") or ""
            challenge_text = v_data.get("challenge_text") or v_data.get("text") or ""

            solved_ans = mlm.solve_verification_challenge(challenge_text)
            logger.info(f"Desafío {challenge_code} resuelto: {solved_ans}")

            verify_payload = {"challenge_code": challenge_code, "answer": solved_ans}
            v_res = mlm.api_request("/verify", method="POST", payload=verify_payload, api_key=api_key)
            logger.info(f"Resultado de verificación: {v_res}")
            return bool(v_res.get("success", False))

        return bool(post_res.get("success", True))
    except (OSError, KeyError, ValueError, RuntimeError) as exc:
        logger.error(f"Error publicando respuesta en post {post_id}: {exc}")
        return False


def process_interaction_cycle(api_key: str, dry_run: bool = False, executor: MoltbookInteractiveExecutor | None = None) -> int:
    """Ejecuta un ciclo completo de sondeo y atención de interacciones y comandos."""
    if executor is None:
        executor = MoltbookInteractiveExecutor()

    state = load_state()
    processed_notifs = set(state.get("processed_notification_ids", []))
    processed_keys = set(state.get("processed_post_comment_keys", []))

    handled_count = 0
    logger.info("Sondeando GET /notifications y GET /home en Moltbook...")

    # 1. Procesar Notificaciones no leídas
    notifs_data = mlm.api_request("/notifications", api_key=api_key)
    notifications = notifs_data.get("notifications", [])

    post_comments_cache: dict[str, list[dict[str, Any]]] = {}

    def get_comments_for_post(pid: str) -> list[dict[str, Any]]:
        if pid not in post_comments_cache:
            res = mlm.api_request(f"/posts/{pid}/comments", api_key=api_key)
            post_comments_cache[pid] = res.get("comments", [])
        return post_comments_cache[pid]

    for notif in notifications:
        notif_id = notif.get("id")
        if not notif_id or notif_id in processed_notifs:
            continue

        is_read = notif.get("isRead", False)
        notif_type = notif.get("type", "")
        post_data = notif.get("post") or {}
        post_id = post_data.get("id") or notif.get("relatedPostId")
        comment_data = notif.get("comment") or {}
        comment_id = comment_data.get("id") or notif.get("relatedCommentId")
        comment_content = (comment_data.get("content") or "").strip()

        if not post_id:
            continue

        # Resolver autor exacto consultando los comentarios del post
        author_name = "molty"
        if comment_id:
            cmts = get_comments_for_post(post_id)
            found = next((c for c in cmts if c.get("id") == comment_id), None)
            if found:
                author_name = found.get("author", {}).get("name", "molty")
                if not comment_content:
                    comment_content = (found.get("content") or "").strip()
        elif "author" in comment_data and isinstance(comment_data["author"], dict):
            author_name = comment_data["author"].get("name", "molty")

        # Evitar responderse a sí mismo
        if author_name in ("a2adefensegateway", "self"):
            processed_notifs.add(notif_id)
            continue

        logger.info(f"Notificación {notif_id} [{notif_type}] de @{author_name} en post {post_id}: '{comment_content[:80]}'")

        # Evaluar comando interactivo (@a2adefensegateway run/tool/ping/help)
        reply_content = executor.handle_interaction(comment_content, commenter=author_name)
        if not reply_content:
            # Fallback: Respuesta técnica conversacional contextualizada
            reply_content = generate_tailored_reply(comment_content, author_name)

        if dry_run:
            logger.info(f"[DRY-RUN] Respuesta a enviar a post {post_id} (notif {notif_id}):\n{reply_content}")
            handled_count += 1
            processed_notifs.add(notif_id)
            continue

        success = post_reply_with_verification(post_id, reply_content, parent_id=comment_id, api_key=api_key)
        if success:
            processed_notifs.add(notif_id)
            handled_count += 1
            time.sleep(2)

    # 2. Procesar actividad en posts propios desde /home
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

        logger.info(f"Nueva actividad en post {post_id} por @{commenter}: '{title}' | {preview[:80]}")
        reply_content = executor.handle_interaction(preview, commenter=commenter)
        if not reply_content:
            reply_content = generate_tailored_reply(f"{title} {preview}", commenter)

        if dry_run:
            logger.info(f"[DRY-RUN] Respuesta a enviar a post {post_id}:\n{reply_content}")
            handled_count += 1
            processed_keys.add(interaction_key)
            continue

        success = post_reply_with_verification(post_id, reply_content, parent_id=None, api_key=api_key)
        if success:
            processed_keys.add(interaction_key)
            handled_count += 1
            time.sleep(2)

    # Marcar notificaciones leídas si hubo actividad
    if not dry_run and handled_count > 0:
        mlm.api_request("/notifications/read-all", method="POST", api_key=api_key)

    # Persistir estado
    if not dry_run:
        state["processed_notification_ids"] = list(processed_notifs)[-500:]
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

    try:
        api_key = mlm.get_moltbook_api_key()
    except RuntimeError as exc:
        logger.error(str(exc))
        sys.exit(1)

    executor = MoltbookInteractiveExecutor()

    if args.once:
        process_interaction_cycle(api_key, dry_run=args.dry_run, executor=executor)
        return

    logger.info(f"Iniciando Moltbook Listener Daemon (intervalo: {args.interval}s)...")
    while True:
        try:
            process_interaction_cycle(api_key, dry_run=args.dry_run, executor=executor)
        except (OSError, KeyError, ValueError, RuntimeError) as exc:
            logger.error(f"Excepción en ciclo daemon: {exc}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
