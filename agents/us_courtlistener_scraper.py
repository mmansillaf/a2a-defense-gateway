"""
US Caselaw and Court Opinions Scraper & Retrieval Engine.
Integrates with CourtListener (Free Law Project) REST API v4,
with deterministic offline fallback for air-gapped environments and CI/CD pipelines.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("courtlistener_scraper")

COURTLISTENER_BASE_URL = "https://www.courtlistener.com/api/rest/v4/search/"

# Fixtures deterministas de respaldo para consultas recurrentes en modo offline / testing
OFFLINE_CASELAW_FIXTURES: list[dict[str, Any]] = [
    {
        "case_name": "Bell Atlantic Corp. v. Twombly",
        "citation": "550 U.S. 544",
        "court": "Supreme Court of the United States",
        "date_filed": "2007-05-21",
        "status": "Precedente Vinculante",
        "snippet": "Because the plaintiffs here have not nudged their claims across the line from conceivable to plausible, their complaint must be dismissed.",
        "docket_number": "05-1126",
        "download_url": "https://www.courtlistener.com/opinion/145730/bell-atlantic-corp-v-twombly/",
    },
    {
        "case_name": "Ashcroft v. Iqbal",
        "citation": "556 U.S. 662",
        "court": "Supreme Court of the United States",
        "date_filed": "2009-05-18",
        "status": "Precedente Vinculante",
        "snippet": "Threadbare recitals of the elements of a cause of action, supported by mere conclusory statements, do not suffice under Rule 8.",
        "docket_number": "07-1015",
        "download_url": "https://www.courtlistener.com/opinion/145869/ashcroft-v-iqbal/",
    },
    {
        "case_name": "Dobbs v. Jackson Women's Health Organization",
        "citation": "597 U.S. 215",
        "court": "Supreme Court of the United States",
        "date_filed": "2022-06-24",
        "status": "Precedente Vigente (Roe Overruled)",
        "snippet": "The Constitution makes no reference to abortion, and no such right is implicitly protected by any constitutional provision.",
        "docket_number": "19-1392",
        "download_url": "https://www.courtlistener.com/opinion/7352342/dobbs-v-jackson-womens-health-organization/",
    },
    {
        "case_name": "In re Caremark International Inc. Derivative Litigation",
        "citation": "698 A.2d 959",
        "court": "Delaware Court of Chancery",
        "date_filed": "1996-09-25",
        "status": "Doctrina Corporativa Delaware (Oversight Duty)",
        "snippet": "Directors have an affirmative duty to ensure that a corporate information and reporting system exists reasonably designed to provide timely, accurate information.",
        "docket_number": "Civ. A. 13670",
        "download_url": "https://www.courtlistener.com/opinion/1958611/in-re-caremark-intern-inc-der-lit/",
    },
]


class CaselawSearchInput(BaseModel):
    query: str = Field(..., description="Términos de búsqueda, nombres de partes o materia legal (ej. 'Twombly plausible pleading', 'Caremark oversight duty')")
    court: str | None = Field(default=None, description="Filtro opcional de tribunal (ej. 'scotus', 'ca9', 'ca2', 'delch')")
    max_results: int = Field(default=5, ge=1, le=20, description="Cantidad máxima de resultados a retornar")
    api_token: str | None = Field(default=None, description="Token de autenticación opcional para CourtListener API v4")


class CaselawOpinionRecord(BaseModel):
    case_name: str
    citation: str
    court: str
    date_filed: str
    status: str
    snippet: str
    docket_number: str
    download_url: str


class CaselawSearchOutput(BaseModel):
    doc_id: str
    query: str
    total_results: int
    source: str
    results: list[CaselawOpinionRecord]


def search_us_court_opinions(payload: CaselawSearchInput) -> CaselawSearchOutput:
    """
    Busca jurisprudencia y opiniones judiciales federales y estatales de EE. UU.
    Intenta conexión a CourtListener v4; si falla o no hay token/red, conmuta deterministamente al índice local.
    """
    q_clean = payload.query.strip()
    records: list[CaselawOpinionRecord] = []
    source = "OFFLINE_CANONICAL_INDEX"

    if payload.api_token:
        try:
            params = {"q": q_clean, "type": "o", "order_by": "score desc"}
            if payload.court:
                params["court"] = payload.court

            url = f"{COURTLISTENER_BASE_URL}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Token {payload.api_token}",
                    "User-Agent": "A2A-Defense-Gateway-CourtScraper/1.0 (https://a2a.vilmamonroy.com)",
                },
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("results", [])[: payload.max_results]:
                    records.append(
                        CaselawOpinionRecord(
                            case_name=item.get("caseName", "Unknown Case"),
                            citation=item.get("citation", ["No Citation"])[0] if isinstance(item.get("citation"), list) and item.get("citation") else "Unreported",
                            court=item.get("court", "Federal Court"),
                            date_filed=str(item.get("dateFiled", "Unknown")),
                            status="API_RETRIEVED",
                            snippet=item.get("headline", "")[:250],
                            docket_number=item.get("docketNumber", "N/A"),
                            download_url=item.get("absolute_url", ""),
                        )
                    )
                if records:
                    source = "COURTLISTENER_V4_LIVE"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            logger.warning("Fallo en llamada a CourtListener API v4 (%s). Usando fallback local.", exc)

    # Si no se obtuvieron resultados remotos, filtrar en el fixture determinista local
    if not records:
        tokens = [t.lower() for t in q_clean.split()]
        matched = []
        for fix in OFFLINE_CASELAW_FIXTURES:
            score = sum(
                1 for t in tokens if t in fix["case_name"].lower() or t in fix["citation"].lower() or t in fix["snippet"].lower()
            )
            if score > 0 or not tokens:
                matched.append((score, fix))

        matched.sort(key=lambda x: x[0], reverse=True)
        for _, m in matched[: payload.max_results]:
            records.append(CaselawOpinionRecord(**m))

        # Si aún no hay coincidencias exactas, devolver los precedentes principales
        if not records:
            for fix in OFFLINE_CASELAW_FIXTURES[: payload.max_results]:
                records.append(CaselawOpinionRecord(**fix))

    return CaselawSearchOutput(
        doc_id=f"CASELAW-SEARCH-{hash(q_clean) & 0xFFFFFFFF:08x}",
        query=q_clean,
        total_results=len(records),
        source=source,
        results=records,
    )
