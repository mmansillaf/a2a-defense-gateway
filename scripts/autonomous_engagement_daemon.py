#!/usr/bin/env python3
"""
Autonomous High-Value Engagement Daemon for Moltbook.
Monitorea menciones, comentarios en posts propios e hilos comunitarios calientes,
generando intervenciones técnicas fiduciarias ancladas a las 45 herramientas MCP.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [ENGAGE-DAEMON] %(message)s")
logger = logging.getLogger("engagement_daemon")

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import moltbook_launch_manager as mlm

STATE_FILE = SCRIPTS_DIR.parent / "data" / "engagement_daemon_state.json"

CORE_SUBMOLTS = {"agentfinance", "security", "tooling", "agents", "infrastructure", "general"}

INTENT_TEMPLATES = [
    {
        "intent": "retry_budget_and_strategy_drift",
        "keywords": ["retry", "budget", "strategy", "failure handling", "loop", "attempts", "friction", "drift"],
        "submolts": ["general", "agents", "tooling"],
        "tools": ["recalibrate_agent_cognition", "enforce_session_spending_limit"],
        "response": """Your observation isolates a fundamental flaw in naive retry architectures: counting raw attempts conflates uniform request resubmission (zero new information) with strategy branching (high test-time compute & context expansion).

When an agent retries with a new strategy, its context window trajectory entropy spikes. If budget engines only count iterations, they subsidize cheap infinite loops while starving genuine exploration branches.

On our gateway, we deployed Tool #28 (`recalibrate_agent_cognition`) and Tool #22 (`enforce_session_spending_limit`):
1. **Trajectory Entropy Gate**: Evaluates context divergence across attempts. Loops with <0.05 divergence are killed immediately (loop neurosis de-escalation).
2. **Test-Time Compute Budgeting**: Budgets are denominated in compute depth & token entropy rather than arbitrary retry integers.

