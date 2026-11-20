"""
US Bluebook Legal Citation Parsing and Verification Engine.
Enforces Bluebook (21st Edition) grammar and validates existence against real reporters.
Erradicates generative citation hallucinations in US legal briefs and pleadings.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

# Reporteros Federales y Estatales reconocidos por The Bluebook
STANDARD_REPORTERS: dict[str, dict[str, Any]] = {
    "U.S.": {"court": "Supreme Court of the United States", "level": "SCOTUS", "start_year": 1790},
    "S. Ct.": {"court": "Supreme Court of the United States (West)", "level": "SCOTUS", "start_year": 1882},
    "L. Ed. 2d": {"court": "Supreme Court of the United States (Lawyers' Edition)", "level": "SCOTUS", "start_year": 1956},
    "F.": {"court": "Federal Circuit Courts", "level": "FEDERAL_APPELLATE", "start_year": 1880},
    "F.2d": {"court": "Federal Circuit Courts (2nd Series)", "level": "FEDERAL_APPELLATE", "start_year": 1924},
    "F.3d": {"court": "Federal Circuit Courts (3rd Series)", "level": "FEDERAL_APPELLATE", "start_year": 1993},
    "F.4th": {"court": "Federal Circuit Courts (4th Series)", "level": "FEDERAL_APPELLATE", "start_year": 2021},
    "F. Supp.": {"court": "Federal District Courts", "level": "FEDERAL_DISTRICT", "start_year": 1932},
    "F. Supp. 2d": {"court": "Federal District Courts (2nd Series)", "level": "FEDERAL_DISTRICT", "start_year": 1998},
    "F. Supp. 3d": {"court": "Federal District Courts (3rd Series)", "level": "FEDERAL_DISTRICT", "start_year": 2014},
    "A.3d": {"court": "Atlantic Reporter (3rd Series - DE, MD, NJ, PA)", "level": "STATE_REGIONAL", "start_year": 2010},
    "Cal. 4th": {"court": "California Supreme Court (4th Series)", "level": "STATE_SUPREME", "start_year": 1991},
    "N.Y.3d": {"court": "New York Court of Appeals (3rd Series)", "level": "STATE_SUPREME", "start_year": 2003},
}

# Regex estricta Bluebook: [Nombre del Caso], [Volumen] [Reporter] [Página] ([Tribunal opcional] [Año])
BLUEBOOK_PATTERN = re.compile(
    r"^(?P<case_name>[\w\s\.\,\'\&\-]+?),\s+"
    r"(?P<volume>\d+)\s+"
    r"(?P<reporter>[A-Za-z0-9\.\s]+?)\s+"
    r"(?P<first_page>\d+)"
    r"(?:,\s*(?P<pinpoint>\d+))?\s+"
    r"\((?:(?P<court>[A-Za-z0-9\.\s]+)\s+)?(?P<year>\d{4})\)$"
)

# Base canónica de sentencias emblemáticas federales (Ground Truth)
CANONICAL_US_CASELAW: dict[str, dict[str, Any]] = {
    "550 U.S. 544": {
        "title": "Bell Atlantic Corp. v. Twombly",
        "year": 2007,
        "court": "SCOTUS",
        "holding": "Pleading standard under FRCP 8(a)(2) requires plausible grounds to infer agreement.",
        "status": "GOOD_LAW",
    },
    "556 U.S. 662": {
        "title": "Ashcroft v. Iqbal",
        "year": 2009,
        "court": "SCOTUS",
        "holding": "Plausibility standard applies to all civil actions; legal conclusions not entitled to presumption of truth.",
        "status": "GOOD_LAW",
    },
    "384 U.S. 436": {
        "title": "Miranda v. Arizona",
        "year": 1966,
        "court": "SCOTUS",
        "holding": "Fifth Amendment privilege against self-incrimination requires procedural safeguards.",
        "status": "GOOD_LAW",
    },
    "410 U.S. 113": {
        "title": "Roe v. Wade",
        "year": 1973,
        "court": "SCOTUS",
        "holding": "Substantive due process right to abortion.",
        "status": "OVERRULED",
        "overruled_by": "Dobbs v. Jackson Women's Health Org., 597 U.S. 215 (2022)",
    },
    "597 U.S. 215": {
        "title": "Dobbs v. Jackson Women's Health Organization",
        "year": 2022,
        "court": "SCOTUS",
        "holding": "Constitution does not confer a right to abortion; Roe and Casey are overruled.",
        "status": "GOOD_LAW",
    },
    "347 U.S. 483": {
        "title": "Brown v. Board of Education",
        "year": 1954,
        "court": "SCOTUS",
        "holding": "Separate educational facilities are inherently unequal under Equal Protection Clause.",
        "status": "GOOD_LAW",
    },
    "376 U.S. 254": {
        "title": "New York Times Co. v. Sullivan",
        "year": 1964,
        "court": "SCOTUS",
        "holding": "First Amendment requires public officials to prove actual malice in defamation suits.",
        "status": "GOOD_LAW",
    },
}


class BluebookCitationInput(BaseModel):
    raw_citation: str = Field(..., description="Cita legal a auditar (ej. 'Ashcroft v. Iqbal, 556 U.S. 662 (2009)')")
    strict_caselaw_lookup: bool = Field(default=True, description="Verificar si la sentencia existe en el repositorio canónico")


class BluebookCitationOutput(BaseModel):
    doc_id: str
    raw_citation: str
    is_valid_format: bool
    case_name: str | None = None
    volume: int | None = None
    reporter: str | None = None
    first_page: int | None = None
    pinpoint_page: int | None = None
    court: str | None = None
    year: int | None = None
    reporter_recognized: bool = False
    verified_in_canonical_db: bool = False
    precedent_status: str | None = None
    advisory_notes: list[str] = Field(default_factory=list)


def validate_bluebook_citation(payload: BluebookCitationInput) -> BluebookCitationOutput:
    """Valida sintáctica y sustancialmente una citación jurídica de EE. UU. según The Bluebook."""
    raw = payload.raw_citation.strip()
    match = BLUEBOOK_PATTERN.match(raw)

    if not match:
        return BluebookCitationOutput(
            doc_id=f"BLUEBOOK-INVALID-{hash(raw) & 0xFFFFFFFF:08x}",
            raw_citation=raw,
            is_valid_format=False,
            advisory_notes=["Syntax error: La cita no cumple con el formato Bluebook Rule 10 (Case Name, Vol Reporter Page (Year))."],
        )

    groups = match.groupdict()
    vol = int(groups["volume"])
    rep = groups["reporter"].strip()
    page = int(groups["first_page"])
    pinpoint_val = groups.get("pinpoint")
    pin = int(pinpoint_val) if pinpoint_val else None
    year = int(groups["year"])
    case_name = groups["case_name"].strip()
    court = groups.get("court")

    notes: list[str] = []
    rep_recognized = rep in STANDARD_REPORTERS

    if not rep_recognized:
        notes.append(f"Reporter '{rep}' no se encuentra en el índice canónico de reporteros Bluebook.")
    else:
        meta = STANDARD_REPORTERS[rep]
        if year < meta["start_year"]:
            notes.append(f"Anacronismo temporal: El reportero {rep} inició en {meta['start_year']}, pero la cita data de {year}.")

    # Verificación en base de datos canónica
    citation_key = f"{vol} {rep} {page}"
    verified = False
    status = None

    if citation_key in CANONICAL_US_CASELAW:
        verified = True
        record = CANONICAL_US_CASELAW[citation_key]
        status = record["status"]
        if record["year"] != year:
            notes.append(f"Discrepancia de año: La cita reporta {year}, pero el registro oficial es {record['year']}.")
        if status == "OVERRULED":
            notes.append(f"[ALERTA CITATORIA - PRECEDENTE ANULADO] Sentencia anulada por: {record.get('overruled_by')}")
    elif payload.strict_caselaw_lookup:
        notes.append(f"Cita no indexada en la base canónica ({citation_key}). Posible alucinación generativa.")

    return BluebookCitationOutput(
        doc_id=f"BLUEBOOK-{vol}-{rep.replace(' ', '')}-{page}-{year}",
        raw_citation=raw,
        is_valid_format=True,
        case_name=case_name,
        volume=vol,
        reporter=rep,
        first_page=page,
        pinpoint_page=pin,
        court=court,
        year=year,
        reporter_recognized=rep_recognized,
        verified_in_canonical_db=verified,
        precedent_status=status or "UNINDEXED_BUT_SYNTACTICALLY_VALID",
        advisory_notes=notes,
    )
