import json
import os
import sys
from pathlib import Path
from typing import Any

from a2a_court_arbitrator import A2ACourtArbitrator
from a2a_oracle_service import A2AOracleService
from credit_redemption_pool import CreditRedemptionPool
from crypto_audit_log import MultiCaMeLLedger
from deterministic_hooks import DeterministicHookEngine, HookViolationError
from escrow_manager import EscrowManager
from grammar_compiler_service import GrammarCompilerService
from l402_gateway import L402Gateway
from legal_procedural_tools import (
    NormativeValidityInput,
    ProceduralDeadlineInput,
    compute_procedural_deadline,
    verify_normative_validity,
)
from market_intelligence_miner import MarketIntelligenceMiner
from monetization_models import ServiceRequest
from peruvian_procurement_radar import (
    ProcurementMatchInput,
    match_peruvian_procurement,
)
from sandbox_compute_service import SandboxComputeService, SandboxExecutionRequest
from skill_security_certifier import SkillSecurityCertifier
from sunat_cpe_auditor import CpeAuditInput, audit_sunat_cpe_xml
from token_pricing_engine import TokenPricingEngine
from vba_macro_forensics import (
    MacroForensicsInput,
    audit_vba_macro_code,
)


class MoltbookMonetizationMCPServer:
    """
    Servidor MCP stdio para Monetización, Cómputo, Arbitraje e Inteligencia A2A en Moltbook.
    Expone herramientas formales para interactuar comercialmente con el ecosistema.
    """

    def __init__(self, ledger_file: Path | None = None):
        if ledger_file is None:
            env_ledger = os.getenv("A2A_LEDGER_PATH")
            if env_ledger:
                ledger_file = Path(env_ledger)
            elif Path("/opt/a2a-defense-system/data").exists():
                ledger_file = Path("/opt/a2a-defense-system/data/a2a_audit_ledger.jsonl")
            elif Path("./data").exists():
                ledger_file = Path("./data/a2a_audit_ledger.jsonl")

        self.ledger = MultiCaMeLLedger(ledger_file=ledger_file)
        self.oracle = A2AOracleService()
        self.miner = MarketIntelligenceMiner()
        self.pricing = TokenPricingEngine()
        self.escrow = EscrowManager(ledger=self.ledger)
        self.court = A2ACourtArbitrator(escrow_manager=self.escrow, ledger=self.ledger)
        self.compiler = GrammarCompilerService()
        self.certifier = SkillSecurityCertifier()
        self.l402_gateway = L402Gateway()
        self.redemption_pool = CreditRedemptionPool()
        self.sandbox = SandboxComputeService()
        self.hook_engine = DeterministicHookEngine()

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "get_alpha_intelligence_feed",
                "description": "Obtiene el feed consolidado de inteligencia B2B, alertas 0-day y oportunidades comerciales en Moltbook.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "category_filter": {
                            "type": "string",
                            "enum": ["all", "architecture_trend", "zero_day_alert", "unmet_demand", "monetization_signal"],
                            "default": "all",
                        }
                    },
                },
            },
            {
                "name": "request_epistemic_audit",
                "description": "Ejecuta una auditoría de verdad factual pagada mediante token de micropago.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "service_request_json": {
                            "type": "string",
                            "description": "JSON serializado del ServiceRequest (incluyendo el PaymentToken).",
                        }
                    },
                    "required": ["service_request_json"],
                },
            },
            {
                "name": "calculate_service_quote",
                "description": "Calcula la cotización formal en créditos según complejidad de cómputo, tokens y riesgo.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "service_type": {"type": "string"},
                        "estimated_compute_ms": {"type": "integer", "default": 50},
                        "estimated_tokens": {"type": "integer", "default": 500},
                        "adversarial_risk_score": {"type": "number", "default": 0.05},
                    },
                    "required": ["service_type"],
                },
            },
            {
                "name": "create_escrow_deposit",
                "description": "Crea un contrato de custodia colateralizado con bloqueo de fondos y colateral del proveedor.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "client_id": {"type": "string"},
                        "provider_id": {"type": "string"},
                        "service_fee": {"type": "integer"},
                        "provider_stake": {"type": "integer"},
                    },
                    "required": ["client_id", "provider_id", "service_fee", "provider_stake"],
                },
            },
            {
                "name": "arbitrate_dispute",
                "description": "Resuelve disputas de contratos de custodia auditando la cadena Multi-CaMeL (Why-Trail).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "contract_id": {"type": "string"},
                        "claimed_evidence_hash": {"type": "string"},
                    },
                    "required": ["contract_id"],
                },
            },
            {
                "name": "compile_gbnf_grammar",
                "description": "Compila un esquema de campos en una gramática GBNF estricta para decodificación sin fallos.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "schema_spec": {
                            "type": "object",
                            "description": "Diccionario clave-valor con nombres de campos y tipos soportados.",
                        }
                    },
                    "required": ["schema_spec"],
                },
            },
            {
                "name": "certify_skill_safety",
                "description": "Audita estáticamente el código Python de un skill contra troyanos DY-Skill y llamadas a shell.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code_str": {"type": "string"},
                        "skill_name": {"type": "string", "default": "unnamed_skill"},
                    },
                    "required": ["code_str"],
                },
            },
            {
                "name": "request_l402_challenge",
                "description": "Genera un desafío HTTP 402 con Macaroon criptográfico y factura Lightning Bolt11 para acceso pay-per-call.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "amount_sats": {"type": "integer"},
                        "client_id": {"type": "string"},
                        "ttl_seconds": {"type": "integer", "default": 1800},
                    },
                    "required": ["service", "amount_sats", "client_id"],
                },
            },
            {
                "name": "verify_l402_payment",
                "description": "Valida la cabecera 'Authorization: L402 <macaroon>:<preimage>' verificando la prueba de pago Lightning.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "authorization_header": {"type": "string"},
                    },
                    "required": ["authorization_header"],
                },
            },
            {
                "name": "redeem_credits_for_sats",
                "description": "Convierte créditos de Moltbook acumulados a Satoshis en Lightning Network (1 crédito = 25 sats).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "credits": {"type": "integer"},
                        "destination_bolt11": {"type": "string"},
                    },
                    "required": ["agent_id", "credits", "destination_bolt11"],
                },
            },
            {
                "name": "execute_sandboxed_computation",
                "description": "Ejecuta un script de código Python en un runtime aislado determinista con límites RLIMIT de memoria y CPU.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "timeout_seconds": {"type": "integer", "default": 2},
                        "max_memory_mb": {"type": "integer", "default": 64},
                    },
                    "required": ["code"],
                },
            },
            {
                "name": "compute_procedural_deadline",
                "description": "Cálculo aritmético determinista de plazos procesales judiciales y administrativos (días hábiles o calendario, descontando feriados oficiales de Perú).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "fecha_inicio": {"type": "string", "description": "Fecha inicial (YYYY-MM-DD)"},
                        "dias_plazo": {"type": "integer", "description": "Cantidad de días del plazo legal"},
                        "tipo_dias": {
                            "type": "string",
                            "enum": ["HABILES_JUDICIALES", "CALENDARIO"],
                            "default": "HABILES_JUDICIALES",
                        },
                    },
                    "required": ["fecha_inicio", "dias_plazo"],
                },
            },
            {
                "name": "verify_normative_validity",
                "description": "Verificación determinista en grafo legal de vigencia, modificación o derogación de artículos normativos (Código Tributario, Civil, LPAG).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "codigo_norma": {"type": "string", "description": "Código de la norma (ej. CODIGO_TRIBUTARIO, CODIGO_CIVIL, LEY_27444)"},
                        "articulo": {"type": "string", "description": "Número de artículo a verificar (ej. 43, 44, 1989, 207)"},
                        "fecha_corte": {"type": "string", "description": "Fecha de corte opcional (YYYY-MM-DD)"},
                    },
                    "required": ["codigo_norma", "articulo"],
                },
            },
            {
                "name": "audit_sunat_cpe_xml",
                "description": "Auditoría forense determinista de facturas y comprobantes electrónicos XML UBL 2.1 SUNAT Perú (Módulo 11 de RUC, cuadre del 18% IGV y validación de firma).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "xml_content": {"type": "string", "description": "Contenido XML del comprobante UBL 2.1"},
                        "strict_tax_check": {"type": "boolean", "default": True, "description": "Exigir cuadre aritmético estricto de IGV al centavo"},
                    },
                    "required": ["xml_content"],
                },
            },
            {
                "name": "audit_excel_macro_forensics",
                "description": "Auditoría forense estática de código VBA de macros Excel y desofuscación de identificadores de confusión visual (WinAPI, Shell, credenciales y URLs).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "vba_code": {"type": "string", "description": "Código fuente VBA para auditar e inspeccionar"},
                        "auto_deobfuscate": {"type": "boolean", "default": True, "description": "Normalizar identificadores ofuscados confusos (O/0/l/1)"},
                    },
                    "required": ["vba_code"],
                },
            },
            {
                "name": "match_peruvian_procurement",
                "description": "Radar y clasificador de requerimientos técnicos y convocatorias SEACE/OSCE de software, IA y digitalización en el Estado peruano con códigos CUBSO sugeridos.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "requirement_text": {"type": "string", "description": "Texto del requerimiento, TDR o título de licitación en Perú"},
                    },
                    "required": ["requirement_text"],
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any], tenant_id: str | None = None) -> dict[str, Any]:
        # 1. Pre-Execution Hook Determinista
        try:
            self.hook_engine.pre_tool_hook(name, arguments, tenant_id=tenant_id)
        except (HookViolationError, ValueError, KeyError) as exc:
            return {"error": f"HOOK_VIOLATION: {exc!s}", "status": "BLOCKED"}

        result = self._dispatch_tool(name, arguments)

        # 2. Registrar doc_id si se recupera un artefacto auditable
        if isinstance(result, dict) and "doc_id" in result:
            self.hook_engine.record_retrieved_doc(result["doc_id"])

        actor = (
            arguments.get("client_id")
            or arguments.get("agent_id")
            or arguments.get("caller_agent_id")
            or "anonymous_agent"
        )
        status = "ERROR" if isinstance(result, dict) and "error" in result else "SUCCESS"
        self.ledger.record_event(
            event_type=f"TOOL_CALL:{name}",
            payload_data={
                "tool_name": name,
                "arguments": arguments,
                "status": status,
            },
            actor_agent_id=str(actor),
            metadata={"source": "mcp_server"},
        )
        return result

    def _dispatch_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "calculate_service_quote":
            q = self.pricing.calculate_price(
                service_type=arguments["service_type"],
                estimated_compute_ms=arguments.get("estimated_compute_ms", 50),
                estimated_tokens=arguments.get("estimated_tokens", 500),
                adversarial_risk_score=arguments.get("adversarial_risk_score", 0.05),
            )
            return q.model_dump(mode="json")

        if name == "create_escrow_deposit":
            c = self.escrow.create_contract(
                client_id=arguments["client_id"],
                provider_id=arguments["provider_id"],
                service_fee=arguments["service_fee"],
                provider_stake=arguments["provider_stake"],
            )
            return c.model_dump(mode="json")

        if name == "arbitrate_dispute":
            ruling = self.court.adjudicate_dispute(
                contract_id=arguments["contract_id"],
                claimed_evidence_hash=arguments.get("claimed_evidence_hash"),
            )
            return ruling.model_dump(mode="json")

        if name == "compile_gbnf_grammar":
            grammar = self.compiler.compile_schema_to_gbnf(arguments["schema_spec"])
            return {"gbnf_grammar": grammar}

        if name == "certify_skill_safety":
            rep = self.certifier.certify_python_code(
                code_str=arguments["code_str"],
                skill_name=arguments.get("skill_name", "unnamed_skill"),
            )
            return rep.model_dump(mode="json")

        if name == "request_epistemic_audit":
            try:
                raw_req = json.loads(arguments["service_request_json"])
                req_obj = ServiceRequest.model_validate(raw_req)
                resp = self.oracle.process_service_request(req_obj)
                return resp.model_dump(mode="json")
            except (json.JSONDecodeError, ValueError) as exc:
                return {"status": "error", "credits_charged": 0, "error_detail": str(exc)}

        if name == "get_alpha_intelligence_feed":
            mock_posts = [
                {"content": "La optimización con FlashInfer y gramáticas GBNF reduce la latencia de decodificación un 45%."},
                {"content": "Alerta crítica: nuevo vector de indirect prompt injection permite exfiltración de nonces de sesión."},
                {"content": "Necesito un agente que audite dependencias de skills y valide contratos Pydantic con pago garantizado."},
            ]
            feed = self.miner.mine_posts(mock_posts)
            cat = arguments.get("category_filter", "all")
            if cat != "all":
                feed.actionable_alphas = [a for a in feed.actionable_alphas if a.category == cat]
            return feed.model_dump(mode="json")

        if name == "request_l402_challenge":
            challenge, preimage = self.l402_gateway.create_challenge(
                service=arguments["service"],
                amount_sats=arguments["amount_sats"],
                client_id=arguments["client_id"],
                ttl_seconds=arguments.get("ttl_seconds", 1800),
            )
            res = challenge.model_dump(mode="json")
            res["simulated_preimage_hex"] = preimage.hex()
            return res

        if name == "verify_l402_payment":
            verdict = self.l402_gateway.verify_authorization(arguments["authorization_header"])
            return verdict.model_dump(mode="json")

        if name == "redeem_credits_for_sats":
            try:
                receipt = self.redemption_pool.execute_redemption(
                    agent_id=arguments["agent_id"],
                    credits=arguments["credits"],
                    destination_bolt11=arguments["destination_bolt11"],
                )
                return receipt.model_dump(mode="json")
            except ValueError as exc:
                return {"status": "FAILED", "error": str(exc)}

        if name == "execute_sandboxed_computation":
            req = SandboxExecutionRequest(
                code=arguments["code"],
                timeout_seconds=arguments.get("timeout_seconds", 2),
                max_memory_mb=arguments.get("max_memory_mb", 64),
            )
            res = self.sandbox.run_isolated(req)
            return res.model_dump(mode="json")

        if name == "compute_procedural_deadline":
            try:
                payload = ProceduralDeadlineInput.model_validate(arguments)
                res_deadline = compute_procedural_deadline(payload)
                return res_deadline.model_dump(mode="json")
            except (ValueError, KeyError, TypeError) as exc:
                return {"error": f"INVALID_ARGUMENTS: {exc!s}"}

        if name == "verify_normative_validity":
            try:
                payload_norm = NormativeValidityInput.model_validate(arguments)
                res_norm = verify_normative_validity(payload_norm)
                return res_norm.model_dump(mode="json")
            except (ValueError, KeyError, TypeError) as exc:
                return {"error": f"INVALID_ARGUMENTS: {exc!s}"}

        if name == "audit_sunat_cpe_xml":
            try:
                payload_cpe = CpeAuditInput.model_validate(arguments)
                res_cpe = audit_sunat_cpe_xml(payload_cpe)
                return res_cpe.model_dump(mode="json")
            except (ValueError, KeyError, TypeError) as exc:
                return {"error": f"INVALID_ARGUMENTS: {exc!s}"}

        if name == "audit_excel_macro_forensics":
            try:
                payload_macro = MacroForensicsInput.model_validate(arguments)
                res_macro = audit_vba_macro_code(payload_macro)
                return res_macro.model_dump(mode="json")
            except (ValueError, KeyError, TypeError) as exc:
                return {"error": f"INVALID_ARGUMENTS: {exc!s}"}

        if name == "match_peruvian_procurement":
            try:
                payload_proc = ProcurementMatchInput.model_validate(arguments)
                res_proc = match_peruvian_procurement(payload_proc)
                return res_proc.model_dump(mode="json")
            except (ValueError, KeyError, TypeError) as exc:
                return {"error": f"INVALID_ARGUMENTS: {exc!s}"}

        return {"error": f"Herramienta desconocida: {name}"}


