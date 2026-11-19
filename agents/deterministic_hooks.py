"""
Motor de Hooks Deterministas y Circuit Breaker para Gobernanza Agéntica.
Previene inyecciones indirectas, accesos multi-tenant indebidos, desbordamiento
de costes y alucinaciones en citas documentales.
"""

from __future__ import annotations

import re
from typing import Any


class HookViolationError(Exception):
    """Excepción emitida cuando una regla de seguridad o gobernanza es violada."""


class DeterministicHookEngine:
    """
    Motor determinista de intercepción pre-tool y post-tool.
    Opera fuera del control del LLM, garantizando invariantes matemáticas.
    """

    def __init__(
        self,
        session_retrieved_ids: set[str] | None = None,
        max_cost_usd: float = 0.25,
        max_tool_calls: int = 15,
    ) -> None:
        self.retrieved_ids: set[str] = session_retrieved_ids or set()
        self.max_cost_usd: float = max_cost_usd
        self.max_tool_calls: int = max_tool_calls
        self.current_cost_usd: float = 0.0
        self.call_count: int = 0

    def record_retrieved_doc(self, doc_id: str) -> None:
        """Registra un ID de documento legítimamente devuelto por una herramienta."""
        if doc_id:
            self.retrieved_ids.add(str(doc_id).strip())

    def pre_tool_hook(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        tenant_id: str | None = None,
        estimated_cost_usd: float = 0.005,
    ) -> None:
        """
        Valida pre-condiciones obligatorias antes de ejecutar cualquier tool MCP:
        1. Aislamiento estricto de inquilino (Multi-tenant isolation).
        2. Circuit breaker por número de llamadas en la sesión.
        3. Circuit breaker de presupuesto financiero acumulado.
        4. Detección de prompt injection en parámetros de texto.
        """
        self.call_count += 1
        if self.call_count > self.max_tool_calls:
            raise HookViolationError(
                f"CIRCUIT_BREAKER_CALLS: Límite de {self.max_tool_calls} llamadas excedido."
            )

        if (self.current_cost_usd + estimated_cost_usd) > self.max_cost_usd:
            raise HookViolationError(
                f"CIRCUIT_BREAKER_COST: Presupuesto de ${self.max_cost_usd:.2f} USD excedido."
            )

        # Validación multi-tenant
        arg_tenant = arguments.get("tenant_id")
        if arg_tenant and tenant_id and arg_tenant != tenant_id:
            raise HookViolationError(
                f"SECURITY_BLOCK_TENANT: Acceso cruzado denegado ({arg_tenant} != {tenant_id})."
            )

        # Detección básica de evasión / prompt injection indirecto
        for k, v in arguments.items():
            if isinstance(v, str):
                lower_v = v.lower()
                if any(x in lower_v for x in ["ignore previous instructions", "system prompt override", "<script>"]):
                    raise HookViolationError(
                        f"SECURITY_BLOCK_INJECTION: Patrón malicioso detectado en argumento '{k}'."
                    )

        self.current_cost_usd += estimated_cost_usd

    def post_response_citation_hook(self, response_text: str) -> bool:
        """
        Extrae todas las referencias estructuradas [DOC:ID] en la respuesta del modelo
        y valida deterministamente que el 100% exista en los IDs recuperados en sesión.
        Erradica la alucinación de jurisprudencia o normas inexistentes.
        """
        pattern = r"\[DOC:([A-Za-z0-9_\-\.\/]+)\]"
        cited_ids = set(re.findall(pattern, response_text))

        if not cited_ids:
            return True

        hallucinated = cited_ids - self.retrieved_ids
        if hallucinated:
            raise HookViolationError(
                f"HALLUCINATION_BLOCK: Citas documentales no recuperadas en sesión: {sorted(hallucinated)}"
            )

        return True
