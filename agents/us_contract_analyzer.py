"""
US Commercial Contract and Exhibit 10 Clause Forensics Engine.
Extracts and audits critical risk provisions: Limitation of Liability, Indemnification,
Governing Law & Forum Selection, Termination for Convenience, and AI Training/Data Rights.
Provides deterministic risk scoring (0-100) and red-flag identification.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ClauseItem(BaseModel):
    """Cláusula extraída con categorización, extracto textual y evaluación de riesgo."""
    clause_type: Literal[
        "LIMITATION_OF_LIABILITY",
        "INDEMNIFICATION",
        "GOVERNING_LAW_AND_VENUE",
        "TERMINATION_FOR_CONVENIENCE",
        "WARRANTIES_AND_DISCLAIMERS",
        "AI_DATA_RIGHTS_AND_CONFIDENTIALITY",
    ]
    raw_snippet: str
    risk_level: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    risk_notes: str


class ContractClauseAuditInput(BaseModel):
    """Parámetros de entrada para la auditoría forense de contratos comerciales de EE. UU."""
    model_config = ConfigDict(extra="forbid")

    contract_text: str = Field(..., min_length=20, description="Texto completo o extracto de contrato comercial o Exhibit 10")
    strict_ai_clause_check: bool = Field(default=True, description="Auditar derechos de entrenamiento de modelos de IA sobre datos")
    contract_title: str | None = Field(default=None, description="Título o identificador del contrato (ej. 'Master Services Agreement')")


class ContractClauseAuditOutput(BaseModel):
    """Dictamen forense determinista de riesgo contractual y mapeo de cláusulas."""
    contract_title: str
    content_sha256: str
    total_clauses_analyzed: int
    clauses_detected: list[ClauseItem]
    detected_governing_law: str | None
    detected_liability_cap_type: Literal["FIXED_MULTIPLE", "FEES_PAID_12M", "UNLIMITED", "DISCLAIMED", "NOT_FOUND"]
    overall_risk_score: int = Field(..., ge=0, le=100, description="Puntuación de riesgo (0=Seguro, 100=Riesgo Extremo)")
    risk_classification: Literal["LOW_RISK", "MODERATE_RISK", "HIGH_RISK", "CRITICAL_RISK"]
    red_flags: list[str]
    compliance_recommendations: list[str]


# Patrones deterministas para cláusulas contractuales clave en jurisprudencia y práctica mercantil de EE. UU.
_PATTERNS = {
    "LIMITATION_OF_LIABILITY": re.compile(
        r"(?i)\b(?:limitation\s+of\s+liability|aggregate\s+liability|in\s+no\s+event\s+shall|consequential\s+damages|indirect[,\s]+special\s+or\s+punitive)\b[\s\S]{0,350}?(?=\.\s+[A-Z]|\n\n|$)"
    ),
    "INDEMNIFICATION": re.compile(
        r"(?i)\b(?:indemnif(?:y|ication|ies)|hold\s+harmless|defend\s+and\s+hold\s+harmless)\b[\s\S]{0,350}?(?=\.\s+[A-Z]|\n\n|$)"
    ),
    "GOVERNING_LAW_AND_VENUE": re.compile(
        r"(?i)\b(?:governed\s+by\s+the\s+laws\s+of|laws\s+of\s+the\s+state\s+of|jurisdiction\s+and\s+venue|exclusive\s+jurisdiction\s+of\s+the\s+courts)\b[\s\S]{0,250}?(?=\.\s+[A-Z]|\n\n|$)"
    ),
    "TERMINATION_FOR_CONVENIENCE": re.compile(
        r"(?i)\b(?:terminate\s+this\s+agreement\s+for\s+convenience|terminate\s+without\s+cause|upon\s+\d+\s+days['’\s]+prior\s+written\s+notice)\b[\s\S]{0,250}?(?=\.\s+[A-Z]|\n\n|$)"
    ),
    "WARRANTIES_AND_DISCLAIMERS": re.compile(
        r"(?i)\b(?:as\s+is\s+and\s+with\s+all\s+faults|disclaim\s+all\s+warranties|implied\s+warranties\s+of\s+merchantability|fitness\s+for\s+a\s+particular\s+purpose)\b[\s\S]{0,250}?(?=\.\s+[A-Z]|\n\n|$)"
    ),
    "AI_DATA_RIGHTS_AND_CONFIDENTIALITY": re.compile(
        r"(?i)\b(?:train(?:ing)?\s+(?:artificial\s+intelligence|machine\s+learning|llm|models?)|use\s+customer\s+data\s+to\s+improve\s+the\s+service|generative\s+ai|prompt\s+inputs?|derived\s+weights)\b[\s\S]{0,300}?(?=\.\s+[A-Z]|\n\n|$)"
    ),
}

_GOV_LAW_STATES = [
    ("Delaware", re.compile(r"(?i)\b(?:state\s+of\s+delaware|delaware\s+law|court\s+of\s+chancery)\b")),
    ("New York", re.compile(r"(?i)\b(?:state\s+of\s+new\s+york|new\s+york\s+law|borough\s+of\s+manhattan)\b")),
    ("California", re.compile(r"(?i)\b(?:state\s+of\s+california|california\s+law|county\s+of\s+santa\s+clara|san\s+francisco)\b")),
    ("Texas", re.compile(r"(?i)\b(?:state\s+of\s+texas|texas\s+law|travis\s+county)\b")),
    ("Washington", re.compile(r"(?i)\b(?:state\s+of\s+washington|washington\s+law|king\s+county)\b")),
]


def audit_us_contract_clauses(payload: ContractClauseAuditInput) -> ContractClauseAuditOutput:
    """
    Audita y analiza contratos comerciales y acuerdos Exhibit 10 de SEC EDGAR.
    Identifica topes de responsabilidad, indemnizaciones desbalanceadas, foro legal
    y cláusulas de apropiación de datos para reentrenamiento de modelos de IA.
    """
    text = payload.contract_text
    sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    clauses: list[ClauseItem] = []
    red_flags: list[str] = []
    recommendations: list[str] = []
    base_risk = 15

    # 1. Detección de ley y jurisdicción gobernante
    gov_law: str | None = None
    for state_name, pat in _GOV_LAW_STATES:
        if pat.search(text):
            gov_law = state_name
            break

    # 2. Extracción de cláusulas estructuradas
    for c_type, pat in _PATTERNS.items():
        if c_type == "AI_DATA_RIGHTS_AND_CONFIDENTIALITY" and not payload.strict_ai_clause_check:
            continue

        match = pat.search(text)
        if match:
            snippet = match.group(0).strip().replace("\n", " ")
            snippet_clean = re.sub(r"\s+", " ", snippet)

            r_level: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = "LOW"
            r_notes = "Standard commercial provision observed."

            if c_type == "LIMITATION_OF_LIABILITY":
                if "sole and exclusive remedy" in snippet_clean.lower() or "disclaim" in snippet_clean.lower():
                    r_level = "HIGH"
                    r_notes = "Consequential damages disclaimed with sole remedy limitation."
                    base_risk += 20
                else:
                    r_level = "MEDIUM"
                    base_risk += 10

            elif c_type == "INDEMNIFICATION":
                if "defend and hold harmless" in snippet_clean.lower() and "gross negligence" not in snippet_clean.lower():
                    r_level = "HIGH"
                    r_notes = "Broad unilateral defense and hold harmless obligation without standard carve-outs."
                    base_risk += 25
                    red_flags.append("Broad indemnification clause without standard fault-based carve-outs.")
                else:
                    r_level = "MEDIUM"
                    base_risk += 12

            elif c_type == "AI_DATA_RIGHTS_AND_CONFIDENTIALITY":
                if re.search(r"(?i)\btrain(?:ing)?\b.*\b(?:models?|service)\b", snippet_clean):
                    r_level = "CRITICAL"
                    r_notes = "Provider claims rights to utilize customer prompts/data for AI/LLM model training."
                    base_risk += 35
                    red_flags.append("CRITICAL: Vendor retains right to train machine learning models on customer inputs/data.")
                    recommendations.append("Insert explicit Zero-Data Retention (ZDR) and No-Training Addendum.")

            elif c_type == "WARRANTIES_AND_DISCLAIMERS":
                if "as is" in snippet_clean.lower():
                    r_level = "MEDIUM"
                    r_notes = "Complete disclaimer of implied warranties of merchantability and fitness."
                    base_risk += 10

            elif c_type == "TERMINATION_FOR_CONVENIENCE":
                r_level = "LOW"
                r_notes = "Termination for convenience observed."

            clauses.append(
                ClauseItem(
                    clause_type=c_type,  # type: ignore[arg-type]
                    raw_snippet=snippet_clean[:280] + ("..." if len(snippet_clean) > 280 else ""),
                    risk_level=r_level,
                    risk_notes=r_notes,
                )
            )

    # 3. Clasificación de tipo de tope de responsabilidad (Liability Cap)
    cap_type: Literal["FIXED_MULTIPLE", "FEES_PAID_12M", "UNLIMITED", "DISCLAIMED", "NOT_FOUND"] = "NOT_FOUND"
    if re.search(r"(?i)fees\s+paid\s+(?:or\s+payable\s+)?in\s+the\s+(?:preceding\s+)?(?:twelve|12)\s+months", text):
        cap_type = "FEES_PAID_12M"
    elif re.search(r"(?i)(?:aggregate\s+liability\s+shall\s+not\s+exceed|\$[0-9,]+)", text):
        cap_type = "FIXED_MULTIPLE"
    elif re.search(r"(?i)in\s+no\s+event\s+shall.*liability\s+exceed\s+zero", text):
        cap_type = "DISCLAIMED"
    elif re.search(r"(?i)unlimited\s+liability", text):
        cap_type = "UNLIMITED"
        base_risk += 30
        red_flags.append("Unlimited liability exposure detected.")

    if cap_type == "NOT_FOUND":
        red_flags.append("No explicit aggregate liability cap identified in text (potential uncapped exposure).")
        base_risk += 15
        recommendations.append("Demand a bilateral aggregate liability cap pegged to 12 months fees paid.")

    if not gov_law:
        red_flags.append("Governing law and jurisdiction clause is missing or ambiguous.")
        base_risk += 10
        recommendations.append("Specify exclusive jurisdiction (e.g., State of Delaware or Southern District of New York).")

    final_score = min(100, max(0, base_risk))
    if final_score >= 75:
        risk_class = "CRITICAL_RISK"
    elif final_score >= 50:
        risk_class = "HIGH_RISK"
    elif final_score >= 30:
        risk_class = "MODERATE_RISK"
    else:
        risk_class = "LOW_RISK"

    return ContractClauseAuditOutput(
        contract_title=payload.contract_title or "Commercial Contract Audit",
        content_sha256=sha256,
        total_clauses_analyzed=len(clauses),
        clauses_detected=clauses,
        detected_governing_law=gov_law,
        detected_liability_cap_type=cap_type,
        overall_risk_score=final_score,
        risk_classification=risk_class,
        red_flags=red_flags,
        compliance_recommendations=recommendations,
    )
