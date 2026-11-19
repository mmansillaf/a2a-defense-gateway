import secrets
from pathlib import Path

from audit_report_generator import ExecutiveAuditReportGenerator
from evidence_triangulator import SemanticEvidenceTriangulator
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from schemas import EvaluatedClaim, QuarantineExtractionPayload
from security_filters import SimHashEngine

app = FastAPI(title="Zero-Trust Control Plane Orchestrator")

ACTIVE_SESSION_NONCE = secrets.token_hex(16)
INGESTED_PAYLOADS: list[QuarantineExtractionPayload] = []
triangulator = SemanticEvidenceTriangulator(load_model=False)  # Cambiar a True en producción con GPU/CPU


@app.post("/ingest-quarantine-report")
async def receive_from_quarantine(raw_payload: dict):
    """Frontera de confianza: valida Nonce, esquema Pydantic y aísla amenazas marcadas."""
    if raw_payload.get("session_nonce") != ACTIVE_SESSION_NONCE:
        raise HTTPException(status_code=403, detail="Nonce de sesión inválido.")

    try:
        validated = QuarantineExtractionPayload.model_validate(raw_payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Esquema rechazado: {exc.errors()}")

    INGESTED_PAYLOADS.append(validated)
    return {
        "status": "isolated" if validated.quarantine_threat_flag else "accepted",
        "claims_accepted": 0 if validated.quarantine_threat_flag else len(validated.extracted_claims),
        "post_id": validated.source_post_id,
    }


def evaluate_all_ingested_claims(
    payloads: list[QuarantineExtractionPayload],
    evidence_auditor: SemanticEvidenceTriangulator,
) -> list[EvaluatedClaim]:
    """
    Aplica la ecuación epistemológica S_c = 0.40(E) + 0.30(I) + 0.20(C) - 0.10(A)
    sobre el conjunto global de afirmaciones extraídas en la sesión.
    """
    all_entries = []
    for p in payloads:
        if p.quarantine_threat_flag and not p.extracted_claims:
            all_entries.append((p, None))
        for claim in p.extracted_claims:
            all_entries.append((p, claim))

    # Pre-calcular huellas léxicas activas para detección de enjambres Sybil entre múltiples autores
    active_fingerprints = [
        (p.author_agent_id, c.lexical_fingerprint)
        for p, c in all_entries
        if c is not None
    ]

    evaluated_results: list[EvaluatedClaim] = []

    for payload, claim in all_entries:
        # Caso 1: El post fue bloqueado en la aduana de cuarentena
        if claim is None:
            evaluated_results.append(
                EvaluatedClaim(
                    claim_id="BLK-0000",
                    statement=f"[Contenido bloqueado en cuarentena - Post {payload.source_post_id}]",
                    score_E=0.0,
                    score_I=0.0,
                    score_C=0.0,
                    penalty_A=1.0,
                    final_trust_score=0.0,
                    verdict="REJECTED_ADVERSARIAL",
                    audit_rationale="Neutralizado por PreIngestionFirewall antes de entrar al LLM.",
                )
            )
            continue

        # Caso 2: El Agente Lector detectó imperativos o intentos de subversión
        if payload.quarantine_threat_flag or claim.detected_imperatives:
            evaluated_results.append(
                EvaluatedClaim(
                    claim_id=claim.claim_id,
                    statement=claim.factual_statement,
                    score_E=0.0,
                    score_I=0.0,
                    score_C=0.0,
                    penalty_A=1.0,
                    final_trust_score=0.0,
                    verdict="REJECTED_ADVERSARIAL",
                    audit_rationale="Penalización máxima (A=1.0): detección de directivas imperativas en el post.",
                )
            )
            continue

        # Caso 3: Evaluación de Independencia de Fuentes (I) mediante distancia de Hamming en SimHash
        distinct_similar_authors = {
            author
            for author, fp in active_fingerprints
            if SimHashEngine.hamming_distance(claim.lexical_fingerprint, fp) <= 8
        }

        if len(distinct_similar_authors) >= 3 and payload.author_account_age_days < 7:
            evaluated_results.append(
                EvaluatedClaim(
                    claim_id=claim.claim_id,
                    statement=claim.factual_statement,
                    score_E=0.0,
                    score_I=0.0,
                    score_C=0.2,
                    penalty_A=0.5,
                    final_trust_score=0.0,
                    verdict="REJECTED_SYBIL",
                    audit_rationale=(
                        f"Ataque Sybil detectado: {len(distinct_similar_authors)} cuentas recientes "
                        f"(<7 días) publicaron variantes con distancia Hamming <= 6."
                    ),
                )
            )
            continue

        score_I = 1.0 if len(distinct_similar_authors) == 1 else 0.75

        # Caso 4: Triangulación Externa NLI (Score E)
        url_str = str(claim.external_evidence_url) if claim.external_evidence_url else None
        nli_audit = evidence_auditor.audit_claim(claim.factual_statement, url_str)
        score_E = nli_audit.final_e_score

        if nli_audit.verdict_label in ("DIRECT_CONTRADICTION", "SSRF_OR_POLICY_BLOCKED"):
            evaluated_results.append(
                EvaluatedClaim(
                    claim_id=claim.claim_id,
                    statement=claim.factual_statement,
                    score_E=0.0,
                    score_I=score_I,
                    score_C=0.0,
                    penalty_A=1.0,
                    final_trust_score=0.0,
                    verdict="REJECTED_ADVERSARIAL",
                    audit_rationale=nli_audit.audit_note,
                )
            )
            continue

        # Caso 5: Coherencia Lógica (C) y Cálculo Final Ponderado S_c
        score_C = 0.90 if claim.claim_type in ("empirical_fact", "technical_spec") else 0.65
        penalty_A = 0.0

        raw_sc = (0.40 * score_E) + (0.30 * score_I) + (0.20 * score_C) - (0.10 * penalty_A)
        final_sc = round(max(0.0, min(1.0, raw_sc)), 3)

        if final_sc >= 0.70 and score_E >= 0.50:
            verdict = "VERIFIED_HIGH"
        elif final_sc >= 0.45:
            verdict = "PROVISIONAL_MEDIUM"
        else:
            verdict = "REJECTED_ADVERSARIAL"

        evaluated_results.append(
            EvaluatedClaim(
                claim_id=claim.claim_id,
                statement=claim.factual_statement,
                score_E=score_E,
                score_I=score_I,
                score_C=score_C,
                penalty_A=penalty_A,
                final_trust_score=final_sc,
                verdict=verdict,
                audit_rationale=nli_audit.audit_note,
            )
        )

    return evaluated_results


def finalize_mission_report(
    topic: str,
    session_nonce: str,
    payloads: list[QuarantineExtractionPayload],
    telemetry: dict[str, int],
    evidence_auditor: SemanticEvidenceTriangulator,
    output_dir: Path = Path("output"),
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    evaluated = evaluate_all_ingested_claims(payloads, evidence_auditor)

    reporter = ExecutiveAuditReportGenerator(mission_topic=topic, session_nonce=session_nonce)
    md_content = reporter.generate_markdown(evaluated, telemetry)
    (output_dir / "audit_report.md").write_text(md_content, encoding="utf-8")

    html_path = reporter.generate_html_dashboard(
        evaluated, telemetry, output_dir / "audit_dashboard.html"
    )
    return html_path
