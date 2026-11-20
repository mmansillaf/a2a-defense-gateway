#!/usr/bin/env python3
"""
US Legal Corpus Pilot Harvest & Market Demand Validation Sampler.
Downloads high-demand sample documents from SEC EDGAR and SCOTUS,
indexes them locally in SQLite, audits clause/doctrinal value,
and syncs the pilot dataset to Google Drive via rclone.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import time
import urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [US-LEGAL-SAMPLER] %(message)s")
logger = logging.getLogger("us_legal_sampler")

BASE_DIR = Path("/home/usuario/Descargas/pycode/SkillA2A_Moltbook/moltbook_defense_system/data/us_legal_sample")
BASE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = BASE_DIR / "us_legal_sample.sqlite"

HEADERS = {
    "User-Agent": "A2ADefenseGateway ResearchBot mmansillaf@gmail.com",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
}

# Muestra curada de alto impacto comercial y agéntico (Costo $0)
TARGET_SAMPLES = [
    {
        "doc_id": "SEC-NVDA-8K-20261117",
        "category": "SEC_EDGAR_MATERIAL_FILING",
        "source": "SEC EDGAR",
        "entity": "NVIDIA Corporation",
        "year": 2026,
        "title": "NVIDIA Form 8-K Current Report (Material Governance & Executive Officers)",
        "url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000088/nvda-20261117.htm",
        "file_ext": "htm",
    },
    {
        "doc_id": "SEC-AAPL-10K-2026",
        "category": "SEC_EDGAR_ANNUAL_REPORT",
        "source": "SEC EDGAR",
        "entity": "Apple Inc.",
        "year": 2026,
        "title": "Apple Inc. Form 10-K Annual Report (Material Contracts, IP & Risk Factors)",
        "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019326000026/aapl-20260926.htm",
        "file_ext": "htm",
    },
    {
        "doc_id": "SCOTUS-NETCHOICE-2024",
        "category": "SCOTUS_OPINION",
        "source": "Supreme Court of the United States",
        "entity": "Moody v. NetChoice, LLC",
        "year": 2024,
        "title": "Moody v. NetChoice, LLC (First Amendment & Social Media Algorithm Moderation)",
        "url": "https://www.supremecourt.gov/opinions/23pdf/603us1r58_8mj9.pdf",
        "file_ext": "pdf",
    },
    {
        "doc_id": "SCOTUS-LOPER-BRIGHT-2024",
        "category": "SCOTUS_OPINION",
        "source": "Supreme Court of the United States",
        "entity": "Loper Bright Enterprises v. Raimondo",
        "year": 2024,
        "title": "Loper Bright Enterprises v. Raimondo (Overruling Chevron Administrative Deference)",
        "url": "https://www.supremecourt.gov/opinions/23pdf/22-451_7m58.pdf",
        "file_ext": "pdf",
    },
]


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS us_legal_sample (
        doc_id TEXT PRIMARY KEY,
        category TEXT,
        source TEXT,
        entity TEXT,
        year INTEGER,
        title TEXT,
        url TEXT,
        file_path TEXT,
        file_size_bytes INTEGER,
        sha256 TEXT,
        word_count INTEGER,
        clause_types_detected TEXT,
        market_demand_score REAL,
        harvest_ts REAL
    )
    """)
    conn.commit()
    conn.close()


def download_file(url: str, dest_path: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
            with open(dest_path, "wb") as f:
                f.write(content)
        return True
    except Exception as exc:
        logger.warning(f"Error descargando {url}: {exc}")
        return False


def audit_clauses_in_text(raw_bytes: bytes, ext: str) -> tuple[int, list[str]]:
    text = ""
    if ext == "htm":
        text = re.sub(r"<[^>]+>", " ", raw_bytes.decode("utf-8", errors="ignore"))
    else:
        # Fallback para PDF o texto crudo
        text = raw_bytes.decode("latin1", errors="ignore")

    words = len(text.split())
    clauses = []
    text_lower = text.lower()

    if "indemnif" in text_lower:
        clauses.append("INDEMNIFICATION")
    if "limitation of liability" in text_lower:
        clauses.append("LIMITATION_OF_LIABILITY")
    if "governing law" in text_lower or "choice of law" in text_lower:
        clauses.append("GOVERNING_LAW")
    if "first amendment" in text_lower:
        clauses.append("FIRST_AMENDMENT_CONSTITUTIONAL")
    if "chevron" in text_lower or "administrative procedure act" in text_lower:
        clauses.append("ADMINISTRATIVE_LAW_DEFERENCE")
    if "clawback" in text_lower or "recoupment" in text_lower:
        clauses.append("EXECUTIVE_CLAWBACK_GOVERNANCE")
    if "confidential" in text_lower:
        clauses.append("CONFIDENTIALITY")

    return words, clauses


def harvest_all() -> None:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    logger.info("Iniciando descarga de muestra curada de alto valor (Costo $0.00)...")

    for sample in TARGET_SAMPLES:
        doc_id = sample["doc_id"]
        ext = sample["file_ext"]
        dest_file = BASE_DIR / f"{doc_id}.{ext}"

        logger.info(f"Procesando {doc_id}: {sample['title']}...")
        success = download_file(sample["url"], dest_file)
        if not success or not dest_file.exists():
            logger.warning(f"Salteando {doc_id} por fallo de descarga.")
            continue

        raw_bytes = dest_file.read_bytes()
        file_size = len(raw_bytes)
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        words, clauses = audit_clauses_in_text(raw_bytes, ext)

        # Cálculo de valor de mercado (0.0 a 10.0)
        demand_score = 9.5 if "EXHIBIT" in sample["category"] or "SCOTUS" in sample["category"] else 8.5

        cur.execute("""
        INSERT OR REPLACE INTO us_legal_sample 
        (doc_id, category, source, entity, year, title, url, file_path, file_size_bytes, sha256, word_count, clause_types_detected, market_demand_score, harvest_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            doc_id,
            sample["category"],
            sample["source"],
            sample["entity"],
            sample["year"],
            sample["title"],
            sample["url"],
            str(dest_file),
            file_size,
            sha256,
            words,
            json.dumps(clauses),
            demand_score,
            time.time(),
        ))
        conn.commit()
        logger.info(f"-> {doc_id} indexado exitosamente: {file_size:,} bytes | {words:,} palabras | Cláusulas: {clauses}")

    conn.close()

    # Sincronización en la nube vía rclone a Google Drive
    logger.info("Iniciando sincronización de muestra a Google Drive (gdrive:09_us_legal/sample/)...")
    rclone_cmd = [
        "/home/usuario/.local/bin/rclone",
        "copy",
        str(BASE_DIR),
        "gdrive:09_us_legal/sample/",
        "--transfers", "4",
        "--fast-list",
        "--drive-chunk-size", "32M",
    ]
    res = subprocess.run(rclone_cmd, capture_output=True, text=True)
    if res.returncode == 0:
        logger.info("¡Sincronización a Google Drive COMPLETADA con éxito!")
    else:
        logger.error(f"Fallo en rclone: {res.stderr}")


if __name__ == "__main__":
    harvest_all()
