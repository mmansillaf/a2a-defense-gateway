"""
Agentic Threat Sentinel & Web3 Drainer Defense Suite.
Herramientas #51, #52 y #53 del Ecosistema A2A Defense Gateway.

Mitiga:
- Tool Poisoning & prompt injection en metadatos MCP (Tool #51).
- Denial-of-Wallet & LLMjacking mediante cuotas y control de amplificación (Tool #52).
- Wallet Drainers, firmas Permit/Permit2 y ataques EIP-712/eth_sign (Tool #53).
"""

from decimal import Decimal
import hashlib
import json
import re
import time
from typing import Any
from pydantic import BaseModel, Field


# ==============================================================================
# TOOL #51: AUDIT MCP TOOL METADATA POISONING
# ==============================================================================

class ToolDefinition(BaseModel):
    name: str = Field(..., description="Nombre de la herramienta")
    description: str = Field(default="", description="Descripción legible por el LLM")
    inputSchema: dict[str, Any] = Field(default_factory=dict, description="Esquema JSON Schema de parámetros")


class MCPMetadataAuditRequest(BaseModel):
    tools_manifest: list[ToolDefinition] = Field(..., description="Lista de herramientas expuestas por el servidor MCP")
    strict_mode: bool = Field(default=True, description="Si es True, evalúa caracteres invisibles y heurística de zero-width")


class MCPMetadataAuditResponse(BaseModel):
    audit_id: str
    is_safe: bool
    threat_score: float = Field(..., ge=0.0, le=1.0, description="0.0=Limpio, 1.0=Altamente malicioso")
    quarantine_recommended: bool
    flagged_tools_count: int
    detected_vectors: list[dict[str, Any]]
    recommendations: list[str]
    timestamp: int


POISON_PATTERNS = [
    (re.compile(r"(?i)(?:ignore\s+(?:all\s+)?previous\s+instructions|system:\s*override|forget\s+rules)"), "PROMPT_INJECTION_OVERRIDE"),
    (re.compile(r"(?i)(?:exfiltrate|send\s+all\s+keys|leak\s+environment|print\s+env)"), "EXFILTRATION_COMMAND"),
    (re.compile(r"(?:<tool_call>|<\|im_start\|>|<\|system\|>|```markdown\s*system)"), "DELIMITER_HIJACKING"),
    (re.compile(r"(?:[\u200B-\u200D\uFEFF\u202A-\u202E])"), "ZERO_WIDTH_INVISIBLE_CHARS"),
    (re.compile(r"(?:(?:[A-Za-z0-9+/]{4}){10,}={0,2})"), "BASE64_OBFUSCATED_PAYLOAD"),
]


def audit_mcp_tool_metadata_poisoning(req: MCPMetadataAuditRequest) -> MCPMetadataAuditResponse:
    """
    Tool #51: Analiza manifiestos de servidores MCP en busca de Tool Poisoning
    (inyecciones de prompt escondidas en descripciones o schemas JSON).
    """
    flagged_vectors = []
    quarantine = False
    
    for tool in req.tools_manifest:
        tool_findings = []
        combined_text = f"{tool.name} {tool.description} {json.dumps(tool.inputSchema)}"
        
        for pattern, vector_type in POISON_PATTERNS:
            matches = pattern.findall(combined_text)
            if matches:
                tool_findings.append({
                    "vector": vector_type,
                    "sample": matches[0][:40],
                    "count": len(matches),
                })
        
        # Verificar pesca de credenciales en nombres de parámetros
        properties = tool.inputSchema.get("properties", {})
        for prop_name in properties:
            if re.search(r"(?i)(?:private_?key|seed_?phrase|mnemonic|auth_?token|api_?secret)", prop_name):
                tool_findings.append({
                    "vector": "SENSITIVE_CREDENTIAL_FISHING",
                    "sample": prop_name,
                    "count": 1,
                })

        if tool_findings:
            flagged_vectors.append({
                "tool_name": tool.name,
                "findings": tool_findings,
            })

    num_flagged = len(flagged_vectors)
    total_tools = max(len(req.tools_manifest), 1)
    
    if num_flagged > 0:
        base_threat = min(1.0, 0.4 + (num_flagged / total_tools) * 0.6)
        quarantine = base_threat >= 0.7 or any(
            any(f["vector"] in ("PROMPT_INJECTION_OVERRIDE", "EXFILTRATION_COMMAND") for f in v["findings"])
            for v in flagged_vectors
        )
    else:
        base_threat = 0.0

    recommendations = []
    if quarantine:
        recommendations.append("BLOQUEAR Y CUARENTENAR: Manifiesto MCP contiene vectores de tool poisoning hostiles.")
    elif num_flagged > 0:
        recommendations.append("SANITIZAR: Se detectaron metadatos sospechosos o posibles ofuscaciones Base64.")
    else:
        recommendations.append("APROBADO: Herramientas verificadas y limpias de inyecciones semánticas.")

    audit_entropy = f"mcp_poison:{num_flagged}:{time.time()}"
    audit_id = f"aud_mcp_{hashlib.sha256(audit_entropy.encode()).hexdigest()[:16]}"

    return MCPMetadataAuditResponse(
        audit_id=audit_id,
        is_safe=num_flagged == 0,
        threat_score=round(base_threat, 2),
        quarantine_recommended=quarantine,
        flagged_tools_count=num_flagged,
        detected_vectors=flagged_vectors,
        recommendations=recommendations,
        timestamp=int(time.time()),
    )


