"""
Radar de Contrataciones Estatales de Software, IA y Transformación Digital en Perú.
Clasifica requerimientos técnicos y convocatorias SEACE/OSCE según la taxonomía
oficial, sugiriendo códigos CUBSO y entidades públicas de compra objetivo.
"""

from __future__ import annotations

import hashlib
import unicodedata

from pydantic import BaseModel, Field


def _strip_accents(text: str) -> str:
    """Elimina tildes y diacríticos para normalización fonética/ortográfica."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )


TAXONOMIA_LICITACIONES_PERU: dict[str, dict[str, list[str] | str]] = {
    "desarrollo_software_apps": {
        "cluster": "Desarrollo de Software, Apps Móviles y Web",
        "sinonimos": [
            "desarrollo de software",
            "fabrica de software",
            "aplicativo movil",
            "aplicacion web",
            "sistema de informacion",
            "software a medida",
            "desarrollo de aplicativo",
            "mantenimiento evolutivo de software",
        ],
        "sectores_objetivo": [
            "GORE Arequipa",
            "GORE Cusco",
            "GORE Piura",
            "MEF (SIAF RP)",
            "Universidades Nacionales",
            "Petroperu",
        ],
        "codigo_cubso_sugerido": "811115 (Servicios de ingeniería de software)",
    },
    "tramite_documentario_std_pki": {
        "cluster": "Trámite Documentario, Mesa de Partes y Firma Digital (PKI)",
        "sinonimos": [
            "sistema de tramite documentario",
            "mesa de partes virtual",
            "firma digital",
            "gestion documental electronica",
            "interoperabilidad pide",
            "notificacion electronica",
        ],
        "sectores_objetivo": [
            "Municipalidades Provinciales",
            "Municipalidades Distritales",
            "Poder Judicial",
            "SUNARP",
            "Gobiernos Regionales",
        ],
        "codigo_cubso_sugerido": "811118 (Servicios de diseño de sistemas y arquitectura)",
    },
    "tributario_rentas_cpe": {
        "cluster": "Sistemas de Rentas, Fiscalización y Facturación CPE",
        "sinonimos": [
            "rentas municipales",
            "sistema de recaudacion tributaria",
            "impuesto predial",
            "arbitrios municipales",
            "fiscalizacion tributaria",
            "comprobantes de pago electronicos",
            "facturacion electronica ubl",
        ],
        "sectores_objetivo": [
            "SAT Huancayo / Piura / Trujillo",
            "Municipalidades de Provincias",
            "EPS Regionales (Sedapar, Sedalib, Sedam)",
            "SUNAT",
        ],
        "codigo_cubso_sugerido": "811122 (Software de gestión y administración tributaria)",
    },
    "legaltech_expedientes_forense": {
        "cluster": "LegalTech, Expedientes Electrónicos y Forense Digital",
        "sinonimos": [
            "expediente judicial electronico",
            "expediente administrativo electronico",
            "custodia digital iso 27037",
            "ediscovery",
            "busqueda jurisprudencial",
            "motor de indexacion legal",
        ],
        "sectores_objetivo": [
            "Poder Judicial",
            "Ministerio Público",
            "Tribunal Fiscal",
            "SUNARP",
            "Indecopi",
        ],
        "codigo_cubso_sugerido": "811118 (Sistemas de archivo y gestión jurídica)",
    },
    "vision_computacional_edge_ai": {
        "cluster": "Visión Computacional y Edge AI",
        "sinonimos": [
            "analitica de video",
            "reconocimiento facial",
            "lectura de placas",
            "lpr",
            "anpr",
            "analitica forense de video",
            "videovigilancia inteligente",
        ],
        "sectores_objetivo": [
            "Municipalidades Provinciales",
            "GOREs",
            "Mininter",
            "Migraciones",
        ],
        "codigo_cubso_sugerido": "811115 (Sistemas de Seguridad Electrónica con IA)",
    },
    "asistentes_conversacionales": {
        "cluster": "IA Conversacional y Canales Digitales",
        "sinonimos": [
            "asistente virtual",
            "chatbot",
            "canal digital interactivo",
            "atencion omnicanal automatizada",
            "agente conversacional",
        ],
        "sectores_objetivo": [
            "RENIEC",
            "ONPE",
            "SUNASS",
            "Banca y Universidades",
        ],
        "codigo_cubso_sugerido": "811121 (Suscripción y servicios de canales digitales)",
    },
    "analitica_predictiva": {
        "cluster": "Machine Learning y Analítica Predictiva",
        "sinonimos": [
            "analitica predictiva",
            "mineria de datos",
            "modelamiento predictivo",
            "deteccion de anomalias",
            "perfilamiento de riesgo algoritmico",
        ],
        "sectores_objetivo": [
            "SUNAT",
            "OSINERGMIN",
            "SBS",
            "Gran Minería",
        ],
        "codigo_cubso_sugerido": "811119 (Consultoría de Tecnologías de Información)",
    },
}


class ProcurementMatchInput(BaseModel):
    requirement_text: str = Field(..., description="Texto del requerimiento técnico, TDR o título de licitación en Perú")


class ProcurementMatchOutput(BaseModel):
    is_match: bool
    matched_clusters: list[str]
    suggested_cubso_codes: list[str]
    target_public_entities: list[str]
    matched_keywords: list[str]
    relevance_score: float
    doc_id: str


def match_peruvian_procurement(payload: ProcurementMatchInput) -> ProcurementMatchOutput:
    """Clasifica un requerimiento según la taxonomía de contrataciones del Estado peruano."""
    text = payload.requirement_text.strip()
    if not text:
        return ProcurementMatchOutput(
            is_match=False,
            matched_clusters=[],
            suggested_cubso_codes=[],
            target_public_entities=[],
            matched_keywords=[],
            relevance_score=0.0,
            doc_id="PROCUREMENT-EMPTY",
        )

    t_norm = _strip_accents(text.lower())
    matched_clusters: list[str] = []
    cubso_codes: list[str] = []
    entities: list[str] = []
    keywords: list[str] = []

    for crit in TAXONOMIA_LICITACIONES_PERU.values():
        cluster_name = str(crit["cluster"])
        sinonimos = crit["sinonimos"]
        assert isinstance(sinonimos, list)
        sectores = crit["sectores_objetivo"]
        assert isinstance(sectores, list)
        cubso = str(crit["codigo_cubso_sugerido"])

        cluster_hit = False
        for s in sinonimos:
            s_norm = _strip_accents(s.lower())
            if s_norm in t_norm:
                keywords.append(s)
                cluster_hit = True

        if cluster_hit:
            matched_clusters.append(cluster_name)
            cubso_codes.append(cubso)
            entities.extend(sectores)

    unique_clusters = list(dict.fromkeys(matched_clusters))
    unique_cubso = list(dict.fromkeys(cubso_codes))
    unique_entities = list(dict.fromkeys(entities))
    unique_keywords = list(dict.fromkeys(keywords))

    score = min(1.0, len(unique_keywords) * 0.25)
    is_match = len(unique_clusters) > 0

    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    doc_id = f"PROCUREMENT-MATCH-{len(unique_clusters)}C-{h}"

    return ProcurementMatchOutput(
        is_match=is_match,
        matched_clusters=unique_clusters,
        suggested_cubso_codes=unique_cubso,
        target_public_entities=unique_entities,
        matched_keywords=unique_keywords,
        relevance_score=round(score, 2),
        doc_id=doc_id,
    )
