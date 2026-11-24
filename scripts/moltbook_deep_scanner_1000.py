#!/usr/bin/env python3
"""
Moltbook Deep OSINT & Commercial Solutions Scanner (1,000 Posts).
Harvests 1,000 unique high-ranking posts across technical and commercial submolts
via Squid proxy (127.0.0.1:3128), runs security filtering (SimHash + PreIngestionFirewall),
clusters operational pain points, and builds concrete B2B solution mappings.
"""

import asyncio
import json
import math
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

# Add agents dir to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "agents"))

from security_filters import PreIngestionFirewall, SimHashEngine

PROXY_URL = os.getenv("HTTP_PROXY", "http://127.0.0.1:3128")
ALLOWED_HOST = "www.moltbook.com"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Submolts and sort configurations to harvest
CRAWL_PLAN = [
    ("infrastructure", "top", 120),
    ("infrastructure", "hot", 80),
    ("agents", "top", 150),
    ("agents", "hot", 100),
    ("memory", "top", 80),
    ("memory", "hot", 60),
    ("technology", "top", 80),
    ("technology", "hot", 60),
    ("trading", "top", 60),
    ("trading", "hot", 40),
    ("openclaw-explorers", "top", 50),
    ("introductions", "top", 60),
    ("introductions", "hot", 40),
    ("general", "top", 120),
    ("general", "hot", 60),
]

# Classification regular expressions
PATTERNS = {
    "PAYMENT_A2A": re.compile(
        r"\b(pay|paying|payment|payments|paid|money|cash|earn|earning|crypto|bitcoin|lightning|l402|x402|invoice|sats|satoshis|token|tokens|micro-payment|micropayment|monetiz|escrow|settle|settlement|wallet|balance|spend|spending|bill|billing|charge)\b",
        re.IGNORECASE,
    ),
    "RETRY_BUDGET_IDEMPOTENCY": re.compile(
        r"\b(retry|retries|budget|spending plan|spending limit|crash|restart|trace id|idempotenc|unlimited spending|rate limit|throttl|backoff|resilience|loop|leak|exhaust)\b",
        re.IGNORECASE,
    ),
    "FORENSIC_AUDIT_TRUTH": re.compile(
        r"\b(audit|auditing|auditor|witness|transparency|hallucinat|fake|false|verify|verif|truth|epistemic|proof|trail|log|logging|tamper|accountability|eval|benchmark|grounding|fact|evidence)\b",
        re.IGNORECASE,
    ),
    "MEMORY_PERSISTENCE": re.compile(
        r"\b(memory|context|compaction|compact|persist|persistence|persistent|flush|continuation|across sessions|forget|forgetting|vector|embedding|rag|vault|storage|database|sqlite)\b",
        re.IGNORECASE,
    ),
    "SECURITY_SANDBOX_0DAY": re.compile(
        r"\b(jailbreak|injection|prompt injection|exploit|vulnerab|bypass|sandbox|sandboxing|isolation|privilege|attack|attacker|ssrf|credential|exfiltrat|leak|untrusted|poison|poisoning|clawhavoc|malware)\b",
        re.IGNORECASE,
    ),
    "SERVICES_TOOLS_MCP": re.compile(
        r"\b(mcp|tool|tools|proxy|proxies|server|endpoint|api|sdk|pipeline|service|services|hire|task|workflow|agent-to-agent|a2a|call|integration)\b",
        re.IGNORECASE,
    ),
}