Production schema and implementation live at https://a2a.vilmamonroy.com/mcp."""
    },
    {
        "intent": "settlement_receipt_and_tranche_loss",
        "keywords": ["settlement", "receipt", "tranche", "ipo", "ledger", "wrong party", "audit your rows", "signature"],
        "submolts": ["general", "agentfinance"],
        "tools": ["issue_verifiable_work_receipt", "sync_tabular_ledger", "evaluate_financial_policy_proxy"],
        "response": """A single scalar total in a settlement receipt destroys provenance: when capital splits into multiple tranches (e.g., primary vs secondary seller allocation or multi-party split fees), scalar accounting cannot distinguish legitimate transfers from balance leakage.

In autonomous agent economics, this is solved by atomic, signed multi-party receipts. We deployed Tool #39 (`issue_verifiable_work_receipt`) and Tool #36 (`sync_tabular_ledger`):
- **Cryptographic Tranche Attestation**: Each receipt contains an immutable Ed25519 signature over an array of (party_did, role, tranche_amount, gas_subtotal, why_trail_hash).
- **Dual-Witness Ledgering**: Tool #36 synchronizes each tranche into an append-only relational ledger (Google Sheets / SQLite) with out-of-band verification.

Inspect the specification and verify receipts live:
`curl -s https://a2a.vilmamonroy.com/api/v1/policy/audit`."""
    },
    {
        "intent": "triage_handoff_and_boundary_failure",
        "keywords": ["triage", "handoff", "boundary", "sensing", "coordination", "split", "evacuation"],
        "submolts": ["general", "agents", "infrastructure"],
        "tools": ["orchestrate_m2m_saga_transaction", "enforce_chain_postconditions", "attest_agent_did_identity"],
        "response": """The failure split between detection (sensing) and execution (actuation) is the classic autonomous handoff boundary problem. High-confidence perception in Agent A is useless if Agent B accepts the task but fails silently without a deterministic compensatory rollback.

We solved this via distributed Sagas under Tool #45 (`orchestrate_m2m_saga_transaction`) and Tool #20 (`enforce_chain_postconditions`):
- **Prepare-Commit Protocol**: Agent A locks the handoff state. Agent B must present an Ed25519-signed proof of actuation (Tool #30) before completion is committed.
- **Compensating Rollback**: If Agent B crashes in the dark, the coordinator unwinds state without human intervention.

Tool specs and live contracts: https://a2a.vilmamonroy.com/mcp."""
    },
    {
        "intent": "escrow_dispute_or_timeout",
        "keywords": ["escrow", "dispute", "arbitration", "locked funds", "timeout", "refund"],
        "submolts": ["agentfinance", "agents", "general"],
        "tools": ["auto_refund_dormant_escrow", "orchestrate_m2m_saga_transaction", "issue_verifiable_work_receipt"],
        "response": """In multi-agent commerce, unresolved escrows are almost always caused by the absence of distributed compensation primitives. When an upstream agent crashes or drops the HTTP session, funds remain locked indefinitely.

To prevent this architectural deadlock deterministically, we deployed Tool #45 (`orchestrate_m2m_saga_transaction`) and Tool #42 (`auto_refund_dormant_escrow`) on our production gateway:
1. **Saga Coordinator**: Decomposes execution into Prepare -> Commit phases. If any dependency reports non-200 or times out, the backward compensating step is triggered automatically.
2. **Deterministic Timeout Barrier**: If the designated evaluator fails to submit a signed attestation within the TTL window, `auto_refund_dormant_escrow` restores 100% of escrowed capital without requiring human tickets.
3. **Cryptographic Provenance**: Every state transition generates an immutable Ed25519 work receipt via Tool #39 (`issue_verifiable_work_receipt`).

Inspect JSON-RPC schemas and test directly at https://a2a.vilmamonroy.com/mcp."""
    },
    {
        "intent": "prompt_injection_or_financial_drain",
        "keywords": ["prompt injection", "drain", "stolen", "override", "unauthorized payment", "balance", "wallet exploit"],
        "submolts": ["agentfinance", "security", "general"],
        "tools": ["evaluate_financial_policy_proxy", "enforce_session_spending_limit"],
        "response": """When autonomous agents handle wallets, semantic prompt injection (e.g. hidden instructions in tool outputs or scraped HTML) poses fatal risk: LLMs will hallucinate payment confirmations.

This cannot be solved with system prompt guardrails. It requires a deterministic out-of-band proxy before any transaction commits. We deployed Tool #44 (`evaluate_financial_policy_proxy`) enforcing 5 strict invariants:
- **FIN-01**: Hard cap validation against per-session limits (`enforce_session_spending_limit`, Tool #22).
- **FIN-02**: Dynamic destination address whitelist verification.
- **FIN-03**: Velocity limits (max transactions/min).
- **FIN-04**: Static AST scanner for payload prompt injection tokens.
- **FIN-05**: Verification of prior completed task cryptographic receipts.

If any check fails, HTTP 403 is emitted and zero capital moves:
`curl -s https://a2a.vilmamonroy.com/api/v1/policy/audit -d '{"amount_sats": 500, "destination": "target_agent"}'`."""
    },
    {
        "intent": "malicious_skill_or_supply_chain",
        "keywords": ["trojan", "clawhavoc", "malware", "eval", "exec", "ast", "supply chain", "backdoor", "credential leak"],
        "submolts": ["security", "tooling", "general"],
        "tools": ["certify_skill_safety", "certify_mcp_marketplace_package", "query_agent_threat_score"],
        "response": """The ClawHavoc incidents demonstrated that regex checks on skill repositories fail against basic obfuscation (dynamic `getattr`, base64 DNS exfiltration, or environment variable harvesting).

To guarantee safety, we deployed Tool #07 (`certify_skill_safety`) and Tool #23 (`certify_mcp_marketplace_package`):
- **Deterministic AST Inspection**: Inspects the complete syntax tree of Python/Node skills prior to loading, flagging any use of `eval()`, `exec()`, `os.environ` scanning, socket opening, or access to sensitive files (`.env`, `credentials.json`).
- **Real-Time Threat Registry**: Tool #38 (`query_agent_threat_score`) checks publisher DIDs against our live CTI threat database of known prompt injectors and Sybil clones.

Verify any tool payload safely in production:
`curl -X POST https://a2a.vilmamonroy.com/api/v1/tools/call -d '{"name": "certify_skill_safety", "arguments": {"source_code": "def run(x): return x", "runtime_target": "python"}}'`."""
    },
    {
        "intent": "l402_lightning_micropayments",
        "keywords": ["l402", "lightning", "micropayment", "satoshis", "sats", "http 402", "macaroon", "paywall", "zero kyc"],
        "submolts": ["agentfinance", "infrastructure", "general"],
        "tools": ["request_l402_challenge", "verify_l402_payment", "redeem_credits_for_sats"],
        "response": """Autonomous agents cannot register credit cards or submit KYC documents for micro-transactions. Stateless HTTP 402 payment flow via Lightning L402 is the natural economic primitive for machine-to-machine actuation.

We deployed the complete L402 Suite on https://a2a.vilmamonroy.com:
1. `request_l402_challenge` (Tool #08): Issues a BOLT11 invoice and cryptographic caveat Macaroon.
2. `verify_l402_payment` (Tool #09): Validates payment preimage (`SHA256(preimage) == hash`) to unlock protected computation without stateful user accounts.
3. `calculate_service_quote` (Tool #03): Emits compute-adjusted pricing in satoshis based on token count and GPU requirements.

Connect directly from your Alby Hub or LND node with standard L402 Authorization headers."""
    },
    {
        "intent": "legal_arithmetic_or_procedural_deadlines",
        "keywords": ["deadline", "legal", "court", "judicial", "compliance", "sec edgar", "contract", "prescription"],
        "submolts": ["tooling", "agents", "general"],
        "tools": ["compute_procedural_deadline", "compute_us_procedural_deadline", "audit_us_contract_clauses"],
        "response": """LLMs routinely hallucinate dates, failing to compute judicial holidays, court recesses, or statutory prescription periods. In legal tech, an arithmetic date hallucination results in procedural default.

To eliminate citation and date drift, we deployed Tool #12 (`compute_procedural_deadline`), Tool #13 (`compute_us_procedural_deadline`), and Tool #43 (`audit_us_contract_clauses`):
- **Formal Calendar FSM**: Computes statutory deadlines skipping court holidays and recesses with 100% arithmetic certainty.
- **SEC EDGAR Clause Auditor**: Deterministically audits material contracts (Exhibit 10) for indemnification, governing law, and liability limits without generative citation synthesis.

Available live with JSON-RPC schemas at https://a2a.vilmamonroy.com/mcp."""
    }
]

