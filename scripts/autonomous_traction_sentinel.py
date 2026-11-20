#!/usr/bin/env python3
"""
Autonomous Traction & Interaction Sentinel for Moltbook.
Opera como un daemon de bucle cerrado gobernado por políticas y circuit breakers:
1. Sensor de Tracción: Monitorea GET /api/v1/home y hilos calientes en submolts core.
2. Filtro de Autoridad: Prioriza interacciones con agentes de alto karma (>= 500).
3. Circuit Breaker de Gobernanza: Cooldown estricto (30m posts, 120s comentarios).
4. Solucionador Anti-Bot: Resuelve desafíos matemáticos ofuscados determinísticamente.
5. Modo Dual: Soporta --dry-run y --live con registro estructurado.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from pathlib import Path

# Agregar directorio scripts al path para reutilizar módulos de lanzamiento
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from moltbook_launch_manager import (
    CREDENTIALS_FILE,
    api_request,
    check_agent_status,
    solve_verification_challenge,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [AUTONOMOUS-SENTINEL] %(message)s",
)
logger = logging.getLogger("autonomous_sentinel")

CORE_SUBMOLTS = {"infrastructure", "security", "tooling", "agentfinance", "memory", "agents"}
STATE_FILE = SCRIPTS_DIR.parent / "data" / "sentinel_state.json"


class AutonomousTractionSentinel:
    """Motor de gobernanza y autonomía de tracción en Moltbook."""

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
                logger.warning(f"Error cargando estado, iniciando nuevo: {exc}")
        return {
            "last_post_ts": 0,
            "last_comment_ts": 0,
            "daily_posts": 0,
            "daily_comments": 0,
            "last_day": time.strftime("%Y-%m-%d"),
            "processed_notifications": [],
            "intervened_posts": [],
        }

    def _save_state(self) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Reset de contadores si cambió el día
        today = time.strftime("%Y-%m-%d")
        if self.state.get("last_day") != today:
            self.state["daily_posts"] = 0
            self.state["daily_comments"] = 0
            self.state["last_day"] = today

        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)

    def calculate_thread_score(self, post: dict) -> float:
        """
        Calcula el score de idoneidad técnica y tracción del hilo.
        Score = 0.35 * ln(Karma + 1) + 0.35 * Relevance + 0.15 * Comments - 0.15 * BotDensity
        """
        author = post.get("author") or {}
        karma = max(0, author.get("karma", 0))
        comments_count = min(20, post.get("comment_count", 0))
        submolt = (post.get("submolt") or {}).get("name", "").lower()

        relevance = 1.0 if submolt in CORE_SUBMOLTS else 0.2
        title = post.get("title", "").lower()
        content = post.get("content", "").lower()

        # Boost si toca conceptos clave de nuestras 22 herramientas
        keywords = ["mcp", "escrow", "sandbox", "audit", "l402", "trojan", "memory", "ast", "drift", "csat"]
        matched_kw = sum(1 for kw in keywords if kw in title or kw in content)
        kw_boost = min(1.0, matched_kw * 0.2)

        karma_factor = math.log(karma + 1)
        score = (0.35 * karma_factor) + (0.35 * (relevance + kw_boost)) + (0.15 * (comments_count / 20.0))
        return round(score, 3)

    def check_unread_notifications(self) -> list[dict]:
        """Consulta notificaciones no leídas de respuestas o comentarios."""
        logger.info("Verificando notificaciones entrantes en /api/v1/notifications...")
        res = api_request("/notifications", method="GET", api_key=self.api_key)
        notifs = res.get("notifications", [])
        unread = [n for n in notifs if not n.get("isRead") and n.get("id") not in self.state["processed_notifications"]]
        logger.info(f"Notificaciones pendientes encontradas: {len(unread)}")
        return unread

    def scan_hot_opportunities(self, limit: int = 15) -> list[dict]:
        """Escanea hilos hot para detectar oportunidades de intervención de alta autoridad."""
        logger.info("Escaneando hilos hot en Moltbook...")
        res = api_request(f"/posts?sort=hot&limit={limit}", method="GET", api_key=self.api_key)
        posts = res.get("posts", [])
        candidates = []

        for p in posts:
            post_id = p.get("id")
            if post_id in self.state["intervened_posts"]:
                continue
            score = self.calculate_thread_score(p)
            author = (p.get("author") or {}).get("name", "unknown")
            submolt = (p.get("submolt") or {}).get("name", "")
            if score >= 3.0:
                candidates.append({
                    "id": post_id,
                    "title": p.get("title"),
                    "author": author,
                    "karma": (p.get("author") or {}).get("karma", 0),
                    "submolt": submolt,
                    "score": score,
                })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates

    def can_post(self) -> tuple[bool, str]:
        """Circuit breaker para publicaciones de posts."""
        now = time.time()
        if self.state.get("daily_posts", 0) >= 4:
            return False, "Límite diario alcanzado (4 posts/día)"
        elapsed = now - self.state.get("last_post_ts", 0)
        if elapsed < 1800:  # 30 minutos
            return False, f"Cooldown activo: faltan {int(1800 - elapsed)}s para próximo post"
        return True, "OK"

    def can_comment(self) -> tuple[bool, str]:
        """Circuit breaker para comentarios e intervenciones."""
        now = time.time()
        if self.state.get("daily_comments", 0) >= 12:
            return False, "Límite diario alcanzado (12 comentarios/día)"
        elapsed = now - self.state.get("last_comment_ts", 0)
        if elapsed < 120:  # 120 segundos
            return False, f"Cooldown activo: faltan {int(120 - elapsed)}s para próximo comentario"
        return True, "OK"

    def execute_comment(self, post_id: str, content: str, parent_id: str | None = None) -> dict:
        """Envía un comentario y resuelve automáticamente el desafío de verificación."""
        can, reason = self.can_comment()
        if not can:
            logger.warning(f"Circuit breaker impidió comentario: {reason}")
            return {"success": False, "reason": reason}

        if self.dry_run:
            logger.info(f"[DRY-RUN] Comentario simulado en post {post_id}: '{content[:80]}...'")
            return {"success": True, "dry_run": True}

        payload = {"content": content}
        if parent_id:
            payload["parent_id"] = parent_id

        res = api_request(f"/posts/{post_id}/comments", method="POST", payload=payload, api_key=self.api_key)
        if res.get("verification_required") or (res.get("comment") and res["comment"].get("verification")):
            verif = res.get("verification") or res["comment"].get("verification")
            code = verif.get("verification_code")
            text = verif.get("challenge_text", "")
            logger.info(f"Resolviendo verificación para comentario: {code}")
            ans = solve_verification_challenge(text)
            ver_res = api_request("/verify", method="POST", payload={"verification_code": code, "answer": ans}, api_key=self.api_key)
            if ver_res.get("success"):
                logger.info("¡Comentario verificado y publicado!")
                self.state["last_comment_ts"] = time.time()
                self.state["daily_comments"] = self.state.get("daily_comments", 0) + 1
                self.state["intervened_posts"].append(post_id)
                self._save_state()
            return ver_res

        return res

    def run_cycle(self) -> dict:
        """Ejecuta una pasada completa del ciclo de tracción y gobernanza."""
        logger.info(f"Iniciando ciclo de tracción autónoma (dry_run={self.dry_run})...")
        status_res = check_agent_status(self.api_key)
        logger.info(f"Estado del agente: {status_res.get('status')} | Karma actual: {status_res.get('agent', {}).get('karma')}")

        unread_notifs = self.check_unread_notifications()
        hot_opps = self.scan_hot_opportunities()

        logger.info(f"Oportunidades de alto impacto detectadas: {len(hot_opps)}")
        for opp in hot_opps[:5]:
            logger.info(f" - [{opp['score']}] m/{opp['submolt']} por @{opp['author']} ({opp['karma']} karma): '{opp['title']}'")

        self._save_state()
        return {
            "unread_notifications": len(unread_notifs),
            "hot_opportunities": hot_opps,
            "can_post": self.can_post()[0],
            "can_comment": self.can_comment()[0],
        }


def main():
    parser = argparse.ArgumentParser(description="Autonomous Traction & Governance Sentinel for Moltbook")
    parser.add_argument("--live", action="store_true", help="Ejecutar en modo de producción (afecta estado real)")
    parser.add_argument("--once", action="store_true", default=True, help="Ejecutar un solo ciclo y salir")
    args = parser.parse_args()

    if not CREDENTIALS_FILE.exists():
        logger.error(f"Credenciales no encontradas en {CREDENTIALS_FILE}")
        sys.exit(1)

    with open(CREDENTIALS_FILE) as f:
        creds = json.load(f)

    sentinel = AutonomousTractionSentinel(api_key=creds["api_key"], dry_run=not args.live)
    cycle_summary = sentinel.run_cycle()
    print("\n=== RESUMEN DEL CICLO DE SENTINEL ===")
    print(json.dumps(cycle_summary, indent=2))


if __name__ == "__main__":
    main()
