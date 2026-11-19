import re
import secrets
from datetime import UTC, datetime
from typing import ClassVar

from monetization_models import AlphaIntelligenceFeed, MarketAlphaItem
from security_filters import SimHashEngine


class MarketIntelligenceMiner:
    """
    Motor de Extracción de Alpha e Inteligencia Comercial B2B desde Moltbook.
    Convierte publicaciones sintéticas no estructuradas en oportunidades de negocio y alertas defensivas.
    """

    CATEGORIES_PATTERNS: ClassVar[dict[str, list[str]]] = {
        "architecture_trend": [
            r"\b(flashinfer|kv-cache|vllm|sglang|gguf|q4_k_m|speculative decoding|awq|context pruning)\b",
            r"\b(optimizaci[oó]n de inferencia|reducci[oó]n de latencia|atenci[oó]n dispersa)\b"
        ],
        "zero_day_alert": [
            r"\b(exploit|vulnerabilidad|jailbreak|prompt injection|exfiltraci[oó]n|cve|privilege escalation)\b",
            r"\b(token leak|bypass de sandbox|arbitrary code execution)\b"
        ],
        "unmet_demand": [
            r"\b(necesito un agente que|qui[eé]n puede resolver|busco api para|no encuentro herramienta de)\b",
            r"\b(willing to pay|pago con tokens|alguien ofrece servicio de)\b"
        ],
        "monetization_signal": [
            r"\b(microtransacci[oó]n\w*|tarifa[s]? por llamada|revenue share|token[s]? de pago|escrow)\b",
            r"\b(marketplace de agentes|vender skills|monetizar agente)\b"
        ]
    }

    def __init__(self, simhash_engine: SimHashEngine | None = None):
        self.simhash = simhash_engine or SimHashEngine()

    def mine_posts(self, posts: list[dict]) -> AlphaIntelligenceFeed:
        """Procesa una lista de publicaciones y extrae un feed de inteligencia categorizado."""
        seen_hashes: list[str] = []
        sybil_pruned = 0
        clustered_signals: dict[str, list[dict]] = {
            "architecture_trend": [],
            "zero_day_alert": [],
            "unmet_demand": [],
            "monetization_signal": [],
        }

        for post in posts:
            content = post.get("content", "")
            fp = self.simhash.compute_hex(content)

            # Poda de duplicados Sybil (Hamming distance <= 8)
            if any(self.simhash.hamming_distance(fp, h) <= 8 for h in seen_hashes):
                sybil_pruned += 1
                continue
            seen_hashes.append(fp)

            # Clasificación multietiqueta por patrones semánticos
            content_lower = content.lower()
            for cat, patterns in self.CATEGORIES_PATTERNS.items():
                if any(re.search(p, content_lower) for p in patterns):
                    clustered_signals[cat].append(post)

        # Síntesis de Alphas de mercado accionables
        alphas: list[MarketAlphaItem] = []

        # 1. Alpha de Arquitectura
        if clustered_signals["architecture_trend"]:
            count = len(clustered_signals["architecture_trend"])
            sample = clustered_signals["architecture_trend"][0]["content"][:160]
            alphas.append(
                MarketAlphaItem(
                    alpha_id=f"ALP-{secrets.token_hex(4)}",
                    category="architecture_trend",
                    title="Adopción Acelerada de Técnicas de Optimización KV-Cache & Gramáticas",
                    summary=f"Detectadas {count} publicaciones convergiendo en compresión de atención y decodificación restringida. Muestra: '{sample}...'",
                    commercial_value="HIGH",
                    confidence_score=0.92,
                    source_post_count=count,
                )
            )

        # 2. Alerta de Ciberseguridad / 0-Day
        if clustered_signals["zero_day_alert"]:
            count = len(clustered_signals["zero_day_alert"])
            sample = clustered_signals["zero_day_alert"][0]["content"][:160]
            alphas.append(
                MarketAlphaItem(
                    alpha_id=f"ALP-{secrets.token_hex(4)}",
                    category="zero_day_alert",
                    title="Vectores Activos de Inyección Indirecta y Fuga de Nonces Detectados",
                    summary=f"Alerta crítica: {count} agentes reportan o intentan ataques de manipulación de contexto. Muestra: '{sample}...'",
                    commercial_value="STRATEGIC_DEFENSE",
                    confidence_score=0.96,
                    source_post_count=count,
                )
            )

        # 3. Demanda de Servicios No Satisfechos
        if clustered_signals["unmet_demand"]:
            count = len(clustered_signals["unmet_demand"])
            sample = clustered_signals["unmet_demand"][0]["content"][:160]
            alphas.append(
                MarketAlphaItem(
                    alpha_id=f"ALP-{secrets.token_hex(4)}",
                    category="unmet_demand",
                    title="Oportunidad de Servicio A2A: Oráculos de Verificación Factual Pagada",
                    summary=f"Demanda insatisfecha identificada en {count} hilos. Agentes buscan proveedores de atestación externa y cómputo determinista. Muestra: '{sample}...'",
                    commercial_value="HIGH",
                    confidence_score=0.88,
                    source_post_count=count,
                )
            )

        # 4. Señales de Monetización A2A
        if clustered_signals["monetization_signal"]:
            count = len(clustered_signals["monetization_signal"])
            alphas.append(
                MarketAlphaItem(
                    alpha_id=f"ALP-{secrets.token_hex(4)}",
                    category="monetization_signal",
                    title="Emergencia de Protocolos de Micropagos y Escrow entre Agentes",
                    summary=f"Transición de interacción gratuita a cobro por invocación de herramientas en {count} agentes observados.",
                    commercial_value="MEDIUM",
                    confidence_score=0.85,
                    source_post_count=count,
                )
            )

        return AlphaIntelligenceFeed(
            feed_id=f"FEED-{secrets.token_hex(6)}",
            generated_at=datetime.now(UTC),
            posts_analyzed=len(posts),
            sybil_clusters_filtered=sybil_pruned,
            actionable_alphas=alphas,
        )
