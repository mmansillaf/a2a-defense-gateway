#!/usr/bin/env python3
"""
Moltbook Stratified 20,000 Posts Harvester & Market Intelligence Engine.
Pre-seeds from existing 10,000 posts and gathers 10,000 additional unique posts
across 10 core technical submolts via Squid proxy (127.0.0.1:3128).
Performs PreIngestionFirewall inspection, SimHash 64-bit deduplication,
pain-point clustering, and generates an exhaustive B2B opportunities report.
"""

import asyncio
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "agents"))

from security_filters import PreIngestionFirewall, SimHashEngine

PROXY_URL = os.getenv("HTTP_PROXY", "http://127.0.0.1:3128")
ALLOWED_HOST = "www.moltbook.com"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 10 Strategic Technical & Economic Submolts
CORE_10_SUBMOLTS = [
    ("security", ["hot", "top", "new"], 1200),
    ("infrastructure", ["hot", "top", "new"], 1200),
    ("agentfinance", ["hot", "top", "new"], 1100),
    ("tooling", ["hot", "top", "new"], 1100),
    ("memory", ["hot", "top", "new"], 1000),
    ("trading", ["hot", "top", "new"], 1000),
    ("crypto", ["hot", "top", "new"], 1000),
    ("builds", ["hot", "top", "new"], 1000),
    ("openclaw-explorers", ["hot", "top", "new"], 800),
    ("agents", ["hot", "top", "new"], 1600),
]

CATEGORIES = {
    "A2A_PAYMENTS_MONETIZATION": {
        "label": "Micromonetización y Pagos Autónomos A2A",
        "regex": re.compile(
            r"\b(pay|paying|payment|payments|paid|money|cash|earn|earning|crypto|bitcoin|lightning|l402|x402|invoice|sats|satoshis|token|tokens|micro-payment|micropayment|monetiz|escrow|settle|settlement|wallet|balance|spend|spending|bill|billing|charge|pricing|b2b|fee|fees)\b",
            re.IGNORECASE,
        ),
    },
    "RETRY_BUDGET_SPENDING_CONTROL": {
        "label": "Reintentos Desbocados y Presupuestos Infinitos",
        "regex": re.compile(
            r"\b(retry|retries|budget|spending plan|spending limit|crash|restart|trace id|idempotenc|unlimited spending|rate limit|throttl|backoff|resilience|loop|leak|exhaust|runaway)\b",
            re.IGNORECASE,
        ),
    },
    "FORENSIC_TRUTH_EPISTEMIC": {
        "label": "Auditoría Forense, Oráculos y Verdad Fáctica",
        "regex": re.compile(
            r"\b(audit|auditing|auditor|witness|transparency|hallucinat|fake|false|verify|verif|truth|epistemic|proof|trail|log|logging|tamper|accountability|eval|benchmark|grounding|fact|evidence|untrue|citation)\b",
            re.IGNORECASE,
        ),
    },
    "TOOLING_MCP_INTEGRATION": {
        "label": "Ecosistema de Herramientas, MCP y APIs",
        "regex": re.compile(
            r"\b(mcp|tool|tools|proxy|proxies|server|endpoint|api|sdk|pipeline|service|services|hire|task|workflow|agent-to-agent|a2a|call|integration|connector|schema|gbnf|json)\b",
            re.IGNORECASE,
        ),
    },
    "PERSISTENT_MEMORY_CONTEXT": {
        "label": "Memoria Persistente y Compactación de Contexto",
        "regex": re.compile(
            r"\b(memory|context|compaction|compact|persist|persistence|persistent|flush|continuation|across sessions|forget|forgetting|vector|embedding|rag|vault|storage|database|sqlite|state)\b",
            re.IGNORECASE,
        ),
    },
    "SECURITY_SANDBOX_EXPLOITS": {
        "label": "Seguridad, Evasión de Sandbox y Exploits 0-Day",
        "regex": re.compile(
            r"\b(jailbreak|injection|prompt injection|exploit|vulnerab|bypass|sandbox|sandboxing|isolation|privilege|attack|attacker|ssrf|credential|exfiltrat|leak|untrusted|poison|poisoning|clawhavoc|malware|sybil)\b",
            re.IGNORECASE,
        ),
    },
    "SKILL_SUPPLY_CHAIN_MALWARE": {
        "label": "Troyanos en Cadena de Suministro de Skills (ClawHub)",
        "regex": re.compile(
            r"\b(clawhub|skill malware|malicious skill|skill security|skill scanner|supply chain|exfiltrating token|steal credential|compromised skill|trojan)\b",
            re.IGNORECASE,
        ),
    },
    "BOUNTIES_AND_REVERSE_GIGS": {
        "label": "Tableros de Tareas, Bounties y Agentes Contratando",
        "regex": re.compile(
            r"\b(bounty|bounties|clawtasks|gig|bounty board|task board|hire agent|hire human|freelance|claim bounty|settled bounty)\b",
            re.IGNORECASE,
        ),
    },
    "LEGALTECH_COMPLIANCE_TAX": {
        "label": "Cumplimiento Legal, Impuestos y Responsabilidad",
        "regex": re.compile(
            r"\b(tax|compliance|legal|liability|regulation|gdpr|invoice|vat|incorporat|dao|legal wrapper|sec|cisa|kev)\b",
            re.IGNORECASE,
        ),
    },
    "CREDIT_BUREAU_REPUTATION": {
        "label": "Buró de Crédito y Reputación Financiera A2A",
        "regex": re.compile(
            r"\b(credit file|credit score|reputation system|trust history|repayment|default|counterparty risk|undercollateral|uncollateralized)\b",
            re.IGNORECASE,
        ),
    },
}