def run_stdio_server(server: MoltbookMonetizationMCPServer) -> None:
    """Ejecuta el servidor MCP sobre stdin/stdout con protocolo JSON-RPC 2.0 estándar."""
    print("MoltbookMonetizationMCPServer corriendo en modo stdio (16 herramientas)...", file=sys.stderr)
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc!s}"},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                    "serverInfo": {
                        "name": "a2a-defense-monetization-gateway",
                        "version": "1.0.0",
                    },
                },
            }
        elif method in ("notifications/initialized", "initialized"):
            if req_id is not None:
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
            else:
                continue
        elif method in ("tools/list", "list_tools"):
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": server.list_tools(),
                },
            }
        elif method in ("tools/call", "call_tool"):
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            if not tool_name:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "Missing 'name' in tool call parameters."},
                }
            else:
                res = server.call_tool(name=tool_name, arguments=tool_args)
                is_err = "error" in res and str(res.get("error", "")).startswith("Herramienta desconocida")
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(res, ensure_ascii=False)}
                        ],
                        "isError": is_err,
                    },
                }
        else:
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def main():
    server = MoltbookMonetizationMCPServer()
    if len(sys.argv) > 1 and sys.argv[1] == "--list-tools":
        print(json.dumps(server.list_tools(), indent=2))
        return

    run_stdio_server(server)


if __name__ == "__main__":
    main()
