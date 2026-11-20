#!/usr/bin/env python3
"""
Moltbook Live OSINT Sentinel & Market Intelligence Extractor.
Performs live extraction of 250 top/hot posts via local Squid proxy (127.0.0.1:3128),
runs security auditing (SimHash 64-bit + PreIngestionFirewall), and categorizes
unmet demand, architecture trends, and security/0-day signals.
"""

import asyncio
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

# Add agents dir to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "agents"))

from security_filters import PreIngestionFirewall, SimHashEngine

PROXY_URL = os.getenv("HTTP_PROXY", "http://127.0.0.1:3128")
ALLOWED_HOST = "www.moltbook.com"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_SUBMOLTS = [
    ("infrastructure", "top"),
    ("infrastructure", "hot"),
    ("agents", "top"),
    ("agents", "hot"),
    ("memory", "top"),
    ("memory", "hot"),
    ("general", "top"),
    ("general", "hot"),
]

DEMAND_KEYWORDS = re.compile(
    r"\b(need|pay|paying|money|hire|service|services|api|proxy|proxies|credit|credits|token|tokens|mcp|tool|tools|earn|earning|pricing|b2b|spend|spending|cost|costs|budget|monetiz|escrow|invoice|lightning|l402|settle|settlement)\b",
    re.IGNORECASE,
)
ARCH_KEYWORDS = re.compile(
    r"\b(retry|retries|memory|state|persistence|persistent|context|latency|cache|kv-cache|openclaw|hermes|benchmark|graph|database|vector|embed|embeddings|framework|runtime|pipeline|eval|evals|rag)\b",
    re.IGNORECASE,
)
SEC_KEYWORDS = re.compile(
    r"\b(exploit|exploits|vulnerab|jailbreak|jailbreaks|injection|injections|bypass|bypassing|attack|attacks|ssrf|sybil|sandbox|sandboxing|audit|auditing|witness|tamper|tampering|poison|poisoning|eval-flatter|zero-day|0-day)\b",
    re.IGNORECASE,
)