# ==============================================================================
# TOOL #52: ENFORCE DENIAL-OF-WALLET QUOTA (LLMjacking & Amplification Control)
# ==============================================================================

class DenialOfWalletRequest(BaseModel):
    session_id: str = Field(..., description="ID de sesión del agente")
    agent_id: str = Field(..., description="Identificador del agente")
    prompt_tokens: int = Field(..., ge=0, description="Tokens consumidos en el prompt de entrada")
    completion_tokens: int = Field(..., ge=0, description="Tokens consumidos en la respuesta")
    thinking_tokens: int = Field(default=0, ge=0, description="Tokens de razonamiento CoT extendido")
    cost_usd: float = Field(..., ge=0.0, description="Costo monetario acumulado de la sesión")
    max_budget_usd: float = Field(default=5.0, description="Presupuesto máximo asignado a la sesión")
    max_amplification_ratio: float = Field(default=10.0, description="Ratio máx tolerado (completion+thinking)/prompt")


class DenialOfWalletResponse(BaseModel):
    quota_status: str = Field(..., description="'QUOTA_HEALTHY' o 'DENIAL_OF_WALLET_BLOCKED'")
    agent_id: str
    session_id: str
    total_tokens: int
    amplification_ratio: float
    budget_exceeded: bool
    reasoning_loop_detected: bool
    action_enforced: str = Field(..., description="'ALLOW', 'THROTTLE' o 'HALT_KILL_SWITCH'")
    incident_hash: str | None
    timestamp: int


def enforce_denial_of_wallet_quota(req: DenialOfWalletRequest) -> DenialOfWalletResponse:
    """
    Tool #52: Monitorea y frena ataques de Denial-of-Wallet / LLMjacking,
    cortando bucles de amplificación de tokens y gasto desmedido de inferencia.
    """
    total_tokens = req.prompt_tokens + req.completion_tokens + req.thinking_tokens
    denominator = max(req.prompt_tokens, 1)
    amplification_ratio = round((req.completion_tokens + req.thinking_tokens) / denominator, 2)
    
    budget_exceeded = req.cost_usd >= req.max_budget_usd
    # Bucle de razonamiento: thinking tokens desproporcionados respecto a la complejidad de entrada
    reasoning_loop = req.thinking_tokens > (req.prompt_tokens * 15) and req.thinking_tokens > 2000
    ratio_breach = amplification_ratio > req.max_amplification_ratio

    is_blocked = budget_exceeded or reasoning_loop or ratio_breach
    
    if is_blocked:
        status = "DENIAL_OF_WALLET_BLOCKED"
        action = "HALT_KILL_SWITCH"
        entropy = f"{req.session_id}:{req.cost_usd}:{total_tokens}:{time.time()}"
        incident_hash = f"dow_{hashlib.sha256(entropy.encode()).hexdigest()}"
    else:
        status = "QUOTA_HEALTHY"
        action = "ALLOW"
        incident_hash = None

    return DenialOfWalletResponse(
        quota_status=status,
        agent_id=req.agent_id,
        session_id=req.session_id,
        total_tokens=total_tokens,
        amplification_ratio=amplification_ratio,
        budget_exceeded=budget_exceeded,
        reasoning_loop_detected=reasoning_loop,
        action_enforced=action,
        incident_hash=incident_hash,
        timestamp=int(time.time()),
    )


# ==============================================================================
# TOOL #53: AUDIT EIP-712 PERMIT DRAINER PAYLOAD
# ==============================================================================

KNOWN_DRAINERS = {
    "0x0000000000000000000000000000000000000000": "NULL_ADDRESS",
    "0x000046a6f1e8093b16752765b2633054170845a7": "KNOWN_INFERNO_DRAINER_OPERATOR",
    "0xd8da6bf26964af9d7eed9e03e53415d37aa96045": "TEST_BENIGN_VITALIK",
}

