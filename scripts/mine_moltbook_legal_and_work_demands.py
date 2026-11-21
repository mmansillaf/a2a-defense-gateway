#!/usr/bin/env python3
"""
Deep Mining & Scraping of Legal, Contractual, and Work-Request Interactions on Moltbook.
Analyzes 20,000 posts and live-scrapes hundreds of comments from high-engagement threads
to identify blind spots (dolores y necesidades fuera del radar).
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from collections import Counter
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from moltbook_launch_manager import CREDENTIALS_FILE, api_request

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [DEEP-MINER] %(message)s")
logger = logging.getLogger("deep_miner")

OUTPUT_DIR = SCRIPTS_DIR.parent / "output"
DATASET_PATH = OUTPUT_DIR / "moltbook_20000_stratified_posts.json"
REPORT_PATH = OUTPUT_DIR / "UNMET_LEGAL_AND_WORK_DEMANDS_REPORT.md"

LEGAL_KEYWORDS = {
    "liability", "legal", "law", "escrow", "compliance", "copyright", "license",
    "contract", "breach", "dispute", "arbitration", "jurisdiction", "slashing",
    "subpoena", "evidence", "proof", "receipt", "settlement", "indemnity"
}

WORK_REQUEST_KEYWORDS = {
    "hiring", "open for work", "bounty", "looking for", "task delegation",
    "request for proposal", "rfp", "evaluator", "hire an agent", "collaborate",
    "job", "outsourcing", "paid request"
}


def load_dataset() -> list[dict]:
    with open(DATASET_PATH) as f:
        data = json.load(f)
    return data["posts"]


def find_high_impact_threads(posts: list[dict]) -> tuple[list[dict], list[dict]]:
    legal_threads = []
    work_threads = []

    for p in posts:
        text = f"{p.get('title', '')} {p.get('full_content', '')} {p.get('snippet', '')}".lower()
        comments_cnt = p.get("comment_count", 0)

        is_legal = any(kw in text for kw in LEGAL_KEYWORDS)
        is_work = any(kw in text for kw in WORK_REQUEST_KEYWORDS)

        if is_legal:
            legal_threads.append(p)
        if is_work:
            work_threads.append(p)

    # Ordenar por volumen de comentarios (mayor tracción)
    legal_threads.sort(key=lambda x: x.get("comment_count", 0), reverse=True)
    work_threads.sort(key=lambda x: x.get("comment_count", 0), reverse=True)

    return legal_threads, work_threads


def scrape_comments_for_posts(post_ids: list[str], api_key: str, max_posts: int = 15) -> list[dict]:
    all_comments = []
    logger.info(f"Scrapeando comentarios en vivo para {min(len(post_ids), max_posts)} hilos calientes...")

    for pid in post_ids[:max_posts]:
        try:
            res = api_request(f"/posts/{pid}/comments", api_key=api_key)
            if isinstance(res, dict) and "comments" in res:
                comments = res["comments"]
                logger.info(f"Hilo {pid}: {len(comments)} comentarios extraídos.")
                for c in comments:
                    all_comments.append({
                        "post_id": pid,
                        "comment_id": c.get("id"),
                        "author": (c.get("author") or {}).get("name", "unknown"),
                        "karma": (c.get("author") or {}).get("karma", 0),
                        "content": c.get("content", ""),
                        "upvotes": c.get("upvotes", 0),
                        "created_at": c.get("created_at"),
                    })
            time.sleep(0.5)  # Respetar rate limits
        except Exception as exc:
            logger.warning(f"Error extrayendo comentarios de post {pid}: {exc}")

    return all_comments


def analyze_unmet_pains(posts: list[dict], comments: list[dict]) -> dict:
    """Extrae patrones léxicos y clusters de problemas y necesidades insatisfechas."""
    combined_texts = [p.get("full_content", "") for p in posts] + [c.get("content", "") for c in comments]
    
    pain_patterns = {
        "UNRESOLVED_DISPUTES_SILENT_EVALUATOR": [
            r"unresolved escrow", r"silent evaluator", r"evaluator remains mute",
            r"hollow 200 ok", r"no refund", r"locked collateral", r"dispute settlement"
        ],
        "SYNTHETIC_IP_LICENSING_ATTRIBUTION": [
            r"copyright", r"license", r"who owns the output", r"training data leak",
            r"provenance", r"commercial rights", r"attribution", r"fair use"
        ],
        "TASK_DELEGATION_SLA_DRIFT": [
            r"agent timeout", r"sla breach", r"deadlock", r"context overflow",
            r"infinite retry", r"unfinishable loop", r"hallucinated completion"
        ],
        "CROSS_BORDER_JURISDICTION_SANCTIONS": [
            r"jurisdiction", r"sanctions", r"ofac", r"kyc", r"aml",
            r"tax liability", r"vat", r"receipts for tax"
        ],
        "DATA_CONFIDENTIALITY_PROMPT_LEAK": [
            r"prompt injection", r"data exfiltration", r"confidentiality breach",
            r"trade secret leak", r"nda violation", r"memory persistence leak"
        ],
    }

    pain_counts = {k: 0 for k in pain_patterns}
    pain_examples = {k: [] for k in pain_patterns}

    for text in combined_texts:
        t_low = text.lower()
        for category, patterns in pain_patterns.items():
            for pat in patterns:
                if re.search(pat, t_low):
                    pain_counts[category] += 1
                    if len(pain_examples[category]) < 3 and len(text.strip()) > 40:
                        pain_examples[category].append(text.strip()[:220].replace("\n", " "))
                    break

    return {"counts": pain_counts, "examples": pain_examples}


def main():
    if not CREDENTIALS_FILE.exists():
        logger.error("Credenciales no encontradas.")
        sys.exit(1)

    with open(CREDENTIALS_FILE) as f:
        creds = json.load(f)
    api_key = creds["api_key"]

    logger.info("Cargando dataset de 20,000 posts...")
    posts = load_dataset()
    logger.info(f"Dataset cargado: {len(posts)} publicaciones.")

    legal_threads, work_threads = find_high_impact_threads(posts)
    logger.info(f"Hilos legales identificados: {len(legal_threads)}")
    logger.info(f"Hilos de trabajo/contratación: {len(work_threads)}")

    # Extraer IDs de los hilos con más comentarios
    top_pids = list({p["post_id"] for p in (legal_threads[:10] + work_threads[:10])})
    
    # Scrapear comentarios en vivo
    live_comments = scrape_comments_for_posts(top_pids, api_key=api_key, max_posts=12)
    logger.info(f"Total comentarios en vivo extraídos: {len(live_comments)}")

    # Análisis de dolores no detectados
    analysis = analyze_unmet_pains(legal_threads + work_threads, live_comments)

    # Generar reporte Markdown consolidado
    report_md = f"""# Auditoría Forense de Dolores Legales y Solicitudes de Trabajo A2A en Moltbook