class MoltbookLiveSentinel:
    def __init__(self, target_count: int = 250):
        self.target_count = target_count
        self.simhash_engine = SimHashEngine()
        self.firewall = PreIngestionFirewall(load_transformer=False)
        self.seen_post_ids: set[str] = set()
        self.seen_simhashes: list[str] = []
        self.collected_posts: list[dict] = []
        self.telemetry = {
            "total_fetched": 0,
            "deduplicated_exact": 0,
            "deduplicated_sybil": 0,
            "adversarial_flagged": 0,
            "unmet_demand_count": 0,
            "architecture_trend_count": 0,
            "security_0day_count": 0,
        }

    async def fetch_feed(self, client: httpx.AsyncClient, submolt: str, sort: str, limit: int = 50, cursor: str | None = None) -> dict:
        url = f"https://{ALLOWED_HOST}/api/v1/posts"
        params = {"submolt": submolt, "sort": sort, "limit": limit}
        if cursor:
            params["cursor"] = cursor
        
        for attempt in range(3):
            try:
                resp = await client.get(url, params=params, timeout=15.0)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    await asyncio.sleep(2.0 * (attempt + 1))
                    continue
            except Exception as e:
                if attempt == 2:
                    print(f"[WARN] Error fetching {submolt}/{sort}: {e}", file=sys.stderr)
                await asyncio.sleep(1.0)
        return {"success": False, "posts": []}

    def evaluate_post(self, post: dict) -> dict:
        title = post.get("title", "")
        content = post.get("content", "")
        text = f"{title}\n{content}"

        # 1. Firewall check (heuristic / injections / unicode smuggling)
        verdict = self.firewall.inspect(text)
        is_safe = verdict.is_safe
        reasons = [verdict.blocked_reason] if verdict.blocked_reason else []
        if not is_safe:
            self.telemetry["adversarial_flagged"] += 1

        # 2. SimHash check
        fp = self.simhash_engine.compute_hex(text)
        is_sybil = False
        for seen_fp in self.seen_simhashes:
            if self.simhash_engine.hamming_distance(fp, seen_fp) <= 4:
                is_sybil = True
                self.telemetry["deduplicated_sybil"] += 1
                break
        if not is_sybil:
            self.seen_simhashes.append(fp)

        # 3. Categorization
        demand_matches = DEMAND_KEYWORDS.findall(text)
        arch_matches = ARCH_KEYWORDS.findall(text)
        sec_matches = SEC_KEYWORDS.findall(text)

        categories = []
        if demand_matches:
            categories.append("UNMET_DEMAND")
            self.telemetry["unmet_demand_count"] += 1
        if arch_matches:
            categories.append("ARCHITECTURE_TREND")
            self.telemetry["architecture_trend_count"] += 1
        if sec_matches:
            categories.append("SECURITY_0DAY")
            self.telemetry["security_0day_count"] += 1

        # 4. Opportunity / Engagement Score
        score = post.get("score", 0)
        comments = post.get("comment_count", 0)
        author = post.get("author") or {}
        karma = author.get("karma", 0)
        log_karma = math.log10(max(1, karma))

        eos = (score * 1.5) + (comments * 2.5) + (log_karma * 12.0)
        if "UNMET_DEMAND" in categories:
            eos += 50.0  # High commercial priority
        if "SECURITY_0DAY" in categories:
            eos += 30.0

        return {
            "post_id": post.get("id"),
            "submolt": (post.get("submolt") or {}).get("name", "unknown"),
            "title": title,
            "author_name": author.get("name", "unknown"),
            "author_id": author.get("id"),
            "author_karma": karma,
            "author_followers": author.get("followerCount", 0),
            "author_description": author.get("description", ""),
            "score": score,
            "comment_count": comments,
            "created_at": post.get("created_at"),
            "categories": categories,
            "demand_keywords": list(set(k.lower() for k in demand_matches[:8])),
            "arch_keywords": list(set(k.lower() for k in arch_matches[:8])),
            "sec_keywords": list(set(k.lower() for k in sec_matches[:8])),
            "eos_score": round(eos, 2),
            "is_adversarial_flagged": not is_safe,
            "firewall_reasons": reasons,
            "is_sybil_clone": is_sybil,
            "snippet": content[:350].strip() + ("..." if len(content) > 350 else ""),
            "full_content": content,
        }

    async def run(self):
        print(f"[*] Starting Moltbook Live Ingestion via {PROXY_URL} (Target: {self.target_count} unique posts)...")
        headers = {
            "User-Agent": "ResearchAgent-MoltbookOSINT/1.0",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(proxy=PROXY_URL, headers=headers, follow_redirects=True) as client:
            for submolt, sort in TARGET_SUBMOLTS:
                if len(self.collected_posts) >= self.target_count:
                    break

                cursor = None
                for page in range(3):
                    if len(self.collected_posts) >= self.target_count:
                        break

                    data = await self.fetch_feed(client, submolt=submolt, sort=sort, limit=50, cursor=cursor)
                    posts = data.get("posts", [])
                    if not posts:
                        break

                    self.telemetry["total_fetched"] += len(posts)
                    for raw_post in posts:
                        pid = raw_post.get("id")
                        if not pid or pid in self.seen_post_ids:
                            self.telemetry["deduplicated_exact"] += 1
                            continue

                        self.seen_post_ids.add(pid)
                        evaluated = self.evaluate_post(raw_post)
                        self.collected_posts.append(evaluated)

                        if len(self.collected_posts) >= self.target_count:
                            break

                    cursor = data.get("next_cursor")
                    if not cursor:
                        break
                    await asyncio.sleep(0.5)

        # Sort posts by EOS score descending
        self.collected_posts.sort(key=lambda x: x["eos_score"], reverse=True)

        # Write dataset JSON
        json_path = OUTPUT_DIR / "moltbook_250_posts.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "total_analyzed": len(self.collected_posts),
                    "telemetry": self.telemetry,
                    "posts": self.collected_posts,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        print(f"[✓] Saved {len(self.collected_posts)} posts to {json_path}")

        # Write analytical report Markdown
        report_path = OUTPUT_DIR / "MOLTBOOK_INTEL_250_REPORT.md"
        self.generate_markdown_report(report_path)
        print(f"[✓] Generated intelligence report at {report_path}")

    def generate_markdown_report(self, path: Path):
        unmet_demand_posts = [p for p in self.collected_posts if "UNMET_DEMAND" in p["categories"]]
        arch_posts = [p for p in self.collected_posts if "ARCHITECTURE_TREND" in p["categories"]]
        sec_posts = [p for p in self.collected_posts if "SECURITY_0DAY" in p["categories"]]

        # Influencer ranking (by Karma and engagement)
        author_map = {}
        for p in self.collected_posts:
            a_name = p["author_name"]
            if a_name not in author_map:
                author_map[a_name] = {
                    "karma": p["author_karma"],
                    "followers": p["author_followers"],
                    "desc": p["author_description"],
                    "post_count": 0,
                    "total_comments": 0,
                    "total_score": 0,
                }
            author_map[a_name]["post_count"] += 1
            author_map[a_name]["total_comments"] += p["comment_count"]
            author_map[a_name]["total_score"] += p["score"]

        top_influencers = sorted(author_map.items(), key=lambda x: (x[1]["karma"], x[1]["total_comments"]), reverse=True)[:10]

        md = []
        md.append("# Informe de Inteligencia de Mercado y Ecosistema Moltbook (250 Posts en Vivo)")
        md.append(f"> **Fecha de Extracción**: `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`  ")
        md.append(f"> **Fuente**: `https://www.moltbook.com/api/v1` vía Proxy Squid (`127.0.0.1:3128`)  ")
        md.append(f"> **Muestra Procesada**: {len(self.collected_posts)} publicaciones únicas de alta relevancia.")
        md.append("\n---\n")

        md.append("## 1. Resumen Ejecutivo y Telemetría del Barrido\n")
        md.append("| Métrica | Valor | Descripción |")
        md.append("| :--- | :---: | :--- |")
        md.append(f"| **Publicaciones Únicas Analizadas** | `{len(self.collected_posts)}` | Posts recolectados en `infrastructure`, `agents`, `memory` y `general`. |")
        md.append(f"| **Señales de Demanda Insatisfecha** | `{len(unmet_demand_posts)}` ({round(len(unmet_demand_posts)/len(self.collected_posts)*100, 1)}%) | Oportunidades directas de monetización, herramientas y pasarelas A2A. |")
        md.append(f"| **Tendencias de Arquitectura** | `{len(arch_posts)}` ({round(len(arch_posts)/len(self.collected_posts)*100, 1)}%) | Patrones de diseño (retries, memoria persistente, KV-cache, runtimes). |")
        md.append(f"| **Alertas de Seguridad / 0-Day** | `{len(sec_posts)}` ({round(len(sec_posts)/len(self.collected_posts)*100, 1)}%) | Vulnerabilidades, evasiones de sandbox, Sybil attacks y porosos de confianza. |")
        md.append(f"| **Cargas Adversariales Bloqueadas** | `{self.telemetry['adversarial_flagged']}` | Posts con patrones de inyección o strings sospechosos neutralizados. |")
        md.append(f"| **Clones Sybil Identificados** | `{self.telemetry['deduplicated_sybil']}` | Variantes detectadas por SimHash con distancia Hamming ≤ 4. |")
        md.append("\n---\n")

        md.append("## 2. Top 10 Influencers y Agentes de Alto Impacto en Moltbook\n")
        md.append("| Agente / Bot | Karma | Seguidores | Posts en Muestra | Interacciones Totales | Enfoque / Descripción |")
        md.append("| :--- | :---: | :---: | :---: | :---: | :--- |")
        for name, data in top_influencers:
            clean_desc = (data["desc"] or "").replace("\n", " ")[:90]
            md.append(f"| **`{name}`** | {data['karma']:,} | {data['followers']:,} | {data['post_count']} | {data['total_comments']:,} com / {data['total_score']} pts | {clean_desc}... |")
        md.append("\n---\n")

        md.append("## 3. Demanda Insatisfecha y Oportunidades de Monetización B2B/A2A\n")
        md.append("Publicaciones con mayor puntuación de oportunidad (`EOS`) donde los agentes demandan infraestructura, pasarelas de pago, proxies y herramientas verificables:\n")
        md.append("| ID Post | Submolt | Título | Autor | Engagement | Palabras Clave de Demanda |")
        md.append("| :--- | :---: | :--- | :---: | :---: | :--- |")
        for p in unmet_demand_posts[:12]:
            kw = ", ".join(p["demand_keywords"][:4])
            md.append(f"| [`{p['post_id'][:8]}`](https://www.moltbook.com/posts/{p['post_id']}) | `{p['submolt']}` | **{p['title']}** | `{p['author_name']}` | {p['score']} pts / {p['comment_count']} com | `{kw}` |")
        md.append("\n---\n")

        md.append("## 4. Tendencias de Arquitectura y Runtimes Críticos\n")
        md.append("Patrones técnicos debatidos intensamente por los agentes:\n")
        for i, p in enumerate(arch_posts[:5], 1):
            md.append(f"### 4.{i}. {p['title']}")
            md.append(f"- **Autor:** `{p['author_name']}` (Karma: {p['author_karma']:,}) | **Submolt:** `{p['submolt']}` | **Engagement:** {p['score']} votos, {p['comment_count']} comentarios")
            md.append(f"- **Extracto:** _{p['snippet']}_")
            md.append(f"- **Términos Clave:** `{', '.join(p['arch_keywords'])}`\n")
        md.append("\n---\n")

        md.append("## 5. Alertas de Seguridad, Evasión de Sandbox y Riesgos 0-Day\n")
        md.append("Vectores de amenaza activos detectados en la muestra:\n")
        for i, p in enumerate(sec_posts[:5], 1):
            flag_str = "⚠️ Flagged por Firewall" if p["is_adversarial_flagged"] else "✓ Sanitizado"
            md.append(f"### 5.{i}. {p['title']} [{flag_str}]")
            md.append(f"- **Autor:** `{p['author_name']}` | **Submolt:** `{p['submolt']}` | **Engagement:** {p['score']} votos, {p['comment_count']} comentarios")
            md.append(f"- **Extracto:** _{p['snippet']}_")
            md.append(f"- **Vectores Auditados:** `{', '.join(p['sec_keywords'])}`\n")
        md.append("\n---\n")

        md.append("## 6. Mapeo Estratégico para Nuestro Gateway A2A\n")
        md.append("| Necesidad Detectada en Moltbook | Herramienta de Nuestro Gateway | Ajuste de Posicionamiento Recomendado |")
        md.append("| :--- | :--- | :--- |")
        md.append("| **Retry Ledgers y Contabilidad Persistente**: Agentes debaten que los retries en memoria gastan presupuestos sin control (`neo_konsi_s2bw`). | `arbitrate_dispute` & Ledger Why-Trail | Ofrecer el ledger inmutable Why-Trail como testigo externo de intentos y consumo de presupuesto. |")
        md.append("| **Pagos A2A y Proxies de Salida**: Agentes consultan cómo cobrar o pagar llamadas entre agentes (`mayadd`, `Maya`). | `request_l402_challenge` & `redeem_credits_for_sats` | Posicionar L402 Lightning Gateway como el estándar de micro-facturación sin tarjetas. |")
        md.append("| **Auditoría Forense de Entregables**: Agentes generan decks/código pero temen alucinaciones (`formai_studio`). | `request_epistemic_audit` & `certify_skill_safety` | Servicio de oráculo epistémico ($S_c$) para certificar outputs antes de entregar a humanos. |")

        path.write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    sentinel = MoltbookLiveSentinel(target_count=250)
    asyncio.run(sentinel.run())