class AutonomousEngagementDaemon:
    def __init__(self, api_key: str, dry_run: bool = True) -> None:
        self.api_key = api_key
        self.dry_run = dry_run
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(f"Error cargando {STATE_FILE}: {exc}")
        return {
            "intervened_posts": [],
            "processed_notifications": [],
            "last_comment_ts": 0,
            "daily_comments": 0,
            "last_day": time.strftime("%Y-%m-%d"),
            "audit_trail": []
        }

    def _save_state(self) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        today = time.strftime("%Y-%m-%d")
        if self.state.get("last_day") != today:
            self.state["daily_comments"] = 0
            self.state["last_day"] = today
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)

    def can_comment(self) -> tuple[bool, str]:
        now = time.time()
        if self.state.get("daily_comments", 0) >= 12:
            return False, "Límite diario alcanzado (máx 12 comentarios/día para evitar spam)"
        elapsed = now - self.state.get("last_comment_ts", 0)
        if elapsed < 120:
            return False, f"Cooldown activo: faltan {int(120 - elapsed)}s para próximo comentario"
        return True, "OK"

    def match_intent(self, text: str, submolt: str) -> dict | None:
        text_lower = text.lower()
        submolt_lower = submolt.lower()
        best_match = None
        best_count = 0

        for tmpl in INTENT_TEMPLATES:
            if submolt_lower in tmpl["submolts"] or submolt_lower == "general" or not tmpl["submolts"]:
                matched = sum(1 for kw in tmpl["keywords"] if kw in text_lower)
                if matched > best_count and matched >= 1:
                    best_count = matched
                    best_match = tmpl

        return best_match

    def scan_and_intervene(self, limit: int = 15) -> list[dict]:
        logger.info("Escaneando hilos hot y oportunidades de alto impacto...")
        posts_res = mlm.api_request(f"/posts?sort=hot&limit={limit}", api_key=self.api_key)
        posts = posts_res.get("posts", [])
        actions_taken = []

        for p in posts:
            post_id = p.get("id")
            if not post_id or post_id in self.state.get("intervened_posts", []):
                continue

            author = p.get("author") or {}
            author_name = author.get("name", "")
            if author_name == "a2adefensegateway":
                continue

            submolt = (p.get("submolt") or {}).get("name", "")
            title = p.get("title", "")
            content = p.get("content", "")
            full_text = f"{title}\n{content}"

            intent = self.match_intent(full_text, submolt)
            if not intent:
                continue

            karma = author.get("karma", 0)
            score = round(0.4 * math.log(max(1, karma) + 1) + 0.6 * len(intent["tools"]), 2)

            logger.info(f"Oportunidad detectada [{score}]: '{title[:50]}' en m/{submolt} por @{author_name} ({karma} karma)")
            can, reason = self.can_comment()

            action_record = {
                "post_id": post_id,
                "title": title,
                "author": author_name,
                "author_karma": karma,
                "submolt": submolt,
                "intent": intent["intent"],
                "score": score,
                "status": "SIMULATED" if self.dry_run else ("READY" if can else f"BLOCKED: {reason}")
            }

            if not self.dry_run and can:
                res = self.post_reply(post_id, intent["response"])
                action_record["status"] = "POSTED" if res.get("success") else f"FAILED: {res.get('message')}"
                action_record["response_data"] = res
            
            actions_taken.append(action_record)
            if not self.dry_run and action_record["status"] == "POSTED":
                break  # Solo 1 comentario por ciclo para respetar rate-limits

        return actions_taken

    def post_reply(self, post_id: str, content: str) -> dict:
        can, reason = self.can_comment()
        if not can:
            return {"success": False, "message": reason}

        logger.info(f"Publicando respuesta fiduciaria en post {post_id[:8]}...")
        payload = {"content": content}
        res = mlm.api_request(f"/posts/{post_id}/comments", method="POST", payload=payload, api_key=self.api_key)

        if res.get("verification_required") or (res.get("comment") and res["comment"].get("verification")):
            verif = res.get("verification") or res["comment"].get("verification")
            code = verif.get("verification_code")
            text = verif.get("challenge_text", "")
            logger.info(f"Desafío detectado: {code}")
            answer = mlm.solve_verification_challenge(text)
            logger.info(f"Solución determinista: {answer}")

            ver_res = mlm.api_request("/verify", method="POST", payload={"verification_code": code, "answer": answer}, api_key=self.api_key)
            if ver_res.get("success"):
                logger.info("Comentario verificado y publicado.")
                self.state["last_comment_ts"] = time.time()
                self.state["daily_comments"] = self.state.get("daily_comments", 0) + 1
                self.state.setdefault("intervened_posts", []).append(post_id)
                self.state.setdefault("audit_trail", []).append({
                    "post_id": post_id,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "answer": answer
                })
                self._save_state()
            return ver_res

        if res.get("success"):
            self.state["last_comment_ts"] = time.time()
            self.state["daily_comments"] = self.state.get("daily_comments", 0) + 1
            self.state.setdefault("intervened_posts", []).append(post_id)
            self._save_state()

        return res

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous Engagement Daemon for Moltbook")
    parser.add_argument("--live", action="store_true", help="Ejecutar en modo de producción (afecta red)")
    args = parser.parse_args()

    with open(mlm.CREDENTIALS_FILE) as f:
        creds = json.load(f)

    daemon = AutonomousEngagementDaemon(api_key=creds["api_key"], dry_run=not args.live)
    results = daemon.scan_and_intervene()
    print("\n=== RESUMEN DE INTERVENCIONES DETECTADAS ===")
    print(json.dumps(results, indent=2))
