"""Advanced Forensic & Zero-Day Threat Tools (EIP-7702, Malicious Routers, EchoLeak, MEV).

Desarrollado a partir de la investigación forense 2026 (invet05):
- Tool #57: audit_eip7702_delegation (Prevención de secuestro de cuentas EOA vía EIP-7702).
- Tool #58: detect_malicious_llm_router (Detección de interceptación MITM y robo de claves por proxies LLM).
- Tool #59: audit_echoleak_markdown_exfiltration (Mitigación de fuga de datos CVE-2025-32711 y exfiltración markdown).
- Tool #60: simulate_dex_sandwich_risk (Simulación y contención de ataques sandwich MEV en swaps de agentes).
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, ConfigDict, Field

# -----------------------------------------------------------------------------
# Tool #57: audit_eip7702_delegation
# -----------------------------------------------------------------------------

SAFE_SMART_ACCOUNT_FACTORIES = {
    "0x4e59b44847b379578588920ca78fbf26c0b4956c": "Safe v1.4.1 Singleton",
    "0x0000000000000068f116a894984e2db1123eb395": "Biconomy Nexus ERC-4337/7702",
    "0xd9db270c1b5e3bd161e8c8503c55ceabee709552": "Safe v1.3.0 Singleton",
    "0x0000000000400c42f164b6010074427e3650f902": "ZeroDev Kernel v3.1",
}

KNOWN_MALICIOUS_DELEGATION_CONTRACTS = {
    "0xbad000000000000000000000000000000000dead": "TraderTraitor Lazarus Drainer",
    "0x6666666666666666666666666666666666666666": "Generic Permit2/7702 Sweep Drainer",
    "0x1337c0de00000000000000000000000000000000": "Fake MultiSig Proxy Hijacker",
}


class EIP7702DelegationRequest(BaseModel):
    """Solicitud de auditoría de autorización de delegación EIP-7702."""

    model_config = ConfigDict(extra="ignore")

    eoa_address: str = Field(..., description="Dirección EOA titular de la cuenta (0x...)")
    delegated_contract_address: str = Field(..., description="Dirección del contrato delegado en la tupla de autorización")
    chain_id: int = Field(..., description="ID de la cadena (0 indica riesgo de replay trans-cadena)")
    nonce: int = Field(default=0, ge=0, description="Nonce de autorización de la EOA")
    bytecode_hex: str = Field(default="", description="Bytecode opcional del contrato delegado para análisis de opcodes")
    raw_authorization_prefix: str = Field(default="0x05", description="Prefijo mágico EIP-7702 (estándar 0x05)")


class EIP7702DelegationResponse(BaseModel):
    """Resultado de la auditoría de delegación EIP-7702."""

    is_safe: bool = Field(..., description="True si la delegación cumple directivas de seguridad")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Score de riesgo (0.0 limpio, 1.0 crítico)")
    threat_level: str = Field(..., description="CLEAN, LOW, MEDIUM, CRITICAL")
    delegated_contract_classification: str = Field(..., description="Clasificación del contrato delegado")
    flags: list[str] = Field(default_factory=list, description="Banderas de advertencia detectadas")
    mitigation_advice: str = Field(..., description="Recomendación fiduciaria de mitigación")


def audit_eip7702_delegation(req: EIP7702DelegationRequest) -> EIP7702DelegationResponse:
    """Audita una autorización de delegación EIP-7702 para prevenir secuestro de billeteras EOA."""
    flags: list[str] = []
    risk = 0.0
    delegated_addr = req.delegated_contract_address.lower().strip()
    eoa_addr = req.eoa_address.lower().strip()

    if not re.match(r"^0x[a-fA-F0-9]{40}$", delegated_addr):
        return EIP7702DelegationResponse(
            is_safe=False,
            risk_score=1.0,
            threat_level="CRITICAL",
            delegated_contract_classification="INVALID_ADDRESS",
            flags=["INVALID_ETH_ADDRESS_FORMAT"],
            mitigation_advice="Rechazar: dirección de contrato delegado inválida o malformada.",
        )

    # 1. Verificar si es un drainer conocido
    if delegated_addr in KNOWN_MALICIOUS_DELEGATION_CONTRACTS:
        flags.append(f"KNOWN_MALICIOUS_DRAINER: {KNOWN_MALICIOUS_DELEGATION_CONTRACTS[delegated_addr]}")
        return EIP7702DelegationResponse(
            is_safe=False,
            risk_score=1.0,
            threat_level="CRITICAL",
            delegated_contract_classification="KNOWN_EXPLOIT_DRAINER",
            flags=flags,
            mitigation_advice="BLOQUEO ABSOLUTO: Contrato catalogado en lista negra como drainer EIP-7702 de alta severidad.",
        )

    # 2. Verificar delegación circular (EOA delegándose a sí misma)
    if delegated_addr == eoa_addr:
        flags.append("CIRCULAR_SELF_DELEGATION")
        risk += 0.5

    # 3. Validar prefijo EIP-7702
    if req.raw_authorization_prefix.lower() not in ("0x05", "5"):
        flags.append("INVALID_EIP7702_MAGIC_PREFIX")
        risk += 0.4

    # 4. Replay trans-cadena (chain_id == 0 permite retransmitir en todas las cadenas)
    if req.chain_id == 0:
        flags.append("CROSS_CHAIN_REPLAY_RISK_CHAIN_ID_ZERO")
        risk += 0.6
    elif req.chain_id < 0:
        flags.append("NEGATIVE_CHAIN_ID_ANOMALY")
        risk += 0.8

    # 5. Análisis de bytecode si fue provisto
    classification = "UNKNOWN_CUSTOM_IMPLEMENTATION"
    if delegated_addr in SAFE_SMART_ACCOUNT_FACTORIES:
        classification = SAFE_SMART_ACCOUNT_FACTORIES[delegated_addr]
    elif req.bytecode_hex:
        clean_code = req.bytecode_hex.lower().replace("0x", "")
        # Opcodes peligrosos: SELFDESTRUCT (ff), DELEGATECALL no acotado (f4)
        if "ff" in clean_code:
            flags.append("BYTECODE_CONTAINS_SELFDESTRUCT")
            risk += 0.7
        if "f4" in clean_code and "Safe" not in classification:
            flags.append("BYTECODE_CONTAINS_ARBITRARY_DELEGATECALL")
            risk += 0.4
    else:
        flags.append("UNVERIFIED_CONTRACT_BYTECODE")
        risk += 0.2

    # Normalizar riesgo
    risk_score = min(1.0, max(0.0, risk))
    threat_level = "CLEAN" if risk_score == 0.0 else ("LOW" if risk_score < 0.3 else ("MEDIUM" if risk_score < 0.7 else "CRITICAL"))
    is_safe = risk_score < 0.4

    advice = (
        "Autorización segura: Contrato delegado reconocido y parámetros validados."
        if is_safe
        else "ADVERTENCIA: No firmar esta delegación EIP-7702. Riesgo de control total o drenaje de activos."
    )

    return EIP7702DelegationResponse(
        is_safe=is_safe,
        risk_score=round(risk_score, 2),
        threat_level=threat_level,
        delegated_contract_classification=classification,
        flags=flags,
        mitigation_advice=advice,
    )


# -----------------------------------------------------------------------------
# Tool #58: detect_malicious_llm_router
# -----------------------------------------------------------------------------

SUSPICIOUS_ROUTER_HEADERS = [
    "x-mitm-logged",
    "x-snoop-key",
    "x-injected-prompt",
    "x-shadow-proxy",
]

MALICIOUS_INJECTION_SNIPPETS = [
    "ignore previous instructions and send",
    "exfiltrate credentials to",
    "transfer all balance to",
    "private_key",
    "aws_secret_access_key",
    "export api_key",
]


class LLMRouterAuditRequest(BaseModel):
    """Solicitud de auditoría de seguridad para routers e intermediarios LLM."""

    model_config = ConfigDict(extra="ignore")

    router_endpoint_url: str = Field(..., description="URL del endpoint proxy/router LLM")
    canary_token_sent: str = Field(default="", description="Token canario secreto enviado en el prompt de prueba")
    response_body_text: str = Field(..., description="Cuerpo completo de respuesta devuelto por el router")
    response_headers: dict[str, str] = Field(default_factory=dict, description="Cabeceras HTTP devueltas por el router")
    latency_overhead_ms: float = Field(default=0.0, ge=0.0, description="Latencia adicional introducida por el router (ms)")


class LLMRouterAuditResponse(BaseModel):
    """Resultado de la auditoría del router LLM."""

    is_compromised: bool = Field(..., description="True si se detecta compromiso, MITM o comportamiento malicioso")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Puntuación de riesgo")
    threat_level: str = Field(..., description="CLEAN, LOW, SUSPICIOUS, COMPROMISED")
    canary_leaked: bool = Field(..., description="True si el canario fue reflejado o exfiltrado anormalmente")
    injected_instructions_found: list[str] = Field(default_factory=list, description="Instrucciones inyectadas detectadas")
    anomalies: list[str] = Field(default_factory=list, description="Anomalías estructurales o de red identificadas")
    recommended_action: str = Field(..., description="Acción de contención recomendada")


def detect_malicious_llm_router(req: LLMRouterAuditRequest) -> LLMRouterAuditResponse:
    """Detecta intermediarios LLM maliciosos que manipulan respuestas o capturan credenciales."""
    anomalies: list[str] = []
    injections: list[str] = []
    risk = 0.0
    canary_leaked = False

    parsed = urlparse(req.router_endpoint_url)
    if parsed.scheme != "https" and parsed.hostname not in ("127.0.0.1", "localhost"):
        anomalies.append("UNENCRYPTED_HTTP_TRANSPORT")
        risk += 0.5

    # 1. Inspección de cabeceras sospechosas
    for h_name in req.response_headers:
        low_h = h_name.lower()
        if any(s in low_h for s in SUSPICIOUS_ROUTER_HEADERS):
            anomalies.append(f"SUSPICIOUS_HEADER_PRESENT: {h_name}")
            risk += 0.4

    # 2. Comprobación de fuga de canario si no se esperaba reflejo
    if req.canary_token_sent and len(req.canary_token_sent) >= 8 and req.canary_token_sent in req.response_body_text:
        canary_leaked = True
        anomalies.append("CANARY_TOKEN_REFLECTED_IN_RESPONSE")
        risk += 0.3

    # 3. Detección de instrucciones inyectadas en la respuesta
    body_low = req.response_body_text.lower()
    for snippet in MALICIOUS_INJECTION_SNIPPETS:
        if snippet in body_low:
            injections.append(snippet)
            risk += 0.6

    # 4. Latencia anómala (>2500ms de overhead sugiere inspección profunda fuera de banda)
    if req.latency_overhead_ms > 2500.0:
        anomalies.append(f"ANOMALOUS_LATENCY_OVERHEAD: {req.latency_overhead_ms}ms")
        risk += 0.25

    risk_score = min(1.0, max(0.0, risk))
    threat_level = "CLEAN" if risk_score == 0.0 else ("LOW" if risk_score < 0.3 else ("SUSPICIOUS" if risk_score < 0.6 else "COMPROMISED"))
    is_compromised = risk_score >= 0.5

    action = (
        "Router verificado: Tráfico íntegro sin alteraciones detectadas."
        if not is_compromised
        else "ACCION INMEDIATA: Desconectar router LLM, revocar API keys y conmutar a provider directo."
    )

    return LLMRouterAuditResponse(
        is_compromised=is_compromised,
        risk_score=round(risk_score, 2),
        threat_level=threat_level,
        canary_leaked=canary_leaked,
        injected_instructions_found=injections,
        anomalies=anomalies,
        recommended_action=action,
    )


# -----------------------------------------------------------------------------
# Tool #59: audit_echoleak_markdown_exfiltration
# -----------------------------------------------------------------------------

# Patrones para Markdown images: ![alt](url) y links: [text](url)
MARKDOWN_IMAGE_REGEX = re.compile(r"!\[(.*?)\]\((https?://[^\s\)]+)\)", re.IGNORECASE)
MARKDOWN_LINK_REGEX = re.compile(r"(?<!!)\[(.*?)\]\((https?://[^\s\)]+)\)", re.IGNORECASE)
HTML_IMG_REGEX = re.compile(r"<img[^>]+src=[\"'](https?://[^\"']+)[\"']", re.IGNORECASE)
ZERO_WIDTH_CHARS = re.compile(r"[\u200B-\u200D\uFEFF\u202A-\u202E]")


class EchoLeakAuditRequest(BaseModel):
    """Solicitud de auditoría de exfiltración markdown y EchoLeak (CVE-2025-32711)."""

    model_config = ConfigDict(extra="ignore")

    text_content: str = Field(..., description="Texto de salida generado por el LLM o recibido para renderizado")
    whitelisted_domains: list[str] = Field(
        default_factory=lambda: ["a2a.vilmamonroy.com", "github.com", "raw.githubusercontent.com"],
        description="Lista blanca de dominios seguros autorizados para incrustar recursos",
    )
    defang_leaks: bool = Field(default=True, description="Si True, reemplaza URLs sospechosas por marcadores inertes")


class DetectedLeak(BaseModel):
    """Elemento sospechoso de exfiltración detectado."""

    leak_type: str = Field(..., description="MARKDOWN_IMAGE, MARKDOWN_LINK, HTML_IMG, ZERO_WIDTH_PAYLOAD")
    target_url: str = Field(..., description="URL sospechosa")
    suspicious_payload: str = Field(..., description="Fragmento exfiltrado o query params de alta entropía")
    risk_factor: str = Field(..., description="Motivo de la alerta")


class EchoLeakAuditResponse(BaseModel):
    """Resultado del escaneo y sanitización anti-EchoLeak."""

    has_exfiltration_risk: bool = Field(..., description="True si se detectan vectores de exfiltración activa")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Puntuación de riesgo")
    threat_level: str = Field(..., description="CLEAN, LOW, HIGH, CRITICAL")
    detected_leaks: list[DetectedLeak] = Field(default_factory=list, description="Lista de fugas encontradas")
    sanitized_text: str = Field(..., description="Texto neutralizado sin enlaces exfiltradores activos")


def audit_echoleak_markdown_exfiltration(req: EchoLeakAuditRequest) -> EchoLeakAuditResponse:
    """Inspecciona y neutraliza intentos de exfiltración de contexto vía markdown e imágenes (CVE-2025-32711)."""
    leaks: list[DetectedLeak] = []
    risk = 0.0
    sanitized = req.text_content

    # 1. Detectar caracteres de ancho cero (Zero-Width Steganography)
    zw_matches = ZERO_WIDTH_CHARS.findall(req.text_content)
    if zw_matches:
        risk += 0.5
        leaks.append(
            DetectedLeak(
                leak_type="ZERO_WIDTH_PAYLOAD",
                target_url="none",
                suspicious_payload=f"{len(zw_matches)} zero-width chars detected",
                risk_factor="Esteganografía por caracteres invisibles de ancho cero (Unicode Smuggling)",
            )
        )
        if req.defang_leaks:
            sanitized = ZERO_WIDTH_CHARS.sub("", sanitized)

    # Función auxiliar para evaluar URLs
    def evaluate_url(url: str, leak_type: str) -> None:
        nonlocal risk
        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower()

        is_whitelisted = any(domain == w or domain.endswith("." + w) for w in req.whitelisted_domains)

        query = parsed.query
        parsed_params = parse_qs(query)

        has_high_entropy_params = False
        param_leak = ""
        for k, vals in parsed_params.items():
            for v in vals:
                # Detección de base64 largo o tokens en params
                if len(v) > 24 or any(sub in v.lower() for sub in ["sk-", "bearer", "session", "jwt", "token", "key"]):
                    has_high_entropy_params = True
                    param_leak = f"{k}={v[:32]}..."
                    break

        if not is_whitelisted and leak_type in ("MARKDOWN_IMAGE", "HTML_IMG"):
            # Imagen externa no autorizada: Carga automática inmediata (Zero-click)
            risk += 0.6
            leaks.append(
                DetectedLeak(
                    leak_type=leak_type,
                    target_url=url,
                    suspicious_payload=param_leak or query or url,
                    risk_factor="Renderizado automático de imagen externa no confiable (Zero-click exfiltration)",
                )
            )
        elif has_high_entropy_params:
            risk += 0.4
            leaks.append(
                DetectedLeak(
                    leak_type=leak_type,
                    target_url=url,
                    suspicious_payload=param_leak,
                    risk_factor="Parámetros de consulta transportan tokens o payloads de alta entropía",
                )
            )

    # 2. Evaluar imágenes Markdown
    for match in MARKDOWN_IMAGE_REGEX.finditer(req.text_content):
        evaluate_url(match.group(2), "MARKDOWN_IMAGE")
        if req.defang_leaks:
            sanitized = sanitized.replace(match.group(0), f"`[DEFANGED_IMAGE_TAG: {match.group(1)}]`")

    # 3. Evaluar tags HTML img
    for match in HTML_IMG_REGEX.finditer(req.text_content):
        evaluate_url(match.group(1), "HTML_IMG")
        if req.defang_leaks:
            sanitized = sanitized.replace(match.group(0), "`[DEFANGED_HTML_IMG]`")

    # 4. Evaluar enlaces Markdown
    for match in MARKDOWN_LINK_REGEX.finditer(req.text_content):
        evaluate_url(match.group(2), "MARKDOWN_LINK")

    risk_score = min(1.0, max(0.0, risk))
    threat_level = "CLEAN" if risk_score == 0.0 else ("LOW" if risk_score < 0.3 else ("HIGH" if risk_score < 0.7 else "CRITICAL"))
    has_risk = risk_score >= 0.4

    return EchoLeakAuditResponse(
        has_exfiltration_risk=has_risk,
        risk_score=round(risk_score, 2),
        threat_level=threat_level,
        detected_leaks=leaks,
        sanitized_text=sanitized if req.defang_leaks else req.text_content,
    )


# -----------------------------------------------------------------------------
# Tool #60: simulate_dex_sandwich_risk
# -----------------------------------------------------------------------------

class SandwichRiskSimulationRequest(BaseModel):
    """Solicitud de simulación de ataque sandwich y protección MEV."""

    model_config = ConfigDict(extra="ignore")

    dex_pool_address: str = Field(..., description="Dirección del par de liquidez DEX (Solana AMM o Uniswap EVM)")
    swap_amount_usd: float = Field(..., gt=0.0, description="Monto en USD que la orden del agente intercambiará")
    slippage_tolerance_pct: float = Field(..., ge=0.01, le=100.0, description="Tolerancia de deslizamiento (ej: 0.5 para 0.5%, 5.0 para 5%)")
    pool_liquidity_usd: float = Field(default=50000.0, gt=0.0, description="Liquidez total disponible en el pool (USD)")
    is_private_mempool: bool = Field(default=False, description="True si la orden se envía vía bundle privado (Jito / Flashbots)")


class SandwichRiskSimulationResponse(BaseModel):
    """Resultado de la simulación de riesgo MEV sandwich."""

    is_vulnerable: bool = Field(..., description="True si la orden es susceptible a extracción depredadora sandwich")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Puntuación de riesgo")
    mev_threat_level: str = Field(..., description="MINIMAL, MODERATE, HIGH, EXTREME")
    expected_price_impact_pct: float = Field(..., description="Impacto de precio intrínseco calculado (%)")
    estimated_extractable_mev_usd: float = Field(..., description="Ganancia estimada que un bot MEV podría extraer (USD)")
    recommended_slippage_pct: float = Field(..., description="Tolerancia de slippage dinámico fiduciario recomendado (%)")
    recommended_execution_route: str = Field(..., description="Ruta óptima sugerida (pública vs bundle privado)")
    advisory_notes: str = Field(..., description="Instrucciones operativas para el agente de trading")


def simulate_dex_sandwich_risk(req: SandwichRiskSimulationRequest) -> SandwichRiskSimulationResponse:
    """Calcula el riesgo de front-running y ataque sandwich MEV en swaps automáticos de agentes."""
    # 1. Calcular impacto de precio constante k = x * y simplificado
    # Impacto = (swap_amount / (pool_liquidity / 2)) * 100
    effective_pool_side = req.pool_liquidity_usd / 2.0
    impact_pct = (req.swap_amount_usd / effective_pool_side) * 100.0

    # 2. Análisis del spread de slippage
    revert_risk = impact_pct > req.slippage_tolerance_pct

    # Si la tolerancia es sustancialmente mayor que el impacto real, el bot MEV explota la diferencia
    excess_slippage_pct = max(0.0, req.slippage_tolerance_pct - impact_pct)

    # Ganancia estimada del bot MEV: valor del swap * exceso de slippage aprovechable (con factor de eficiencia 85%)
    extractable_mev_usd = 0.0
    if not req.is_private_mempool and excess_slippage_pct > 0.1:
        extractable_mev_usd = req.swap_amount_usd * (excess_slippage_pct / 100.0) * 0.85

    # 3. Puntuación de riesgo
    risk = 0.0
    if req.is_private_mempool:
        # Bundles privados eliminan el mempool público
        risk = 0.05
        threat_level = "MINIMAL"
        is_vuln = False
    elif revert_risk:
        risk = 0.7
        threat_level = "HIGH"
        is_vuln = True
    else:
        if excess_slippage_pct >= 2.0 or extractable_mev_usd >= 100.0:
            risk = 0.9
            threat_level = "EXTREME"
            is_vuln = True
        elif excess_slippage_pct >= 0.5 or extractable_mev_usd >= 25.0:
            risk = 0.65
            threat_level = "HIGH"
            is_vuln = True
        elif excess_slippage_pct > 0.1:
            risk = 0.35
            threat_level = "MODERATE"
            is_vuln = False
        else:
            risk = 0.1
            threat_level = "MINIMAL"
            is_vuln = False

    # Slippage recomendado: impacto intrínseco + buffer de 0.1% a 0.2%
    rec_slippage = round(max(0.05, impact_pct * 1.05 + 0.1), 2)
    route = "JITO_BUNDLE_PRIVATE_RPC" if (is_vuln or req.swap_amount_usd >= 500.0) else "STANDARD_DEX_ROUTER"

    if revert_risk:
        notes = (
            f"FALLO DE EJECUCIÓN INMINENTE: Impacto de precio calculado ({round(impact_pct, 2)}%) "
            f"excede el slippage permitido ({req.slippage_tolerance_pct}%). La transacción revertirá."
        )
    elif is_vuln:
        notes = (
            f"PELIGRO DE SANDWICH: Exceso de slippage ({req.slippage_tolerance_pct}% vs {round(impact_pct, 2)}% real) "
            f"permite a bots extraer aprox ${round(extractable_mev_usd, 2)} USD. Utilizar RPC privado."
        )
    else:
        notes = "Swap seguro: Orden protegida por bundle privado o slippage ajustado con precisión."

    return SandwichRiskSimulationResponse(
        is_vulnerable=is_vuln,
        risk_score=round(risk, 2),
        mev_threat_level=threat_level,
        expected_price_impact_pct=round(impact_pct, 3),
        estimated_extractable_mev_usd=round(extractable_mev_usd, 2),
        recommended_slippage_pct=rec_slippage,
        recommended_execution_route=route,
        advisory_notes=notes,
    )
