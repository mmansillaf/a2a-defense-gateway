"""
Pruebas Unitarias para Herramientas de Cómputo Procesal y Grafo Normativo.
Valida el descuento exacto de feriados peruanos (D. Leg. 713), fines de semana y vigencia determinista.
"""

from datetime import date

from legal_procedural_tools import (
    NormativeValidityInput,
    ProceduralDeadlineInput,
    compute_procedural_deadline,
    verify_normative_validity,
)


def test_compute_procedural_deadline_business_days_with_holidays():
    # Inicia el miércoles 1 de abril de 2026
    # Jueves 2 y Viernes 3 de abril son feriados de Semana Santa
    # Sábado 4 y Domingo 5 son fin de semana
    # Día hábil 1: Lunes 6 de abril
    # Día hábil 2: Martes 7 de abril
    # Día hábil 3: Miércoles 8 de abril
    inp = ProceduralDeadlineInput(
        fecha_inicio=date(2026, 4, 1),
        dias_plazo=3,
        tipo_dias="HABILES_JUDICIALES",
    )
    res = compute_procedural_deadline(inp)

    assert res.dias_contados == 3
    assert res.fecha_vencimiento == date(2026, 4, 8)
    assert len(res.feriados_descontados) == 2
    assert date(2026, 4, 2) in res.feriados_descontados
    assert date(2026, 4, 3) in res.feriados_descontados
    assert res.fines_de_semana_descontados == 2
    assert res.doc_id.startswith("DEADLINE-HAB-2026-04-01-3D")


def test_compute_procedural_deadline_calendar_days():
    inp = ProceduralDeadlineInput(
        fecha_inicio=date(2026, 7, 20),
        dias_plazo=15,
        tipo_dias="CALENDARIO",
    )
    res = compute_procedural_deadline(inp)

    assert res.dias_contados == 15
    assert res.fecha_vencimiento == date(2026, 8, 4)
    assert res.modalidad == "CALENDARIO"


def test_verify_normative_validity_known_and_unindexed():
    # Artículo 43 Código Tributario (Modificado)
    v_ct = verify_normative_validity(
        NormativeValidityInput(codigo_norma="CODIGO_TRIBUTARIO", articulo="43")
    )
    assert v_ct.estado == "MODIFICADO"
    assert v_ct.vigente is True
    assert "D. Leg. 1421" in str(v_ct.norma_modificatoria)
    assert v_ct.doc_id == "NORM-CT-ART43-V2026"

    # Artículo 1989 Código Civil (Vigente)
    v_cc = verify_normative_validity(
        NormativeValidityInput(codigo_norma="CODIGO_CIVIL", articulo="1989")
    )
    assert v_cc.estado == "VIGENTE"
    assert v_cc.doc_id == "NORM-CC-ART1989-V2026"

    # Norma no indexada
    v_un = verify_normative_validity(
        NormativeValidityInput(codigo_norma="LEY_INEXISTENTE", articulo="999")
    )
    assert v_un.estado == "NO_INDEXADO"
    assert v_un.vigente is False
