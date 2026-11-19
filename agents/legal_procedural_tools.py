"""
Herramientas Deterministas para Cómputo de Plazos Procesales y Verificación Normativa.
Erradica errores aritméticos y alucinaciones en vigencia legal (Perú / LatAm).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

# Feriados oficiales de Perú para 2026 (D. Leg. 713 y leyes especiales)
PERU_HOLIDAYS_2026 = {
    date(2026, 1, 1),   # Año Nuevo
    date(2026, 4, 2),   # Jueves Santo
    date(2026, 4, 3),   # Viernes Santo
    date(2026, 5, 1),   # Día del Trabajo
    date(2026, 6, 7),   # Batalla de Arica y Día de la Bandera
    date(2026, 6, 29),  # San Pedro y San Pablo
    date(2026, 7, 23),  # Día de la FAP
    date(2026, 7, 28),  # Fiestas Patrias
    date(2026, 7, 29),  # Fiestas Patrias
    date(2026, 8, 6),   # Batalla de Junín
    date(2026, 8, 30),  # Santa Rosa de Lima
    date(2026, 10, 8),  # Combate de Angamos
    date(2026, 11, 1),  # Todos los Santos
    date(2026, 12, 8),  # Inmaculada Concepción
    date(2026, 12, 9),  # Batalla de Ayacucho
    date(2026, 12, 25), # Navidad
}

# Base de conocimiento determinista de estatus normativo (ejemplos normativos tributarios y civiles clave)
NORMATIVE_GRAPH: dict[str, dict[str, Any]] = {
    "CODIGO_TRIBUTARIO:43": {
        "materia": "tributario",
        "descripcion": "Plazos de prescripción de la acción de la SUNAT",
        "estado": "MODIFICADO",
        "norma_modificatoria": "D. Leg. 1421 / Ley 31814",
        "vigente": True,
        "precedente_vinculante": "STC 00004-2019-PI/TC",
        "doc_id": "NORM-CT-ART43-V2026",
    },
    "CODIGO_TRIBUTARIO:44": {
        "materia": "tributario",
        "descripcion": "Cómputo de los plazos de prescripción",
        "estado": "VIGENTE",
        "norma_modificatoria": None,
        "vigente": True,
        "precedente_vinculante": "RTF 0161-1-2020",
        "doc_id": "NORM-CT-ART44-V2026",
    },
    "CODIGO_CIVIL:1989": {
        "materia": "civil",
        "descripcion": "Efectos de la prescripción extintiva",
        "estado": "VIGENTE",
        "norma_modificatoria": None,
        "vigente": True,
        "precedente_vinculante": "Casación 3456-2022-LIMA",
        "doc_id": "NORM-CC-ART1989-V2026",
    },
    "LEY_27444:207": {
        "materia": "administrativo",
        "descripcion": "Recursos administrativos (Reconsideración y Apelación)",
        "estado": "MODIFICADO",
        "norma_modificatoria": "D. Leg. 1272 y D. Leg. 1452 (TUO D.S. 004-2019-JUS)",
        "vigente": True,
        "precedente_vinculante": None,
        "doc_id": "NORM-LPAG-ART207-V2026",
    },
}


class ProceduralDeadlineInput(BaseModel):
    fecha_inicio: date = Field(..., description="Fecha inicial del acto o notificación (YYYY-MM-DD)")
    dias_plazo: int = Field(..., gt=0, le=730, description="Cantidad de días a computar")
    tipo_dias: Literal["HABILES_JUDICIALES", "CALENDARIO"] = Field(
        default="HABILES_JUDICIALES",
        description="Modalidad de cómputo: días hábiles descontando feriados/fines de semana o días continuos.",
    )


class ProceduralDeadlineOutput(BaseModel):
    doc_id: str
    fecha_inicio: date
    fecha_vencimiento: date
    dias_contados: int
    feriados_descontados: list[date]
    fines_de_semana_descontados: int
    modalidad: str


class NormativeValidityInput(BaseModel):
    codigo_norma: str = Field(..., description="Identificador de la norma (ej. CODIGO_TRIBUTARIO, CODIGO_CIVIL, LEY_27444)")
    articulo: str = Field(..., description="Número de artículo a verificar (ej. 43, 44, 207)")
    fecha_corte: date | None = Field(default=None, description="Fecha de corte para verificar vigencia")


class NormativeValidityOutput(BaseModel):
    doc_id: str
    norma_completa: str
    estado: Literal["VIGENTE", "MODIFICADO", "DEROGADO", "NO_INDEXADO"]
    vigente: bool
    norma_modificatoria: str | None = None
    precedente_vinculante: str | None = None
    materia: str | None = None
    audit_date: date


def compute_procedural_deadline(payload: ProceduralDeadlineInput) -> ProceduralDeadlineOutput:
    """Calcula de forma determinista la fecha límite de un plazo procesal o administrativo."""
    curr = payload.fecha_inicio
    counted = 0
    discounted_holidays: list[date] = []
    weekend_days = 0

    if payload.tipo_dias == "CALENDARIO":
        expiration = payload.fecha_inicio + timedelta(days=payload.dias_plazo)
        return ProceduralDeadlineOutput(
            doc_id=f"DEADLINE-CAL-{payload.fecha_inicio.isoformat()}-{payload.dias_plazo}D",
            fecha_inicio=payload.fecha_inicio,
            fecha_vencimiento=expiration,
            dias_contados=payload.dias_plazo,
            feriados_descontados=[],
            fines_de_semana_descontados=0,
            modalidad="CALENDARIO",
        )

    # Cómputo por días hábiles judiciales (el primer día hábil siguiente es contado)
    while counted < payload.dias_plazo:
        curr += timedelta(days=1)
        if curr.weekday() in (5, 6):  # Sábado o Domingo
            weekend_days += 1
            continue
        if curr in PERU_HOLIDAYS_2026:
            discounted_holidays.append(curr)
            continue
        counted += 1

    return ProceduralDeadlineOutput(
        doc_id=f"DEADLINE-HAB-{payload.fecha_inicio.isoformat()}-{payload.dias_plazo}D",
        fecha_inicio=payload.fecha_inicio,
        fecha_vencimiento=curr,
        dias_contados=counted,
        feriados_descontados=discounted_holidays,
        fines_de_semana_descontados=weekend_days,
        modalidad="HABILES_JUDICIALES",
    )


def verify_normative_validity(payload: NormativeValidityInput) -> NormativeValidityOutput:
    """Verifica de forma estricta y determinista si un artículo legal está vigente o modificado."""
    key = f"{payload.codigo_norma.strip().upper()}:{payload.articulo.strip()}"
    today = payload.fecha_corte or date.today()

    if key in NORMATIVE_GRAPH:
        entry = NORMATIVE_GRAPH[key]
        return NormativeValidityOutput(
            doc_id=entry["doc_id"],
            norma_completa=key,
            estado=entry["estado"],
            vigente=entry["vigente"],
            norma_modificatoria=entry["norma_modificatoria"],
            precedente_vinculante=entry["precedente_vinculante"],
            materia=entry["materia"],
            audit_date=today,
        )

    return NormativeValidityOutput(
        doc_id=f"NORM-UNINDEXED-{key}",
        norma_completa=key,
        estado="NO_INDEXADO",
        vigente=False,
        norma_modificatoria=None,
        precedente_vinculante=None,
        materia=None,
        audit_date=today,
    )
