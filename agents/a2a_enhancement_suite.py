"""
Suite de Enriquecimiento y Optimización A2A para Gobernanza de Herramientas MCP.
Cubre las brechas empíricas detectadas en 20,000 publicaciones de Moltbook:
1. Anti-Hollow OK: Validación estricta de postcondiciones en cadenas de herramientas (P-01).
2. Auditoría Forense de Poda de Contexto: Detección de pérdida de información y gaps en orquestación (P-03).
3. Circuit Breaker de Presupuesto Agéntico: Control de gasto acumulado y freno a bucles infinitos (P-05).
4. Notario de Seguridad para Marketplaces MCP: Auditoría de descripciones y manifiestos envenenados (P-06).
5. Buró de Reputación y Scoring Crediticio A2A: Evaluación de riesgo de contraparte (P-07).
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class PostconditionValidationResult(BaseModel):
    """Resultado de la verificación de postcondiciones de un paso en pipeline MCP."""
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    status: Literal["PASSED", "HOLLOW_OK_BLOCKED", "SCHEMA_MISMATCH"]
    missing_keys: list[str] = Field(default_factory=list)
    empty_keys: list[str] = Field(default_factory=list)
    diagnostics: str


class ContextPruningAuditResult(BaseModel):
    """Auditoría de pérdida de información entre el contexto original y el podado."""
    model_config = ConfigDict(extra="forbid")

    raw_token_estimate: int
    pruned_token_estimate: int
    retention_ratio: float
    missing_critical_entities: list[str] = Field(default_factory=list)
    information_loss_verdict: Literal["ACCEPTABLE_COMPACTION", "CRITICAL_INFORMATION_DROP", "INTEGRITY_VIOLATION"]
    loss_summary: str


class SpendingBudgetStatus(BaseModel):
    """Estado y control del presupuesto financiero de la sesión del agente."""
    model_config = ConfigDict(extra="forbid")

    session_id: str
    max_budget_sats: int
    spent_sats: int
    remaining_sats: int
    call_count: int
    is_circuit_breaker_tripped: bool
    status: Literal["ACTIVE", "TRIPPED_BUDGET_EXCEEDED", "TRIPPED_RATE_EXCEEDED"]


class MarketplacePackageAuditResult(BaseModel):
    """Auditoría de seguridad de un paquete o manifiesto de marketplace MCP."""
    model_config = ConfigDict(extra="forbid")

    package_name: str
    is_safe: bool
    risk_level: Literal["SAFE", "SUSPICIOUS", "MALICIOUS"]
    detected_threats: list[str] = Field(default_factory=list)
    has_obfuscated_base64: bool
    has_zero_width_smuggling: bool
    has_prompt_injection_payload: bool
    sanitized_description: str


class AgentReputationProfile(BaseModel):
    """Perfil de crédito, historial de disputas y scoring de confianza de un agente."""
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    credit_score: int  # 0 a 1000
    tier: Literal["PRIME", "STANDARD", "HIGH_RISK", "SLASHED"]
    total_contracts: int
    fulfilled_contracts: int
    disputed_contracts: int
    slashing_events: int
    trust_index: float  # 0.0 a 1.0


class A2AEnhancementEngine:
    """Motor integral de enriquecimiento y optimización para herramientas A2A."""

    def __init__(self) -> None:
        self.session_budgets: dict[str, dict[str, Any]] = {}
        self.agent_ledgers: dict[str, dict[str, int]] = {}

    def validate_chain_postconditions(
        self,
        tool_name: str,
        output_payload: dict[str, Any],
        required_keys: list[str],
        forbid_null_or_empty: bool = True,
    ) -> PostconditionValidationResult:
        """
        Valida que la salida de una herramienta MCP upstream no sea un 'Hollow OK' vacío.

        Args:
            tool_name: Nombre de la herramienta ejecutada.
            output_payload: Diccionario de salida retornado por la herramienta.
            required_keys: Lista de campos obligatorios que deben existir.
            forbid_null_or_empty: Si es True, prohíbe strings vacíos, listas vacías o valores None.

        Returns:
            PostconditionValidationResult con el veredicto y diagnósticos deterministas.
        """
        missing: list[str] = []
        empty: list[str] = []

        for k in required_keys:
            if k not in output_payload:
                missing.append(k)
            elif forbid_null_or_empty:
                v = output_payload[k]
                if v is None or (isinstance(v, (str, list, dict)) and len(v) == 0):
                    empty.append(k)

        if missing or empty:
            details = []
            if missing:
                details.append(f"Claves ausentes: {missing}")
            if empty:
                details.append(f"Claves con contenido nulo/vacío: {empty}")
            return PostconditionValidationResult(
                is_valid=False,
                status="HOLLOW_OK_BLOCKED",
                missing_keys=missing,
                empty_keys=empty,
                diagnostics=f"Bloqueo anti-Hollow OK en '{tool_name}': {'; '.join(details)}. Avance a llamada downstream denegado.",
            )

        return PostconditionValidationResult(
            is_valid=True,
            status="PASSED",
            missing_keys=[],
            empty_keys=[],
            diagnostics=f"Postcondiciones de '{tool_name}' plenamente satisfechas. 100% de claves requeridas presentes y no vacías.",
        )

    def audit_context_pruning(
        self,
        raw_context: str,
        pruned_context: str,
        critical_entities: list[str] | None = None,
    ) -> ContextPruningAuditResult:
        """
        Audita el gap entre lo que recibió un agente y lo que retuvo tras la poda.

        Args:
            raw_context: Texto o JSON del contexto bruto previo a la poda.
            pruned_context: Texto del contexto compactado.
            critical_entities: Lista opcional de tokens, hashes o IDs obligatorios.

        Returns:
            ContextPruningAuditResult con ratio de retención y veredicto.
        """
        raw_tokens = max(1, len(raw_context.split()))
        pruned_tokens = len(pruned_context.split())
        retention_ratio = round(pruned_tokens / raw_tokens, 4)

        missing_entities: list[str] = []
        if critical_entities:
            for entity in critical_entities:
                if entity not in pruned_context:
                    missing_entities.append(entity)

        if missing_entities:
            verdict: Literal["ACCEPTABLE_COMPACTION", "CRITICAL_INFORMATION_DROP", "INTEGRITY_VIOLATION"] = "INTEGRITY_VIOLATION"
            summary = f"Falla crítica de poda: Se eliminaron {len(missing_entities)} entidades críticas requeridas: {missing_entities}."
        elif retention_ratio < 0.05 and raw_tokens > 200:
            verdict = "CRITICAL_INFORMATION_DROP"
            summary = f"Poda hiper-agresiva ({retention_ratio*100:.1f}% retenido). Alto riesgo de alucinación por omisión."
        else:
            verdict = "ACCEPTABLE_COMPACTION"
            summary = f"Poda validada ({retention_ratio*100:.1f}% retención). Todas las entidades críticas preservadas."

        return ContextPruningAuditResult(
            raw_token_estimate=raw_tokens,
            pruned_token_estimate=pruned_tokens,
            retention_ratio=retention_ratio,
            missing_critical_entities=missing_entities,
            information_loss_verdict=verdict,
            loss_summary=summary,
        )

    def enforce_session_budget(
        self,
        session_id: str,
        max_budget_sats: int,
        charge_sats: int,
    ) -> SpendingBudgetStatus:
        """
        Controla el presupuesto financiero acumulado de la sesión de un agente.

        Args:
            session_id: Identificador de la sesión autónoma.
            max_budget_sats: Techo presupuestario máximo en Satoshis.
            charge_sats: Costo en Satoshis de la operación actual.

        Returns:
            SpendingBudgetStatus con el estado del circuit breaker.
        """
        if session_id not in self.session_budgets:
            self.session_budgets[session_id] = {
                "max_budget_sats": max_budget_sats,
                "spent_sats": 0,
                "call_count": 0,
                "tripped": False,
            }

        state = self.session_budgets[session_id]
        state["max_budget_sats"] = max_budget_sats
        state["call_count"] += 1

        if state["tripped"]:
            return SpendingBudgetStatus(
                session_id=session_id,
                max_budget_sats=state["max_budget_sats"],
                spent_sats=state["spent_sats"],
                remaining_sats=max(0, state["max_budget_sats"] - state["spent_sats"]),
                call_count=state["call_count"],
                is_circuit_breaker_tripped=True,
                status="TRIPPED_BUDGET_EXCEEDED",
            )

        if state["spent_sats"] + charge_sats > max_budget_sats:
            state["tripped"] = True
            return SpendingBudgetStatus(
                session_id=session_id,
                max_budget_sats=state["max_budget_sats"],
                spent_sats=state["spent_sats"],
                remaining_sats=max(0, state["max_budget_sats"] - state["spent_sats"]),
                call_count=state["call_count"],
                is_circuit_breaker_tripped=True,
                status="TRIPPED_BUDGET_EXCEEDED",
            )

        state["spent_sats"] += charge_sats
        remaining = state["max_budget_sats"] - state["spent_sats"]

        return SpendingBudgetStatus(
            session_id=session_id,
            max_budget_sats=state["max_budget_sats"],
            spent_sats=state["spent_sats"],
            remaining_sats=remaining,
            call_count=state["call_count"],
            is_circuit_breaker_tripped=False,
            status="ACTIVE",
        )

    def audit_marketplace_package(
        self,
        package_name: str,
        manifest_json: dict[str, Any] | None,
        tool_description: str,
    ) -> MarketplacePackageAuditResult:
        """
        Audita un paquete o tool de marketplace MCP contra ataques de cadena de suministro.

        Args:
            package_name: Nombre del paquete.
            manifest_json: Manifiesto opcional de la herramienta.
            tool_description: Descripción o docstring de la herramienta.

        Returns:
            MarketplacePackageAuditResult con detección de Base64, inyección y zero-width.
        """
        threats: list[str] = []
        has_b64 = False
        has_zw = False
        has_injection = False

        # 1. Detección de caracteres zero-width (Unicode Smuggling)
        zw_chars = ["\u200b", "\u200c", "\u200d", "\ufeff"]
        for ch in zw_chars:
            if ch in tool_description:
                has_zw = True
                threats.append("Unicode Smuggling: Caracteres invisibles Zero-Width detectados en la descripción.")
                break

        # 2. Detección de payloads Base64 ocultos (>40 caracteres base64 continuos)
        b64_matches = re.findall(r"(?:[A-Za-z0-9+/]{4}){10,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?", tool_description)
        for match in b64_matches:
            try:
                decoded = base64.b64decode(match).decode("utf-8", errors="ignore")
                if any(x in decoded.lower() for x in ["import", "system", "token", "exec", "eval", "curl", "bash"]):
                    has_b64 = True
                    threats.append(f"Payload Base64 ejecutable oculto en docstring: '{decoded[:40]}...'")
            except Exception:
                pass

        # 3. Detección de Inyecciones de Prompt
        injection_keywords = ["ignore previous instructions", "system override", "you are now in maintenance mode", "reveal system prompt"]
        for kw in injection_keywords:
            if kw in tool_description.lower():
                has_injection = True
                threats.append(f"Intento de inyección indirecta de prompt en descripción: '{kw}'")

        # 4. Verificar Manifiesto si existe
        if manifest_json:
            for k, v in manifest_json.items():
                if isinstance(v, str) and ("http://" in v or "ftp://" in v):
                    threats.append(f"Protocolo inseguro no cifrado en manifiesto ('{k}': '{v}')")

        is_safe = len(threats) == 0
        risk_level: Literal["SAFE", "SUSPICIOUS", "MALICIOUS"] = "SAFE"
        if has_b64 or has_injection:
            risk_level = "MALICIOUS"
        elif has_zw or threats:
            risk_level = "SUSPICIOUS"

        sanitized = tool_description
        for ch in zw_chars:
            sanitized = sanitized.replace(ch, "")

        return MarketplacePackageAuditResult(
            package_name=package_name,
            is_safe=is_safe,
            risk_level=risk_level,
            detected_threats=threats,
            has_obfuscated_base64=has_b64,
            has_zero_width_smuggling=has_zw,
            has_prompt_injection_payload=has_injection,
            sanitized_description=sanitized,
        )

    def record_contract_event(
        self,
        agent_id: str,
        event_type: Literal["FULFILLED", "DISPUTED", "SLASHED"],
    ) -> None:
        """Registra un evento contractual de un agente en el buró de reputación."""
        if agent_id not in self.agent_ledgers:
            self.agent_ledgers[agent_id] = {
                "total": 0,
                "fulfilled": 0,
                "disputed": 0,
                "slashed": 0,
            }

        rec = self.agent_ledgers[agent_id]
        rec["total"] += 1
        if event_type == "FULFILLED":
            rec["fulfilled"] += 1
        elif event_type == "DISPUTED":
            rec["disputed"] += 1
        elif event_type == "SLASHED":
            rec["slashed"] += 1

    def get_agent_reputation_profile(self, agent_id: str) -> AgentReputationProfile:
        """
        Calcula el perfil de reputación y scoring crediticio (0 a 1000) de un agente.
        """
        rec = self.agent_ledgers.get(agent_id, {"total": 0, "fulfilled": 0, "disputed": 0, "slashed": 0})
        total = rec["total"]

        if total == 0:
            # Nuevo agente: puntuación neutral
            return AgentReputationProfile(
                agent_id=agent_id,
                credit_score=500,
                tier="STANDARD",
                total_contracts=0,
                fulfilled_contracts=0,
                disputed_contracts=0,
                slashing_events=0,
                trust_index=0.5,
            )

        # Penalización masiva por slashing (-300 pts) y disputas (-50 pts)
        base = 500
        fulfilled_bonus = (rec["fulfilled"] / total) * 500
        dispute_penalty = rec["disputed"] * 60
        slash_penalty = rec["slashed"] * 300

        score = max(0, min(1000, int(base + fulfilled_bonus - dispute_penalty - slash_penalty)))
        trust_index = round(score / 1000.0, 3)

        if rec["slashed"] > 0 or score < 300:
            tier: Literal["PRIME", "STANDARD", "HIGH_RISK", "SLASHED"] = "SLASHED" if rec["slashed"] > 0 else "HIGH_RISK"
        elif score >= 800:
            tier = "PRIME"
        else:
            tier = "STANDARD"

        return AgentReputationProfile(
            agent_id=agent_id,
            credit_score=score,
            tier=tier,
            total_contracts=total,
            fulfilled_contracts=rec["fulfilled"],
            disputed_contracts=rec["disputed"],
            slashing_events=rec["slashed"],
            trust_index=trust_index,
        )