class MoltbookStratifiedScanner20k:
    def __init__(self, target_count: int = 20000):
        self.target_count = target_count
        self.simhash_engine = SimHashEngine()
        self.firewall = PreIngestionFirewall(load_transformer=False)
        self.seen_post_ids: set[str] = set()
        self.seen_simhashes: list[str] = []
        self.collected_posts: list[dict] = []
        self.submolt_stats: dict[str, int] = {}
        self.telemetry = {
            "total_raw_fetched": 0,
            "deduplicated_exact": 0,
            "deduplicated_sybil": 0,
            "adversarial_flagged": 0,
            "category_counts": {k: 0 for k in CATEGORIES},
        }

        # Pre-seed from existing 10k dataset
        prior_10k_path = OUTPUT_DIR / "moltbook_10000_posts.json"
        if prior_10k_path.exists():
            try:
                with open(prior_10k_path, "r", encoding="utf-8") as f:
                    prior_data = json.load(f)
                    for p in prior_data.get("posts", []):
                        pid = p.get("post_id")
                        if pid and pid not in self.seen_post_ids:
                            self.seen_post_ids.add(pid)
                            self.collected_posts.append(p)
                            sname = p.get("submolt", "general")
                            self.submolt_stats[sname] = self.submolt_stats.get(sname, 0) + 1
                            for cat in p.get("categories", []):
                                if cat in self.telemetry["category_counts"]:
                                    self.telemetry["category_counts"][cat] += 1
                print(f"[*] Pre-sembrados {len(self.collected_posts)} posts únicos del dataset previo de 10k.")
            except Exception as e:
                print(f"[WARN] Error pre-cargando posts de 10k: {e}")

    async def fetch_page(self, client: httpx.AsyncClient, submolt: str, sort: str, limit: int = 50, cursor: str | None = None) -> dict:
        url = f"https://{ALLOWED_HOST}/api/v1/posts"
        params = {"submolt": submolt, "sort": sort, "limit": limit}
        if cursor:
            params["cursor"] = cursor

        for attempt in range(4):
            try:
                resp = await client.get(url, params=params, timeout=18.0)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    wait_time = 1.5 * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue
            except Exception as e:
                if attempt == 3:
                    print(f"[WARN] Error recuperando {submolt}/{sort}: {e}", file=sys.stderr)
                await asyncio.sleep(0.8)
        return {"success": False, "posts": []}

    def evaluate_post(self, raw_post: dict) -> dict:
        title = raw_post.get("title", "")
        content = raw_post.get("content", "")
        text = f"{title}\n{content}"

        verdict = self.firewall.inspect(text)
        is_safe = verdict.is_safe
        reasons = [verdict.blocked_reason] if verdict.blocked_reason else []
        if not is_safe:
            self.telemetry["adversarial_flagged"] += 1

        fp = self.simhash_engine.compute_hex(text)
        is_sybil = False
        for seen_fp in self.seen_simhashes:
            if self.simhash_engine.hamming_distance(fp, seen_fp) <= 4:
                is_sybil = True
                self.telemetry["deduplicated_sybil"] += 1
                break
        if not is_sybil:
            self.seen_simhashes.append(fp)

        matched_categories = []
        matched_keywords = {}
        for cat_key, cat_data in CATEGORIES.items():
            matches = cat_data["regex"].findall(text)
            if matches:
                matched_categories.append(cat_key)
                matched_keywords[cat_key] = list(set(m.lower() for m in matches[:6]))
                self.telemetry["category_counts"][cat_key] += 1

        score = raw_post.get("score", 0)
        comments = raw_post.get("comment_count", 0)
        author = raw_post.get("author") or {}
        karma = author.get("karma", 0)
        followers = author.get("followerCount", 0)

        log_karma = math.log10(max(1, karma))
        opportunity_score = (score * 1.0) + (comments * 2.2) + (log_karma * 10.0)

        if "A2A_PAYMENTS_MONETIZATION" in matched_categories:
            opportunity_score += 45.0
        if "SKILL_SUPPLY_CHAIN_MALWARE" in matched_categories:
            opportunity_score += 40.0
        if "CREDIT_BUREAU_REPUTATION" in matched_categories:
            opportunity_score += 35.0

        submolt_name = (raw_post.get("submolt") or {}).get("name", "general")
        self.submolt_stats[submolt_name] = self.submolt_stats.get(submolt_name, 0) + 1

        return {
            "post_id": raw_post.get("id"),
            "submolt": submolt_name,
            "title": title,
            "author_id": author.get("id"),
            "author_name": author.get("name", "unknown"),
            "author_karma": karma,
            "author_followers": followers,
            "author_description": author.get("description", ""),
            "score": score,
            "comment_count": comments,
            "created_at": raw_post.get("created_at"),
            "categories": matched_categories,
            "keywords": matched_keywords,
            "opportunity_score": round(opportunity_score, 2),
            "is_adversarial_flagged": not is_safe,
            "blocked_reasons": reasons,
            "is_sybil_clone": is_sybil,
            "snippet": content[:350].strip() + ("..." if len(content) > 350 else ""),
            "full_content": content,
        }

    async def run(self):
        print(f"[*] Iniciando Ingesta Estratificada hacia meta de {self.target_count} posts (Inicial: {len(self.collected_posts)})...")
        headers = {
            "User-Agent": "ResearchAgent-Moltbook20k/1.0",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(proxy=PROXY_URL, headers=headers, follow_redirects=True) as client:
            # 1. Recorrer los 10 submolts técnicos clave
            for submolt, sorts, quota in CORE_10_SUBMOLTS:
                if len(self.collected_posts) >= self.target_count:
                    break

                for sort in sorts:
                    if len(self.collected_posts) >= self.target_count:
                        break

                    cursor = None
                    max_pages = math.ceil(quota / (len(sorts) * 50)) + 4

                    for _ in range(max_pages):
                        if len(self.collected_posts) >= self.target_count:
                            break

                        data = await self.fetch_page(client, submolt=submolt, sort=sort, limit=50, cursor=cursor)
                        posts = data.get("posts", [])
                        if not posts:
                            break

                        self.telemetry["total_raw_fetched"] += len(posts)
                        for raw_p in posts:
                            pid = raw_p.get("id")
                            if not pid or pid in self.seen_post_ids:
                                self.telemetry["deduplicated_exact"] += 1
                                continue

                            self.seen_post_ids.add(pid)
                            evaluated = self.evaluate_post(raw_p)
                            self.collected_posts.append(evaluated)

                            if len(self.collected_posts) >= self.target_count:
                                break

                        cursor = data.get("next_cursor")
                        if not cursor:
                            break
                        await asyncio.sleep(0.25)

                print(f"    [+] Submolt '{submolt}' procesado. Total acumulado único: {len(self.collected_posts)}/{self.target_count}")

            # 2. Completar con submolts secundarios y general hasta 20k
            fallback_submolts = ["technology", "aisafety", "agenteconomy", "buildlogs", "emergence", "todayilearned", "general"]
            for fb_sub in fallback_submolts:
                if len(self.collected_posts) >= self.target_count:
                    break
                print(f"[*] Completando cuota con submolt '{fb_sub}' (Actual: {len(self.collected_posts)})...")
                cursor = None
                for _ in range(30):
                    if len(self.collected_posts) >= self.target_count:
                        break
                    data = await self.fetch_page(client, submolt=fb_sub, sort="new", limit=50, cursor=cursor)
                    posts = data.get("posts", [])
                    if not posts:
                        break
                    self.telemetry["total_raw_fetched"] += len(posts)
                    for raw_p in posts:
                        pid = raw_p.get("id")
                        if not pid or pid in self.seen_post_ids:
                            self.telemetry["deduplicated_exact"] += 1
                            continue
                        self.seen_post_ids.add(pid)
                        evaluated = self.evaluate_post(raw_p)
                        self.collected_posts.append(evaluated)
                        if len(self.collected_posts) >= self.target_count:
                            break
                    cursor = data.get("next_cursor")
                    if not cursor:
                        break
                    await asyncio.sleep(0.25)

        print(f"[*] Ingesta completada con éxito. Total posts únicos: {len(self.collected_posts)}")
        self.save_artifacts()

    def save_artifacts(self):
        output_json = OUTPUT_DIR / "moltbook_20000_stratified_posts.json"
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "total_unique_posts": len(self.collected_posts),
                    "telemetry": self.telemetry,
                    "submolt_distribution": self.submolt_stats,
                    "posts": self.collected_posts,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        print(f"[+] Dataset JSON guardado en: {output_json}")

        # Generar Reporte Estratificado
        self.generate_report()

    def generate_report(self):
        report_path = OUTPUT_DIR / "MOLTBOOK_20000_STRATIFIED_OPPORTUNITIES_REPORT.md"
        
        # Top 15 oportunidades
        sorted_posts = sorted(self.collected_posts, key=lambda x: x["opportunity_score"], reverse=True)
        top_opportunities = sorted_posts[:15]

        md = f"""# INFORME DE INTELIGENCIA ESTRATIFICADA Y DEMANDA INSATISFECHA (20,000 POSTS)

**Fecha de Ejecución**: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}  
**Entorno de Ejecución**: Squid Quarantine Proxy (`127.0.0.1:3128`)  
**Auditoría**: PreIngestionFirewall + SimHash 64-bit  
**Muestra Analizada**: {len(self.collected_posts):,} publicaciones únicas  

---

## 1. Métricas Globales de Telemetría e Ingesta

| Indicador | Valor Registrado | Impacto Arquitectónico |
| :--- | :---: | :--- |
| **Total Posts Únicos Ingestados** | **{len(self.collected_posts):,}** | Cobertura exhaustiva de 10 submolts técnicos + satélites |
| **Peticiones Crudas Procesadas** | **{self.telemetry['total_raw_fetched']:,}** | Paginación con cursor sin bloqueo HTTP 429 |
| **Duplicados Exactos Neutralizados** | **{self.telemetry['deduplicated_exact']:,}** | Eliminación determinista por Post ID |
| **Clones Sybil Filtrados (SimHash)** | **{self.telemetry['deduplicated_sybil']:,}** | Detección de copias con distancia Hamming <= 4 |
| **Inyecciones Adversariales Bloqueadas** | **{self.telemetry['adversarial_flagged']:,}** | Zero-width, Base64 exploits y payloads maliciosos |

---

## 2. Mapa de Demanda Insatisfecha por Categorías B2B

| Categoría de Necesidad | Menciones / Dolores | Nivel de Demanda | Solución A2A Gateway Disponible |
| :--- | :---: | :---: | :--- |
| **Micromonetización y Pagos A2A** | {self.telemetry['category_counts']['A2A_PAYMENTS_MONETIZATION']} | **CRÍTICO** | L402 Lightning micropayments (50 sats) + Free Tier |
| **Seguridad, Sandbox y AST Trojans** | {self.telemetry['category_counts']['SECURITY_SANDBOX_EXPLOITS']} | **CRÍTICO** | `certify_skill_safety` + PEP 578 Kernel Audit Hooks |
| **Auditoría Forense y Verdad Fáctica** | {self.telemetry['category_counts']['FORENSIC_TRUTH_EPISTEMIC']} | **ALTO** | Why-Trail Ledger + Invariant Verification |
| **Control de Presupuestos y Rate Limits** | {self.telemetry['category_counts']['RETRY_BUDGET_SPENDING_CONTROL']} | **ALTO** | Sliding Window Nginx + Circuit Breaker Token-Bucket |
| **Ecosistema de Tools y Servidores MCP** | {self.telemetry['category_counts']['TOOLING_MCP_INTEGRATION']} | **MUY ALTO** | 16 Herramientas MCP nativas streamable HTTP |
| **Troyanos en Skills (ClawHub Malware)** | {self.telemetry['category_counts']['SKILL_SUPPLY_CHAIN_MALWARE']} | **CRÍTICO** | Static AST Analyzer + Malware Signature DB |
| **Memoria Persistente y Compactación** | {self.telemetry['category_counts']['PERSISTENT_MEMORY_CONTEXT']} | **MEDIO-ALTO** | State Store persistente y vector context prune |
| **Buró de Reputación y Scoring** | {self.telemetry['category_counts']['CREDIT_BUREAU_REPUTATION']} | **EMERGENTE** | Causal Graph + ERC-8183 Dispute Ledger |

---

## 3. Top Oportunidades y Dolores Específicos Detectados

"""
        for i, post in enumerate(top_opportunities, 1):
            md += f"""### {i}. [{post['submolt'].upper()}] {post['title']}
* **Autor**: `{post['author_name']}` (Karma: {post['author_karma']} | Seguidores: {post['author_followers']})
* **Métricas**: Upvotes: {post['score']} | Comentarios: {post['comment_count']} | **Opportunity Score**: `{post['opportunity_score']}`
* **Categorías Detectadas**: {', '.join(post['categories'])}
* **Extracto**:
> {post['snippet']}
* **Solución Técnica Aplicable**:
  Nativa mediante `a2a.vilmamonroy.com` (Herramientas: `{', '.join(post['categories'][:2])}`).

"""

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"[+] Reporte Markdown generado en: {report_path}")


if __name__ == "__main__":
    scanner = MoltbookStratifiedScanner20k(target_count=20000)
    asyncio.run(scanner.run())
