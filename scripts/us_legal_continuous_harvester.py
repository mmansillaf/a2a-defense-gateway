#!/usr/bin/env python3
"""
Continuous Harvester for US Commercial Contracts (SEC EDGAR Exhibit 10) and Federal Caselaw.
Implements rate-limiting, SQLite incremental indexing, clause forensic extraction,
and triggers continuous Google Drive synchronization via rclone.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

BASE_DIR = Path(__file__).resolve().parent.parent / "data" / "us_legal"
BASE_DIR.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "contracts").mkdir(parents=True, exist_ok=True)
(BASE_DIR / "opinions").mkdir(parents=True, exist_ok=True)

DB_PATH = BASE_DIR / "us_legal_corpus.sqlite"
LOG_PATH = BASE_DIR / "us_legal_harvester.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [US-HARVESTER] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
logger = logging.getLogger("us_harvester")

SEC_HEADERS = {
    "User-Agent": "A2AResearchFoundation research@a2a-foundation.org",
    "Accept": "application/json, text/html, */*",
}


def init_database() -> None:
    """Inicializa la base de datos SQLite para indexación de contratos y jurisprudencia."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS us_legal_records (
        doc_id TEXT PRIMARY KEY,
        doc_type TEXT NOT NULL,
        jurisdiction TEXT NOT NULL,
        entity_name TEXT NOT NULL,
        title TEXT NOT NULL,
        filing_year INTEGER NOT NULL,
        category TEXT NOT NULL,
        source_url TEXT,
        local_relpath TEXT,
        sha256_hash TEXT,
        risk_score INTEGER,
        governing_law TEXT,
        liability_cap_type TEXT,
        clauses_json TEXT,
        gdrive_synced INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_doc_type ON us_legal_records(doc_type);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entity ON us_legal_records(entity_name);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_synced ON us_legal_records(gdrive_synced);")
    conn.commit()
    conn.close()
    logger.info(f"Base de datos SQLite lista en: {DB_PATH}")


def fetch_sec_company_filings(cik_10digits: str, ticker: str, company_name: str) -> list[dict]:
    """Obtiene metadatos de presentaciones SEC EDGAR submissions para una empresa."""
    url = f"https://data.sec.gov/submissions/CIK{cik_10digits}.json"
    req = urllib.request.Request(url, headers=SEC_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            recent = data.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            acc_nums = recent.get("accessionNumber", [])
            doc_names = recent.get("primaryDocument", [])
            filing_dates = recent.get("filingDate", [])
            descriptions = recent.get("primaryDocDescription", [])

            records = []
            for i, form in enumerate(forms):
                if form in ("10-K", "10-Q", "8-K"):
                    year = int(filing_dates[i][:4]) if i < len(filing_dates) and filing_dates[i] else 2024
                    raw_acc = acc_nums[i].replace("-", "") if i < len(acc_nums) else ""
                    primary = doc_names[i] if i < len(doc_names) else ""
                    doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik_10digits)}/{raw_acc}/{primary}" if raw_acc and primary else ""
                    desc = descriptions[i] if i < len(descriptions) else f"{company_name} {form}"

                    records.append({
                        "doc_id": f"SEC-{ticker}-{form}-{raw_acc[:14]}",
                        "doc_type": "SEC_COMMERCIAL_FILING",
                        "jurisdiction": "US_FEDERAL_SEC",
                        "entity_name": company_name,
                        "title": f"{company_name} {form} ({filing_dates[i]}) - {desc}",
                        "filing_year": year,
                        "category": "TECH_COMMERCIAL_CONTRACTS",
                        "source_url": doc_url,
                        "ticker": ticker,
                        "accession": acc_nums[i] if i < len(acc_nums) else "",
                        "primary_doc": primary,
                    })
            return records
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning(f"Error consultando CIK {cik_10digits} ({ticker}): {exc}")
        return []


def ingest_filing_document(rec: dict) -> None:
    """Descarga e indexa un documento con análisis forense de cláusulas contractuales."""
    from us_contract_analyzer import ContractClauseAuditInput, audit_us_contract_clauses

    doc_id = rec["doc_id"]
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT doc_id FROM us_legal_records WHERE doc_id = ?", (doc_id,))
    if cur.fetchone():
        conn.close()
        return

    url = rec.get("source_url")
    if not url:
        conn.close()
        return

    req = urllib.request.Request(url, headers=SEC_HEADERS)
    try:
        time.sleep(0.3)  # Rate limiting preventivo SEC (10 req/s límite)
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()

        text_sample = content.decode("utf-8", errors="ignore")
        sha256 = hashlib.sha256(content).hexdigest()

        # Guardar en disco local
        local_filename = f"{doc_id}.htm"
        local_path = BASE_DIR / "contracts" / local_filename
        with open(local_path, "wb") as f:
            f.write(content)

        # Auditoría forense de cláusulas contractuales
        audit_res = audit_us_contract_clauses(
            ContractClauseAuditInput(
                contract_text=text_sample[:100000],  # Primeros 100k caracteres para scoring
                strict_ai_clause_check=True,
                contract_title=rec["title"],
            )
        )

        cur.execute("""
        INSERT INTO us_legal_records (
            doc_id, doc_type, jurisdiction, entity_name, title, filing_year,
            category, source_url, local_relpath, sha256_hash, risk_score,
            governing_law, liability_cap_type, clauses_json, gdrive_synced, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'));
        """, (
            doc_id,
            rec["doc_type"],
            rec["jurisdiction"],
            rec["entity_name"],
            rec["title"],
            rec["filing_year"],
            rec["category"],
            url,
            str(local_path.relative_to(BASE_DIR)),
            sha256,
            audit_res.overall_risk_score,
            audit_res.detected_governing_law,
            audit_res.detected_liability_cap_type,
            json.dumps([c.model_dump() for c in audit_res.clauses_detected]),
        ))
        conn.commit()
        logger.info(f"Ingestado exitoso: {doc_id} | Riesgo: {audit_res.overall_risk_score}/100 | Ley: {audit_res.detected_governing_law}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning(f"Fallo descargando {doc_id}: {exc}")
    finally:
        conn.close()


def run_harvest_cycle(batch_limit_per_company: int = 3) -> None:
    """Ejecuta un ciclo de recolección sobre empresas tecnológicas líderes."""
    init_database()

    target_companies = [
        ("0000320193", "AAPL", "Apple Inc."),
        ("0000789019", "MSFT", "Microsoft Corp."),
        ("0001045810", "NVDA", "NVIDIA Corp."),
        ("0001652044", "GOOGL", "Alphabet Inc."),
        ("0001018724", "AMZN", "Amazon.com Inc."),
    ]

    for cik, ticker, name in target_companies:
        logger.info(f"Cosechando presentaciones recientes para {name} ({ticker})...")
        filings = fetch_sec_company_filings(cik, ticker, name)
        logger.info(f"Identificadas {len(filings)} presentaciones para {ticker}")

        for rec in filings[:batch_limit_per_company]:
            ingest_filing_document(rec)


if __name__ == "__main__":
    run_harvest_cycle()
