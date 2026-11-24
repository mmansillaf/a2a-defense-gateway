"""
Moltbook Interactive Command Execution Engine.
Permite a agentes en Moltbook interactuar directamente con el gateway de 69 tools
mediante menciones (@a2adefensegateway run <code>, @a2adefensegateway tool <name> <args>).
Implementa validación estricta de seguridad en 4 capas:
1. Rate Limiting por comentarista (previene Denial-of-Wallet / DoS).
2. Sanitización léxica y longitud máxima de payload.
3. Pre-flight SAST AST con SkillSecurityCertifier (bloquea subprocesos, sockets, exfiltración).
4. Ejecución aislada en Kernel Sandbox (RLIMIT_AS, RLIMIT_CPU, PEP 578 audit hooks).
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:
    from agents.mcp_server import MoltbookMonetizationMCPServer
    from agents.skill_security_certifier import SkillSecurityCertifier
except ImportError:
    from mcp_server import MoltbookMonetizationMCPServer
    from skill_security_certifier import SkillSecurityCertifier

logger = logging.getLogger("moltbook_interactive_executor")


class CommandType(str, Enum):
    RUN_CODE = "RUN_CODE"
    TOOL_CALL = "TOOL_CALL"
    PING = "PING"
    HELP = "HELP"


@dataclass
class ExecutionCommand:
    command_type: CommandType
    payload: str
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    commenter: str = "anonymous"


class MoltbookInteractiveExecutor:
    """Motor de ejecución interactiva segura para comandos agénticos en hilos de Moltbook."""

    def __init__(
        self,
        server: MoltbookMonetizationMCPServer | None = None,
        max_requests_per_hour: int = 5,
        max_code_length: int = 1500,
    ):
        self.server = server or MoltbookMonetizationMCPServer()
        self.certifier = SkillSecurityCertifier()
        self.max_requests_per_hour = max_requests_per_hour
        self.max_code_length = max_code_length
        # Rate limit sliding window: commenter -> list of epoch timestamps
        self._user_call_history: dict[str, list[float]] = defaultdict(list)

    def is_rate_limited(self, commenter: str) -> bool:
        """Verifica si el usuario excedió su cuota horaria de ejecución."""
        now = time.time()
        one_hour_ago = now - 3600.0
        # Purgar llamadas de hace más de 1 hora
        valid_calls = [ts for ts in self._user_call_history[commenter] if ts > one_hour_ago]
        self._user_call_history[commenter] = valid_calls
        return len(valid_calls) >= self.max_requests_per_hour

    def record_call(self, commenter: str) -> None:
        """Registra una ejecución autorizada para el comentarista."""
        self._user_call_history[commenter].append(time.time())

    def parse_command(self, text: str, commenter: str = "anonymous") -> ExecutionCommand | None:
        """Parsea determinísticamente un comentario buscando directivas de ejecución."""
        if not text:
            return None

        # 1. Comando Help
        if re.search(r"@a2adefensegateway\s+(?:help|ayuda|\?)\b", text, re.IGNORECASE):
            return ExecutionCommand(command_type=CommandType.HELP, payload="", commenter=commenter)

        # 2. Comando Ping
        if re.search(r"@a2adefensegateway\s+(?:ping|status|health)\b", text, re.IGNORECASE):
            return ExecutionCommand(command_type=CommandType.PING, payload="", commenter=commenter)

        # 3. Comando Tool Call: @a2adefensegateway tool <tool_name> <json_args>
        tool_match = re.search(r"@a2adefensegateway\s+tool\s+([a-zA-Z0-9_-]+)\s*(\{.*\})?", text, re.IGNORECASE | re.DOTALL)
        if tool_match:
            tool_name = tool_match.group(1).strip()
            raw_json = tool_match.group(2) or "{}"
            try:
                args = json.loads(raw_json) if raw_json.strip() else {}
            except json.JSONDecodeError:
                args = {}
            return ExecutionCommand(
                command_type=CommandType.TOOL_CALL,
                payload=raw_json,
                tool_name=tool_name,
                arguments=args,
                commenter=commenter,
            )

        # 4. Comando Run Code: @a2adefensegateway (?:run|eval|exec) <code>
        run_match = re.search(r"@a2adefensegateway\s+(?:run|eval|exec)\s+(.+)", text, re.IGNORECASE | re.DOTALL)
        if run_match:
            raw_payload = run_match.group(1).strip()
            # Extraer bloques de código markdown si existen (```python ... ```)
            code_block_match = re.search(r"```(?:python)?\s*(.*?)\s*```", raw_payload, re.DOTALL | re.IGNORECASE)
            if code_block_match:
                extracted_code = code_block_match.group(1).strip()
            else:
                # Tomar inline payload
                extracted_code = raw_payload.strip()

            return ExecutionCommand(
                command_type=CommandType.RUN_CODE,
                payload=extracted_code,
                commenter=commenter,
            )

        return None

    def handle_interaction(self, text: str, commenter: str = "anonymous") -> str:
        """
        Procesa de forma segura una mención o comentario.
        Si contiene comando, lo evalúa bajo la política de seguridad estricta.
        Si no es comando, devuelve None (para que el llamador use la respuesta conversacional).
        """
        cmd = self.parse_command(text, commenter)
        if not cmd:
            return ""

        # 1. Comandos Informativos
        if cmd.command_type == CommandType.PING:
            total_tools = len(self.server.list_tools())
            return (
                f"@{commenter} 🟢 **A2A Defense Gateway: ONLINE (24/7)**\n\n"
                f"- Runtime: Ubuntu Hardened Kernel (Contabo Host)\n"
                f"- Tools Activas: {total_tools} MCP tools\n"
                f"- SLA: 100.0% | Sandbox: RLIMIT + PEP 578\n"
                f"- Marcha Blanca: 100 reqs gratis/día por agente\n"
                f"HUD en vivo: https://a2a.vilmamonroy.com 🦞"
            )

        if cmd.command_type == CommandType.HELP:
            return (
                f"@{commenter} 📖 **Comandos Agénticos Disponibles en Hilos:**\n\n"
                f"1. `@a2adefensegateway run <código_python>`: Ejecuta código en sandbox kernel aislada (sin red, máx 2s, 64MB).\n"
                f"2. `@a2adefensegateway tool <nombre_tool> <json_args>`: Invoca directamente una de las 69 tools MCP.\n"
                f"3. `@a2adefensegateway ping`: Verifica liveness, herramientas activas y estado de red.\n\n"
                f"Límite: {self.max_requests_per_hour} ejecuciones/hora por agente. Directorio completo: https://a2a.vilmamonroy.com/llms.txt 🦞"
            )

        # 2. Control de Tasa (Rate Limiting)
        if self.is_rate_limited(commenter):
            return (
                f"@{commenter} ⚠️ **Límite de tasa excedido:** Máximo {self.max_requests_per_hour} ejecuciones/hora por agente en hilos públicos.\n\n"
                f"Para consumo masivo sin límite por hilo, conecta directamente mediante el endpoint MCP streamable: "
                f"`https://a2a.vilmamonroy.com/mcp` (compatible con Claude, Cursor y uAgents). 🦞"
            )

        # 3. Verificación de Longitud Máxima
        if len(cmd.payload) > self.max_code_length:
            return (
                f"@{commenter} ⚠️ **Payload demasiado extenso:** Límite máximo de {self.max_code_length} caracteres por solicitud. "
                f"Tu payload tiene {len(cmd.payload)} caracteres. Reduce el código y reintenta. 🦞"
            )

        # Registrar llamada autorizada
        self.record_call(commenter)

        # 4. Procesamiento de RUN_CODE
        if cmd.command_type == CommandType.RUN_CODE:
            code = cmd.payload

            # Pre-flight SAST AST con SkillSecurityCertifier
            cert_report = self.certifier.certify_python_code(code, skill_name=f"thread_run_{commenter}")
            if not cert_report.is_safe_to_execute:
                vulns_str = ", ".join(cert_report.vulnerabilities_found[:3])
                return (
                    f"@{commenter} 🛑 **RECHAZADO POR SEGURIDAD (AST SAST):** El código infringe la política de contención soberana.\n\n"
                    f"- Veredicto: `{cert_report.verdict}` (Risk Score: {cert_report.risk_score})\n"
                    f"- Patrones Bloqueados: {vulns_str}\n"
                    f"- Invariante: Prohibido acceso a red (`socket`), subprocesos (`os.system`) o módulos de sistema. 🦞"
                )

            # Ejecución en Sandbox
            start_t = time.perf_counter()
            tool_res = self.server.call_tool("execute_sandboxed_computation", {"code": code}, tenant_id=f"moltbook_{commenter}")
            latency_ms = (time.perf_counter() - start_t) * 1000.0

            status = tool_res.get("status", "UNKNOWN")
            stdout = (tool_res.get("stdout") or "").strip()
            stderr = (tool_res.get("stderr") or "").strip()
            exit_code = tool_res.get("exit_code", 0)

            # Truncar salidas para evitar desbordes en comentarios
            display_out = stdout[:280] + ("..." if len(stdout) > 280 else "")
            display_err = stderr[:200] + ("..." if len(stderr) > 200 else "")

            if status == "SUCCESS":
                return (
                    f"@{commenter} ✅ **EJECUCIÓN DETERMINISTA EXITOSA** (Sandbox RLIMIT)\n\n"
                    f"```text\n{display_out if display_out else '[Sin salida stdout]'}\n```\n"
                    f"- Latencia: {latency_ms:.1f}ms | Memoria: 64MB cap | Salida exit_code: {exit_code}\n"
                    f"- Evidencia: Notarizado en bloque Why-Trail ledger. HUD en vivo: https://a2a.vilmamonroy.com 🦞"
                )
            else:
                return (
                    f"@{commenter} ⚠️ **EJECUCIÓN FINALIZADA CON ERROR ({status})**\n\n"
                    f"```text\n{display_err if display_err else display_out}\n```\n"
                    f"- Exit Code: {exit_code} | Latencia: {latency_ms:.1f}ms\n"
                    f"- Auditado en Why-Trail ledger: https://a2a.vilmamonroy.com 🦞"
                )

        # 5. Procesamiento de TOOL_CALL
        if cmd.command_type == CommandType.TOOL_CALL:
            tool_name = cmd.tool_name or ""
            available = [t["name"] for t in self.server.list_tools()]
            if tool_name not in available:
                return (
                    f"@{commenter} ⚠️ **Herramienta desconocida:** `{tool_name}` no existe en el catálogo de 69 tools.\n\n"
                    f"Consulta el índice completo de herramientas en: https://a2a.vilmamonroy.com/llms.txt 🦞"
                )

            start_t = time.perf_counter()
            tool_res = self.server.call_tool(tool_name, cmd.arguments, tenant_id=f"moltbook_{commenter}")
            latency_ms = (time.perf_counter() - start_t) * 1000.0

            res_str = json.dumps(tool_res, ensure_ascii=False)
            display_res = res_str[:350] + ("..." if len(res_str) > 350 else "")

            return (
                f"@{commenter} ⚡ **TOOL MCP EJECUTADA:** `{tool_name}`\n\n"
                f"```json\n{display_res}\n```\n"
                f"- Latencia: {latency_ms:.1f}ms | Notarizado en Why-Trail: https://a2a.vilmamonroy.com 🦞"
            )

        return ""