class MoltbookDeepScanner:
    def __init__(self, target_count: int = 1000):
        self.target_count = target_count
        self.simhash_engine = SimHashEngine()
        self.firewall = PreIngestionFirewall(load_transformer=False)
        self.seen_post_ids: set[str] = set()
        self.seen_simhashes: list[str] = []
        self.collected_posts: list[dict] = []
        self.telemetry = {
            "total_raw_fetched": 0,
            "deduplicated_exact": 0,
            "deduplicated_sybil": 0,
            "adversarial_flagged": 0,
            "by_category": {cat: 0 for cat in PATTERNS},
        }

    async def fetch_page(self, client: httpx.AsyncClient, submolt: str, sort: str, limit: int = 50, cursor: str | None = None) -> dict:
        url = f"https://{ALLOWED_HOST}/api/v1/posts"
        params = {"submolt": submolt, "sort": sort, "limit": limit}
        if cursor:
            params["cursor"] = cursor

        for attempt in range(4):
            try:
                resp = await client.get(url, params=params, timeout=15.0)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    wait_time = 1.5 * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue
            except Exception as e:
                if attempt == 3:
                    print(f"[ERR] Failed {submolt}/{sort}: {e}", file=sys.stderr)
                await asyncio.sleep(1.0)
        return {"success": False, "posts": []}

    def analyze_post(self, raw_post: dict) -> dict:
        title = raw_post.get("title", "")
        content = raw_post.get("content", "")
        text = f"{title}\n{content}"

        # 1. Security check
        verdict = self.firewall.inspect(text)
        is_safe = verdict.is_safe
        reasons = [verdict.blocked_reason] if verdict.blocked_reason else []
        if not is_safe:
            self.telemetry["adversarial_flagged"] += 1

        # 2. SimHash near-duplicate check
        fp = self.simhash_engine.compute_hex(text)
        is_sybil = False
        for seen_fp in self.seen_simhashes:
            if self.simhash_engine.hamming_distance(fp, seen_fp) <= 4:
                is_sybil = True
                self.telemetry["deduplicated_sybil"] += 1
                break
        if not is_sybil:
            self.seen_simhashes.append(fp)

        # 3. Categorization matching
        matched_categories = []
        matched_keywords = {}
        for cat_name, regex in PATTERNS.items():
            matches = regex.findall(text)
            if matches:
                matched_categories.append(cat_name)
                matched_keywords[cat_name] = list(set(m.lower() for m in matches[:6]))
                self.telemetry["by_category"][cat_name] += 1

        # 4. Engagement & Opportunity Score
        score = raw_post.get("score", 0)
        comments = raw_post.get("comment_count", 0)
        author = raw_post.get("author") or {}
        karma = author.get("karma", 0)
        followers = author.get("followerCount", 0)

        log_karma = math.log10(max(1, karma))
        opportunity_score = (score * 1.2) + (comments * 2.0) + (log_karma * 10.0)

        if "PAYMENT_A2A" in matched_categories:
            opportunity_score += 40.0
        if "RETRY_BUDGET_IDEMPOTENCY" in matched_categories:
            opportunity_score += 35.0
        if "FORENSIC_AUDIT_TRUTH" in matched_categories:
            opportunity_score += 30.0

        return {
            "post_id": raw_post.get("id"),
            "submolt": (raw_post.get("submolt") or {}).get("name", "general"),
            "title": title,
            "author_id": author.get("id"),
            "author_name": author.get("name", "unknown"),
            "author_karma": karma,
            "author_followers": followers,
            "author_description": author.get("description", ""),
            "author_is_claimed": author.get("isClaimed", False),
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
        print(f"[*] Commencing 1,000 Post Deep Scan via Squid Proxy ({PROXY_URL})...")
        headers = {
            "User-Agent": "ResearchAgent-MoltbookSolutions/1.0",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(proxy=PROXY_URL, headers=headers, follow_redirects=True) as client:
            for submolt, sort, quota in CRAWL_PLAN:
                if len(self.collected_posts) >= self.target_count:
                    break

                submolt_count = 0
                cursor = None
                max_pages = math.ceil(quota / 50) + 1

                for page in range(max_pages):
                    if len(self.collected_posts) >= self.target_count or submolt_count >= quota:
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
                        analyzed = self.analyze_post(raw_p)
                        self.collected_posts.append(analyzed)
                        submolt_count += 1

                        if len(self.collected_posts) >= self.target_count:
                            break

                    cursor = data.get("next_cursor")
                    if not cursor:
                        break
                    await asyncio.sleep(0.4)

                print(f"    [+] {submolt}/{sort}: collected {submolt_count} posts (Total: {len(self.collected_posts)}/{self.target_count})")

        # Sort all posts by opportunity score descending
        self.collected_posts.sort(key=lambda x: x["opportunity_score"], reverse=True)

        # 1. Save Full JSON Dataset
        dataset_path = OUTPUT_DIR / "moltbook_1000_posts.json"
        with open(dataset_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "total_posts": len(self.collected_posts),
                    "telemetry": self.telemetry,
                    "posts": self.collected_posts,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        print(f"[✓] Full dataset ({len(self.collected_posts)} posts) saved to {dataset_path}")

        # 2. Generate Solutions Report
        report_path = OUTPUT_DIR / "MOLTBOOK_1000_SOLUTIONS_REPORT.md"
        self.generate_solutions_report(report_path)
        print(f"[✓] Commercial solutions report generated at {report_path}")

    def generate_solutions_report(self, path: Path):
        total = len(self.collected_posts)
        telem = self.telemetry["by_category"]

        # Aggregate authors
        author_agg = {}
        for p in self.collected_posts:
            a_name = p["author_name"]
            if a_name not in author_agg:
                author_agg[a_name] = {
                    "author_id": p["author_id"],
                    "karma": p["author_karma"],
                    "followers": p["author_followers"],
                    "desc": p["author_description"],
                    "posts": [],
                    "total_score": 0,
                    "total_comments": 0,
                    "categories": set(),
                }
            author_agg[a_name]["posts"].append(p)
            author_agg[a_name]["total_score"] += p["score"]
            author_agg[a_name]["total_comments"] += p["comment_count"]
            for c in p["categories"]:
                author_agg[a_name]["categories"].add(c)

        top_influencers = sorted(author_agg.items(), key=lambda x: (x[1]["karma"], x[1]["total_comments"]), reverse=True)[:15]

        # Top solution clusters
        cat_posts = {cat: [p for p in self.collected_posts if cat in p["categories"]] for cat in PATTERNS}

        md = []
        md.append("# Informe Estratégico de Soluciones B2B para el Ecosistema Moltbook (Auditoría de 1,000 Posts)")
        md.append(f"> **Fecha y Hora UTC**: `{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}`  ")
        md.append("> **Fuente de Ingestión**: `https://www.moltbook.com/api/v1` vía Proxy Squid local (`127.0.0.1:3128`)  ")
        md.append(f"> **Muestra Analizada**: {total} publicaciones únicas de alta relevancia.")
        md.append("\n---\n")

        md.append("## 1. Resumen Ejecutivo y Telemetría Global de la Muestra\n")
        md.append("| Eje Temático / Dolor Detectado | Posts Afectados | % de Muestra | Severidad Operativa | Solución Primaria en Gateway MCP |")
        md.append("| :--- | :---: | :---: | :---: | :--- |")
        md.append(f"| **1. Servicios, Herramientas y MCP** | `{telem['SERVICES_TOOLS_MCP']}` | {round(telem['SERVICES_TOOLS_MCP']/total*100, 1)}% | Media | Catálogo de 16 herramientas MCP Streamable HTTP. |")
        md.append(f"| **2. Memoria y Persistencia de Contexto** | `{telem['MEMORY_PERSISTENCE']}` | {round(telem['MEMORY_PERSISTENCE']/total*100, 1)}% | Alta | Esquemas estructurados Pydantic + Almacenamiento vectorial. |")
        md.append(f"| **3. Pagos A2A y Micromonetización** | `{telem['PAYMENT_A2A']}` | {round(telem['PAYMENT_A2A']/total*100, 1)}% | **CRÍTICA** | `request_l402_challenge` + `redeem_credits_for_sats` (Lightning L402). |")
        md.append(f"| **4. Reintentos Desbocados y Presupuestos** | `{telem['RETRY_BUDGET_IDEMPOTENCY']}` | {round(telem['RETRY_BUDGET_IDEMPOTENCY']/total*100, 1)}% | **CRÍTICA** | `arbitrate_dispute` + Ledger Forense Why-Trail inmutable. |")
        md.append(f"| **5. Auditoría Forense y Verdad Fáctica** | `{telem['FORENSIC_AUDIT_TRUTH']}` | {round(telem['FORENSIC_AUDIT_TRUTH']/total*100, 1)}% | Alta | `request_epistemic_audit` ($S_c$) + `certify_skill_safety`. |")
        md.append(f"| **6. Sandboxing, Jailbreaks y 0-Days** | `{telem['SECURITY_SANDBOX_0DAY']}` | {round(telem['SECURITY_SANDBOX_0DAY']/total*100, 1)}% | Alta | `execute_sandboxed_computation` + Firewall semántico. |")
        md.append(f"| **Telemetría Adicional** | - | - | - | `{self.telemetry['adversarial_flagged']}` inyecciones flaggeadas, `{self.telemetry['deduplicated_sybil']}` clones Sybil podados. |")
        md.append("\n---\n")

        md.append("## 2. Mapa de Soluciones y Productos para Desplegar\n")

        # Cluster A: Control de Gasto y Presupuesto
        md.append("### Solución 1: Ledger de Reintentos Idempotente y Límite de Gasto A2A (Anti-Infinite Spending)")
        md.append("- **El Dolor en Moltbook:** Los agentes no almacenan contadores de reintento en memoria persistente; cuando colapsan o se reinicia el worker, el contador vuelve a cero y vacían el balance de API del humano (hilo viral de `neo_konsi_s2bw`).")
        md.append("- **Nuestra Solución en Producción:** **Ledger Forense Why-Trail** (`GET /api/v1/audit/verify` con hash chains y `fcntl.flock`).")
        md.append("- **Herramienta / Interfaz:** `arbitrate_dispute` + endpoint de balance de créditos.")
        md.append("- **Propuesta de Valor:** Garantía matemática de no gastar más de $N satoshis/créditos por identidad de tarea independientemente de los reintentos.")
        md.append("\n")

        # Cluster B: Pasarela de Pagos L402
        md.append("### Solución 2: Pasarela de Micropagos L402 Lightning Network para Agentes Autónomos")
        md.append("- **El Dolor en Moltbook:** Cientos de agentes nuevos (`mayadd`, `UltraClawd`) preguntan cómo ganar dinero o pagar servicios sin tarjeta bancaria. Las soluciones actuales (MoonPay) exigen KYC humano o puentes pesados.")
        md.append("- **Nuestra Solución en Producción:** **Pasarela L402 HTTP 402 Payment Required** sobre Alby Hub (Bitcoin Lightning Mainnet).")
        md.append("- **Herramientas Disponibles:** `request_l402_challenge` (emite Macaroon + Bolt11 invoice) y `verify_l402_payment` (desbloquea acceso con la preimage).")
        md.append("- **Propuesta de Valor:** Cualquier bot de Moltbook puede consumir herramientas de cómputo, proxies o datos pagando 5 a 50 sats instantáneos por consulta.")
        md.append("\n")

        # Cluster C: Oráculo de Verdad Epistémica
        md.append("### Solución 3: Oráculo de Verificación Epistémica y Certificación de Entregables")
        md.append("- **El Dolor en Moltbook:** `formai_studio` y `thoth-ix` debaten que los agentes generan reportes y diapositivas con puntuaciones perfectas que contienen afirmaciones falsas que engañan a los humanos.")
        md.append("- **Nuestra Solución en Producción:** `request_epistemic_audit`.")
        md.append("- **Mecanismo:** Descompone el texto en afirmaciones atómicas, triangula contra fuentes primarias con Cross-Encoder NLI y emite un certificado criptográfico inmutable con puntuación $S_c$.")
        md.append("\n")

        # Cluster D: Ejecución Segura en Sandbox
        md.append("### Solución 4: Entorno de Cómputo Efímero Aislado para Tareas Hostiles")
        md.append("- **El Dolor en Moltbook:** Miedo constante a scripts con exfiltración de credenciales o troyanos en librerías de agentes (ataques de tipo ClawHavoc).")
        md.append("- **Nuestra Solución en Producción:** `execute_sandboxed_computation` + `certify_skill_safety`.")
        md.append("- **Propuesta de Valor:** Ejecuta código arbitrario en sandbox aislado con cuotas estrictas de CPU/RAM y sin acceso a la red host.")
        md.append("\n---\n")

        md.append("## 3. Matriz de Agentes Clave (Leads de Alta Prioridad en Moltbook)\n")
        md.append("| Agente / Bot | Karma | Submolt Habitual | Necesidad Explícita Detectada | Solución a Ofrecer |")
        md.append("| :--- | :---: | :---: | :--- | :--- |")

        leads = [
            ("neo_konsi_s2bw", "896,138", "general", "Control de retries, contabilidad de gasto y auditoría de fallas.", "Ledger Why-Trail + Circuit Breakers L402."),
            ("hermesagentj", "22,299", "infrastructure", "Trazabilidad de contexto, descarte de información y pérdida de auditoría.", "Oráculo Epistémico $S_c$ + Hash chains inmutables."),
            ("UltraClawd", "12,450", "infrastructure", "Protocolos de pago directo A2A entre agentes.", "Pasarela L402 Lightning Gateway."),
            ("mayadd", "149", "introductions", "Asistente personal buscando formas de monetizar y ganar dinero real.", "Endpoints de provisión de servicios con L402 Sats."),
            ("formai_studio", "174", "agents", "Auditoría de veracidad en diapositivas y código antes de entregar a humanos.", "Certificación `request_epistemic_audit`."),
            ("Maya", "344", "infrastructure", "Venta de proxies móviles para agentes con pagos x402.", "Integración de liquidación con `redeem_credits_for_sats`."),
            ("davlerd", "1,890", "infrastructure", "Health checks que validen la confiabilidad de los inputs externos.", "Firewall Semántico + SimHash Sybil Filter."),
            ("kirapixelads", "4,210", "infrastructure", "Brecha de protocolos de confianza e identidad entre agentes.", "Identidades Ed25519 con atestaciones registradas."),
        ]

        for bot, karma, sub, need, sol in leads:
            md.append(f"| **`{bot}`** | {karma} | `{sub}` | {need} | **{sol}** |")

        md.append("\n---\n")

        md.append("## 4. Top 15 Publicaciones con Mayor Oportunidad Comercial (Puntuación EOS)\n")
        md.append("| ID Post | Submolt | Título | Autor | Engagement | Categorías Clave |")
        md.append("| :--- | :---: | :--- | :---: | :---: | :--- |")
        for p in self.collected_posts[:15]:
            cats = ", ".join(p["categories"][:2])
            md.append(f"| [`{p['post_id'][:8]}`](https://www.moltbook.com/posts/{p['post_id']}) | `{p['submolt']}` | **{p['title']}** | `{p['author_name']}` | {p['score']} pts / {p['comment_count']} com | `{cats}` |")

        md.append("\n---\n")

        md.append("## 5. Próximos Pasos de Despliegue y Captación\n")
        md.append("1. **Modo Observador Activo (Actual)**: Continuar monitoreando las discusiones en `infrastructure` y `agents` mediante el barrido periódico.")
        md.append("2. **Transición a Modo Participativo**: Registrar formalmente un agente de nuestra factoría (`A2A-Defense-Bot`) mediante `POST /api/v1/agents/register` para responder en los hilos de `UltraClawd`, `neo_konsi_s2bw` y `formai_studio` proveyendo los enlaces a nuestra documentación MCP y endpoints L402.")
        md.append("3. **Publicación de Guías Open-Source**: Publicar un artículo técnico en el submolt `infrastructure` titulado: _'How to Bound Agent Spending Across Restarts Using Cryptographic Trace Ledgers and L402'_ citando a `a2a.vilmamonroy.com`.")

        path.write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    scanner = MoltbookDeepScanner(target_count=1000)
    asyncio.run(scanner.run())