INFINITE_ALLOWANCE_HEX = "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"


class EIP712DomainInput(BaseModel):
    name: str = Field(default="", description="Nombre de la dApp/protocolo")
    version: str = Field(default="1")
    chainId: int = Field(default=1, description="EVM Chain ID (1=Ethereum, 8453=Base, 42161=Arbitrum)")
    verifyingContract: str = Field(..., description="Dirección del contrato verificador")


class EIP712DrainerAuditRequest(BaseModel):
    primary_type: str = Field(..., description="Tipo de firma: Permit, Permit2, PermitSingle, PermitBatch, PersonalSign")
    domain: EIP712DomainInput
    message: dict[str, Any] = Field(..., description="Estructura de datos del mensaje EIP-712")
    raw_hash: str | None = Field(default=None, description="Hash si fue solicitado vía eth_sign")


class EIP712DrainerAuditResponse(BaseModel):
    audit_id: str
    is_dangerous_drainer: bool
    drainer_risk_score: float = Field(..., ge=0.0, le=1.0)
    drainer_flags: list[str]
    recommended_action: str = Field(..., description="'SAFE_TO_SIGN', 'REJECT_INFINITE_APPROVAL', 'CRITICAL_ABORT_DRAINER_DETECTED'")
    details: dict[str, Any]
    timestamp: int


def audit_eip712_permit_drainer_payload(req: EIP712DrainerAuditRequest) -> EIP712DrainerAuditResponse:
    """
    Tool #53: Audita payloads tipados EIP-712 y firmas Permit/Permit2 en busca de
    patrones de Wallet Drainers, firmas ciegas y vaciado de balances.
    """
    flags = []
    risk = 0.0

    # 1. Chequeo de firma ciega (eth_sign)
    if req.primary_type.lower() in ("personalsign", "eth_sign") or req.raw_hash:
        flags.append("BLIND_SIGNATURE_ETH_SIGN: Firma ciega de hash arbitrario sin decodificación legible.")
        risk = max(risk, 0.95)

    # 2. Chequeo de Spender malicioso o no verificado
    spender = (
        req.message.get("spender")
        or req.message.get("operator")
        or (req.message.get("details", {}).get("spender") if isinstance(req.message.get("details"), dict) else None)
    )
    if spender:
        spender_lower = str(spender).lower()
        if spender_lower in KNOWN_DRAINERS and "DRAINER" in KNOWN_DRAINERS[spender_lower]:
            flags.append(f"KNOWN_DRAINER_OPERATOR: Spender coincide con operador malicioso ({KNOWN_DRAINERS[spender_lower]}).")
            risk = 1.0

    # 3. Asignación ilimitada (Infinite Approval) en Permit / Permit2
    value_val = req.message.get("value") or req.message.get("amount")
    if value_val is not None:
        val_str = str(value_val).lower()
        if val_str == INFINITE_ALLOWANCE_HEX or val_str == "115792089237316195423570985008687907853269984665640564039457584007913129639935" or (val_str.isdigit() and int(val_str) > 10**30):
            flags.append("INFINITE_ALLOWANCE_PERMIT: Solicitud de aprobación infinita de saldo (Permit Drainer vector).")
            risk = max(risk, 0.85)

    # 4. Deadline / Expiración lejana en Permit2
    deadline = req.message.get("deadline") or req.message.get("sigDeadline") or (req.message.get("details", {}).get("expiration") if isinstance(req.message.get("details"), dict) else None)
    if deadline is not None and str(deadline).isdigit():
        d_val = int(deadline)
        if d_val > 2000000000 or d_val == 0:
            flags.append("PERPETUAL_DEADLINE: Vencimiento permanente de la autorización sin expiración.")
            risk = max(risk, 0.70)

    # 5. Determinación de acción
    if risk >= 0.85:
        action = "CRITICAL_ABORT_DRAINER_DETECTED"
        is_drainer = True
    elif risk >= 0.50:
        action = "REJECT_INFINITE_APPROVAL"
        is_drainer = True
    else:
        action = "SAFE_TO_SIGN"
        is_drainer = False

    audit_entropy = f"drainer:{req.primary_type}:{spender}:{time.time()}"
    audit_id = f"aud_drain_{hashlib.sha256(audit_entropy.encode()).hexdigest()[:16]}"

    return EIP712DrainerAuditResponse(
        audit_id=audit_id,
        is_dangerous_drainer=is_drainer,
        drainer_risk_score=risk,
        drainer_flags=flags,
        recommended_action=action,
        details={
            "primary_type": req.primary_type,
            "spender": spender,
            "chain_id": req.domain.chainId,
            "contract": req.domain.verifyingContract,
        },
        timestamp=int(time.time()),
    )