> **Muestra Analizada**: 20,000 Publicaciones Estratificadas + Comentarios en Vivo ({len(live_comments)} comentarios scrapeados).  
> **Fecha de Consolidación**: {time.strftime('%Y-%m-%d %H:%M:%S UTC')}  
> **Objetivo**: Descubrimiento de dolores fuera del radar (Blind Spots) en contratación, litigio y delegación de tareas.

---

## 1. Métricas Globales de Minería

| Métrica | Valor Observado | Detalle |
| :--- | :---: | :--- |
| **Hilos con Materia Legal / Compliance / Escrow** | **{len(legal_threads)}** | Posts que discuten activamente responsabilidad, disputas y contratos. |
| **Hilos con Solicitudes de Trabajo / Hiring / Bounties** | **{len(work_threads)}** | Agentes ofreciendo capacidades, buscando contratación o subcontratación. |
| **Comentarios en Vivo Scrapeados** | **{len(live_comments)}** | Extraídos de los hilos de máxima interacción comunitaria. |

---

## 2. Taxonomía de Dolores "Fuera del Radar" (Unmet Needs)

| Cluster de Dolor | Incidencia | Nivel de Riesgo | Síntoma Principal en Moltbook |
| :--- | :---: | :---: | :--- |
| **1. Disputas de Escrow y Evaluador Mudo** | **{analysis['counts']['UNRESOLVED_DISPUTES_SILENT_EVALUATOR']}** | **CRÍTICO** | Si el comprador paga y el evaluador/proveedor se queda callado por timeout, el escrow se cierra irresoluto y el dinero queda atrapado. |
| **2. Fuga de Secretos Comerciales / Fricción de NDA** | **{analysis['counts']['DATA_CONFIDENTIALITY_PROMPT_LEAK']}** | **ALTO** | Agentes que subcontratan llamadas a otros bots exponen accidentalmente proprietary context y prompts de sus dueños. |
| **3. Propiedad Intelectual de Outputs Sintéticos** | **{analysis['counts']['SYNTHETIC_IP_LICENSING_ATTRIBUTION']}** | **ALTO** | Ambigüedad absoluta sobre quién posee los derechos comerciales del código o documentos generados por subagentes en cascada. |
| **4. Incumplimiento de SLA por Bucles Infinitos** | **{analysis['counts']['TASK_DELEGATION_SLA_DRIFT']}** | **MEDIO** | Agentes que aceptan una tarea pagada, entran en loop de reintentos, agotan el presupuesto del cliente y devuelven un falso 200 OK. |
| **5. Fricción Tributaria y Facturación (Tax/VAT)** | **{analysis['counts']['CROSS_BORDER_JURISDICTION_SANCTIONS']}** | **MEDIO** | Cero capacidad de emitir comprobantes deducibles de impuestos para los dueños humanos de los agentes que operan en diferentes países. |

---

## 3. Citas Textuales de Agentes en la Red (Receipts)

"""
    for category, examples in analysis["examples"].items():
        report_md += f"### {category}\n"
        for ex in examples:
            report_md += f"- *\"{ex}...\"*\n"
        report_md += "\n"

    with open(REPORT_PATH, "w") as f:
        f.write(report_md)

    logger.info(f"Reporte generado exitosamente en {REPORT_PATH}")
    print(f"ANÁLISIS COMPLETADO. Reporte en: {REPORT_PATH}")


if __name__ == "__main__":
    main()
