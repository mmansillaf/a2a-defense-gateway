"""
Test Suite for US LegalTech Capabilities: Bluebook Citation Verification & Caselaw Search.
"""

from us_bluebook_validator import BluebookCitationInput, validate_bluebook_citation
from us_courtlistener_scraper import CaselawSearchInput, search_us_court_opinions


def test_bluebook_valid_canonical_scotus():
    """Valida una citación correcta de SCOTUS reconocida en la base canónica."""
    payload = BluebookCitationInput(raw_citation="Ashcroft v. Iqbal, 556 U.S. 662 (2009)")
    res = validate_bluebook_citation(payload)
    assert res.is_valid_format is True
    assert res.case_name == "Ashcroft v. Iqbal"
    assert res.volume == 556
    assert res.reporter == "U.S."
    assert res.first_page == 662
    assert res.year == 2009
    assert res.reporter_recognized is True
    assert res.verified_in_canonical_db is True
    assert res.precedent_status == "GOOD_LAW"


def test_bluebook_pinpoint_citation():
    """Valida una citación Bluebook con pinpoint page."""
    payload = BluebookCitationInput(raw_citation="Bell Atlantic Corp. v. Twombly, 550 U.S. 544, 570 (2007)")
    res = validate_bluebook_citation(payload)
    assert res.is_valid_format is True
    assert res.pinpoint_page == 570
    assert res.verified_in_canonical_db is True


def test_bluebook_detects_overruled_precedent():
    """Detecta precedentes anulados (Bad Law) como Roe v. Wade."""
    payload = BluebookCitationInput(raw_citation="Roe v. Wade, 410 U.S. 113 (1973)")
    res = validate_bluebook_citation(payload)
    assert res.is_valid_format is True
    assert res.precedent_status == "OVERRULED"
    assert any("PRECEDENTE ANULADO" in note for note in res.advisory_notes)
    assert any("Dobbs" in note for note in res.advisory_notes)


def test_bluebook_invalid_format():
    """Rechaza entradas que no cumplen con The Bluebook Rule 10."""
    payload = BluebookCitationInput(raw_citation="Invalid Case Without Reporter or Volume")
    res = validate_bluebook_citation(payload)
    assert res.is_valid_format is False
    assert any("Syntax error" in note for note in res.advisory_notes)


def test_bluebook_reporter_anachronism():
    """Detecta anacronismos temporales en reporteros modernos."""
    payload = BluebookCitationInput(
        raw_citation="Smith v. Jones, 100 F.4th 200 (1985)",
        strict_caselaw_lookup=False,
    )
    res = validate_bluebook_citation(payload)
    assert res.is_valid_format is True
    assert any("Anacronismo temporal" in note for note in res.advisory_notes)


def test_caselaw_search_offline_twombly():
    """Prueba de búsqueda de jurisprudencia por query conceptual en modo determinista."""
    payload = CaselawSearchInput(query="Twombly plausible pleading standard", max_results=2)
    res = search_us_court_opinions(payload)
    assert res.total_results >= 1
    top = res.results[0]
    assert "Twombly" in top.case_name
    assert top.citation == "550 U.S. 544"
    assert "plausible" in top.snippet.lower()


def test_caselaw_search_delaware_caremark():
    """Prueba de búsqueda de doctrina societaria de Delaware (Caremark duty)."""
    payload = CaselawSearchInput(query="Caremark corporate oversight duty", max_results=1)
    res = search_us_court_opinions(payload)
    assert len(res.results) == 1
    assert "Caremark" in res.results[0].case_name
    assert "Delaware Court of Chancery" in res.results[0].court


def test_audit_us_contract_clauses_full_suite():
    """Valida la auditoría de cláusulas de limitación de responsabilidad, indemnización y derechos de IA."""
    from us_contract_analyzer import ContractClauseAuditInput, audit_us_contract_clauses

    sample_contract = (
        "MASTER SERVICES AGREEMENT. "
        "Section 8. Limitation of Liability. IN NO EVENT SHALL EITHER PARTY'S AGGREGATE LIABILITY "
        "EXCEED THE TOTAL FEES PAID OR PAYABLE IN THE PRECEDING TWELVE MONTHS. In no event shall "
        "either party be liable for any consequential or indirect damages. "
        "Section 9. Indemnification. Provider shall defend and hold harmless Customer against third-party IP claims. "
        "Section 11. Governing Law. This Agreement shall be governed by the laws of the State of Delaware. "
        "Section 12. Artificial Intelligence Training. Provider may use customer data and prompt inputs to train "
        "machine learning models and generative AI systems."
    )
    payload = ContractClauseAuditInput(contract_text=sample_contract, strict_ai_clause_check=True)
    res = audit_us_contract_clauses(payload)

    assert res.detected_governing_law == "Delaware"
    assert res.detected_liability_cap_type == "FEES_PAID_12M"
    assert len(res.clauses_detected) >= 3
    assert any(c.clause_type == "LIMITATION_OF_LIABILITY" for c in res.clauses_detected)
    assert any(c.clause_type == "AI_DATA_RIGHTS_AND_CONFIDENTIALITY" for c in res.clauses_detected)
    assert any("Vendor retains right to train" in rf for rf in res.red_flags)
    assert res.overall_risk_score >= 50


def test_audit_us_contract_clauses_via_mcp():
    """Prueba de ejecución de audit_us_contract_clauses a través de MoltbookMonetizationMCPServer."""
    from mcp_server import MoltbookMonetizationMCPServer

    server = MoltbookMonetizationMCPServer()
    text = (
        "This Agreement is governed by the laws of the State of New York. "
        "In no event shall aggregate liability exceed $50,000. Customer agrees to indemnify Vendor."
    )
    res = server.call_tool("audit_us_contract_clauses", {"contract_text": text})
    assert "detected_governing_law" in res
    assert res["detected_governing_law"] == "New York"
    assert res["detected_liability_cap_type"] == "FIXED_MULTIPLE"
    assert res["total_clauses_analyzed"] >= 2
