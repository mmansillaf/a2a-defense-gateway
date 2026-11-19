"""
Tests unitarios deterministas para las herramientas de portafolio integradas:
1. vba_macro_forensics (audit_excel_macro_forensics)
2. peruvian_procurement_radar (match_peruvian_procurement)
"""

from peruvian_procurement_radar import (
    ProcurementMatchInput,
    match_peruvian_procurement,
)
from vba_macro_forensics import (
    MacroForensicsInput,
    audit_vba_macro_code,
)


def test_vba_macro_forensics_detects_shell_and_confusion() -> None:
    obfuscated_vba = """
    Private Declare PtrSafe Function VirtualAlloc Lib "kernel32" (ByVal lpAddress As Long) As Long
    Sub O0l10O11lO()
        Dim O0l10O11lO_val As String
        O0l10O11lO_val = "p" & "assword" & "123"
        Shell "cmd.exe /c calc.exe"
    End Sub
    """
    payload = MacroForensicsInput(vba_code=obfuscated_vba, auto_deobfuscate=True)
    res = audit_vba_macro_code(payload)

    assert res.is_suspicious is True
    assert res.risk_level == "CRITICAL"
    assert "Shell" in res.detected_shell_invocations
    assert len(res.detected_dll_declarations) == 1
    assert "VirtualAlloc Lib 'kernel32'" in res.detected_dll_declarations[0]
    assert res.confusion_identifiers_found >= 1
    assert "sym_" in res.normalized_preview
    assert res.doc_id.startswith("MACRO-AUDIT-CRITICAL-")


def test_vba_macro_forensics_safe_code() -> None:
    safe_vba = """
    Sub FormatCells()
        Range("A1:B10").Font.Bold = True
        Range("A1").Value = "Total Ventas"
    End Sub
    """
    payload = MacroForensicsInput(vba_code=safe_vba, auto_deobfuscate=True)
    res = audit_vba_macro_code(payload)

    assert res.is_suspicious is False
    assert res.risk_level == "LOW"
    assert len(res.detected_shell_invocations) == 0
    assert len(res.detected_dll_declarations) == 0


def test_peruvian_procurement_radar_matches_software_and_legaltech() -> None:
    sample_tender = (
        "CONTRATACIÓN DE SERVICIO DE FÁBRICA DE SOFTWARE PARA LA IMPLEMENTACIÓN "
        "DEL EXPEDIENTE JUDICIAL ELECTRÓNICO Y MESA DE PARTES VIRTUAL"
    )
    payload = ProcurementMatchInput(requirement_text=sample_tender)
    res = match_peruvian_procurement(payload)

    assert res.is_match is True
    assert res.relevance_score > 0.4
    assert any("Desarrollo de Software" in c for c in res.matched_clusters)
    assert any("LegalTech" in c for c in res.matched_clusters)
    assert any("Poder Judicial" in e for e in res.target_public_entities)
    assert any("811115" in code or "811118" in code for code in res.suggested_cubso_codes)
    assert res.doc_id.startswith("PROCUREMENT-MATCH-")


def test_peruvian_procurement_radar_empty_or_unrelated() -> None:
    payload = ProcurementMatchInput(requirement_text="Adquisición de combustible diesel B5")
    res = match_peruvian_procurement(payload)

    assert res.is_match is False
    assert len(res.matched_clusters) == 0
    assert res.relevance_score == 0.0
