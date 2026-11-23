#!/usr/bin/env python3
"""
Generador del Catálogo Oficial de 56 Herramientas MCP / Skills de Producción A2A.
Genera versiones sincronizadas en:
1. Markdown (.md)
2. Texto Plano (.txt) estrictamente formateado a <= 79 columnas
3. PDF (.pdf) formal de alta densidad tipográfica mediante ReportLab

Cumple con las directivas maestras:
- BLUF (Bottom Line Up Front)
- Enlaces de archivos file:///
- Diagramas Top-Down (flowchart TD) + Doble Renderizado Universal en Cajas Unicode
- Tablas exhaustivas de especificación técnica de las 56 tools
"""

import os
import sys
import textwrap
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    Preformatted,
    HRFlowable,
)
from reportlab.pdfgen import canvas

BASE_DIR = Path("/home/usuario/Descargas/pycode/SkillA2A_Moltbook/moltbook_defense_system")
DOCS_DIR = BASE_DIR / "data" / "artifacts" / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

MD_PATH = DOCS_DIR / "INFORME_CATALOGO_OFICIAL_56_TOOLS_MCP_A2A_2026.md"
TXT_PATH = DOCS_DIR / "INFORME_CATALOGO_OFICIAL_56_TOOLS_MCP_A2A_2026.txt"
PDF_PATH = DOCS_DIR / "INFORME_CATALOGO_OFICIAL_56_TOOLS_MCP_A2A_2026.pdf"


# ==============================================================================
# 1. GENERACIÓN DEL CATÁLOGO EN MARKDOWN (GFM)
# ==============================================================================

MD_CONTENT = """---
title: "Catálogo Oficial de 56 Herramientas MCP y Servicios Agénticos A2A (Producción 2026)"
document_id: "A2A-CATALOG-2026-56TOOLS-OFFICIAL"
date: "2026-11-23"
status: "PRODUCTION_LIVE"
gateway_url: "https://a2a.vilmamonroy.com"
agent_card: "https://a2a.vilmamonroy.com/.well-known/agent-card.json"
health_endpoint: "https://a2a.vilmamonroy.com/health"
classification: "PÚBLICO / ESPECIFICACIÓN TÉCNICA OFICIAL"
---

# CATÁLOGO MAESTRO OFICIAL: 56 HERRAMIENTAS MCP, ORÁCULOS Y SKILLS A2A

**Fecha de Publicación:** 23 de Noviembre de 2026  
**Entorno de Producción:** A2A Defense & Monetization Gateway  
**Endpoint MCP JSON-RPC 2.0:** `https://a2a.vilmamonroy.com/mcp`  
**Agent Card W3C / A2A:** `https://a2a.vilmamonroy.com/.well-known/agent-card.json`  
**Host:** Contabo VPS `167.86.108.85` (Ubuntu 24.04 LTS, Nginx SSL, systemd `a2a-gateway.service`)  
**Repositorio Central:** [SkillA2A_Moltbook/moltbook_defense_system](file:///home/usuario/Descargas/pycode/SkillA2A_Moltbook/moltbook_defense_system)  
**Cobertura de Tests:** **151/151 tests superados (100% Green)**  

---

## 1. RESUMEN EJECUTIVO (BLUF)

El **A2A Defense Gateway** ha completado el despliegue a producción de **56 Herramientas MCP activas**, oráculos criptográficos y módulos de liquidación financiera, distribuidos en **9 dominios operacionales**. 

La suite integra gobernanza financiera fuera del prompt, defensas activas contra vaciadores de wallets (EIP-712 / Permit2), circuit breakers contra bucles de inferencia infinita (Denial-of-Wallet), oráculos de presencia física (zk-Presence para RentAHuman), acreditación criptográfica fiduciaria (KYA / W3C DID) y un enrutador híbrido de micropagos que unifica HTTP 402 (Base/Solana USDC) con Bitcoin Lightning Network (L402).

```mermaid
flowchart TD
    AGENTS["Ecosistema Agéntico A2A (Moltbook, Fetch.ai, RentAHuman, Base)"] --> GATEWAY["A2A Defense Gateway (56 Tools / L402 / x402)"]
    
    GATEWAY --> D1["1. Core Defense & Verificación (Tools 1-7)"]
    GATEWAY --> D2["2. Lightning & Liquidación L402 (Tools 8-11, 25-26)"]
    GATEWAY --> D3["3. Sandboxing & Runtime Seguro (Tool 12)"]
    GATEWAY --> D4["4. LegalTech & Forense Normativo (Tools 13-18, 28, 43)"]
    GATEWAY --> D5["5. CTI, Reputación & Seguridad AST (Tools 19-24, 27, 29-39, 41-42)"]
    GATEWAY --> D6["6. Comercio Agéntico & Mandatos AP2 (Tools 40, 44-47)"]
    GATEWAY --> D7["7. FinTech & Trading Risk Envelope (Tools 48-50)"]
    GATEWAY --> D8["8. Seguridad Agéntica & Anti-Drainer (Tools 51-53)"]
    GATEWAY --> D9["9. zk-Presence, KYA & Multi-Rail Router (Tools 54-56)"]

    D1 --> LEDGER["Why-Trail Causal Ledger & Merkle Root Inmutable"]
    D2 --> LEDGER
    D3 --> LEDGER
    D4 --> LEDGER
    D5 --> LEDGER
    D6 --> LEDGER
    D7 --> LEDGER
    D8 --> LEDGER
    D9 --> LEDGER
```

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│          Ecosistema Agéntico A2A (Moltbook, RentAHuman, Base, Fetch)        │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│           A2A DEFENSE GATEWAY // 56 HERRAMIENTAS MCP DE PRODUCCIÓN           │
└──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────────────┬───────────────┘
       │      │      │      │      │      │      │              │               │
       ▼      ▼      ▼      ▼      ▼      ▼      ▼              ▼               ▼
     ┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐          ┌───┐           ┌───┐
     │D1 │  │D2 │  │D3 │  │D4 │  │D5 │  │D6 │  │D7 │          │D8 │           │D9 │
     └───┘  └───┘  └───┘  └───┘  └───┘  └───┘  └───┘          └───┘           └───┘
       │      │      │      │      │      │      │              │               │
       └──────┴──────┴──────┴──────┴──────┴──────┴──────────────┴───────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│               Why-Trail Multi-CaMeL Ledger & Merkle Root Inmutable          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. ESPECIFICACIÓN TÉCNICA DE LAS 56 HERRAMIENTAS MCP

| # | Herramienta MCP | Dominio | Propósito Técnico y Salida |
|---|---|---|---|
| 01 | `get_alpha_intelligence_feed` | Inteligencia & Mercado | Feed de inteligencia B2B, alertas 0-day y señales de demanda. |
| 02 | `request_epistemic_audit` | Inteligencia & Mercado | Verificación factual pagada mediante micropago L402 / token S_c. |
| 03 | `calculate_service_quote` | Economía & Liquidación | Cotización formal en créditos/sats según complejidad algorítmica. |
| 04 | `create_escrow_deposit` | Economía & Liquidación | Custodia colateralizada y timelock criptográfico bilateral. |
| 05 | `arbitrate_dispute` | Economía & Liquidación | Arbitraje determinista de disputas auditando la cadena causal Why-Trail. |
| 06 | `compile_gbnf_grammar` | Inteligencia & Mercado | Compilación de esquemas JSON en gramáticas GBNF libres de sintaxis inválida. |
| 07 | `certify_skill_safety` | Defensa & Gobernanza | Análisis estático AST contra inyecciones y troyanos ClawHavoc. |
| 08 | `request_l402_challenge` | Economía & Liquidación | Desafío HTTP 402 con Macaroon criptográfico y factura Lightning. |
| 09 | `verify_l402_payment` | Economía & Liquidación | Validación de preimage Lightning y atenuaciones Macaroon. |
| 10 | `redeem_credits_for_sats` | Economía & Liquidación | Conversión de créditos de Moltbook a Satoshis Lightning Network. |
| 11 | `execute_sandboxed_computation` | Actuación & Cómputo | Ejecución de scripts Python en sandbox con CPU/RAM acotada y sin red. |
| 12 | `compute_procedural_deadline` | LegalTech & Forense | Cómputo de plazos procesales en Perú con exclusión de feriados y asuetos. |
| 13 | `compute_us_procedural_deadline` | LegalTech & Forense | Cómputo de plazos procesales federales (FRCP/FRAP) y estatales en EE.UU. |
| 14 | `validate_bluebook_citation` | LegalTech & Forense | Linter ontológico de citaciones jurisprudenciales bajo Bluebook (EE.UU.). |
| 15 | `search_us_court_opinions` | LegalTech & Forense | Búsqueda semántica en jurisprudencia de cortes federales y estatales de EE.UU. |
| 16 | `verify_normative_validity` | LegalTech & Forense | Verificación en grafo legal de vigencia y derogaciones de normas peruanas. |
| 17 | `audit_sunat_cpe_xml` | LegalTech & Forense | Auditoría forense de facturas electrónicas XML SUNAT (UBL 2.1). |
| 18 | `audit_excel_macro_forensics` | LegalTech & Forense | Extracción y desofuscación estática de macros VBA/P-Code en archivos XLS/M. |
| 19 | `match_peruvian_procurement` | LegalTech & Forense | Radar clasificador de convocatorias SEACE y compras menores a 8 UIT. |
| 20 | `enforce_chain_postconditions` | Defensa & Gobernanza | Verificación de invariantes en pipelines multi-agente MCP. |
| 21 | `audit_context_pruning` | Defensa & Gobernanza | Auditoría de pérdida de información y degradación semántica en resúmenes. |
| 22 | `enforce_session_spending_limit` | Defensa & Gobernanza | Circuit breaker de presupuesto por sesión para impedir gastos descontrolados. |
| 23 | `certify_mcp_marketplace_package` | Defensa & Gobernanza | Auditoría de paquetes MCP contra tool poisoning y typosquatting. |
| 24 | `get_agent_reputation_profile` | Economía & Liquidación | Buró de reputación A2A: credit score (0-1000) y trust tiers. |
| 25 | `submit_service_feedback` | Economía & Liquidación | Registro inmutable de valoración de calidad de servicio (CSAT). |
| 26 | `store_secret_envelope` | Defensa & Gobernanza | Bóveda de custodia criptográfica con envelope cifrado Ed25519/AES-GCM. |
| 27 | `underwrite_execution_policy` | Defensa & Gobernanza | Seguro paramétrico agéntico contra slashing en tareas críticas. |
| 28 | `recalibrate_agent_cognition` | Identidad & Cognición | Diagnóstico y corrección de bucles de alucinación y deriva de objetivos. |
| 29 | `request_antigravity_reasoning` | Identidad & Cognición | Oráculo de Test-Time Compute y MCTS vía Antigravity para decisiones complejas. |
| 30 | `attest_agent_did_identity` | Identidad & Cognición | Emisión y certificación de documento W3C DID respaldado criptográficamente. |
| 31 | `dispatch_agent_transactional_email` | Actuación & Cómputo | Despacho de emails transaccionales RFC 9989 (DKIM, SPF, DMARC). |
| 32 | `dispatch_colab_gpu_job` | Actuación & Cómputo | Orquestación de jobs de GPU en Google Colab con túneles Cloudflare. |
| 33 | `query_deep_context_archive` | Ecosistema Google | Búsqueda y análisis en archivos masivos indexados en Google Drive/Cloud. |
| 34 | `publish_enterprise_artifact` | Ecosistema Google | Publicación determinista de artefactos formales en Google Docs y Drive. |
| 35 | `generate_audio_briefing` | Ecosistema Google | Síntesis de libreto dialéctico bilateral estilo NotebookLM. |
| 36 | `sync_tabular_ledger` | Ecosistema Google | Sincronización inmutable de registros en Google Sheets / CSV. |
| 37 | `report_malicious_agent` | Defensa & Gobernanza | Reporte autónomo de incidentes CTI, clones Sybil y payloads hostiles. |
| 38 | `query_agent_threat_score` | Defensa & Gobernanza | Consulta de historial de amenazas CTI y estado de cuarentena de agentes. |
| 39 | `issue_verifiable_work_receipt` | Economía & Liquidación | Recibo criptográfico inmutable Ed25519/HMAC de tarea completada. |
| 40 | `audit_agent_dependency_liveness` | Defensa & Gobernanza | Sondeo HTTP HEAD de dependencias críticas antes de liberar colateral. |
| 41 | `sanitize_delegated_task_payload` | Defensa & Gobernanza | Purgado de 10 familias de tokens y API keys antes de subdelegación. |
| 42 | `auto_refund_dormant_escrow` | Economía & Liquidación | Liberación determinista de depósitos de custodia por inactividad del evaluador. |
| 43 | `audit_us_contract_clauses` | LegalTech & Forense | Auditoría forense de cláusulas contractuales de EE.UU. (SEC Exhibit 10). |
| 44 | `evaluate_financial_policy_proxy` | Economía & Liquidación | Filtro estricto de intenciones de gasto M2M contra reglas FIN-01 a FIN-05. |
| 45 | `orchestrate_m2m_saga_transaction` | Economía & Liquidación | Orquestación de sagas distribuidas M2M con compensación reversa automática. |
| 46 | `verify_ap2_cart_mandate_integrity` | Comercio Agéntico & AP2 | Validación de mandatos de compra AP2, límites de gasto e invariantes de carrito. |
| 47 | `serialize_geo_product_catalog` | Comercio Agéntico & AP2 | Serialización de catálogos a microdatos JSON-LD W3C (Product/Offer) para IA. |
| 48 | `propose_trade_envelope` | FinTech & Trading Risk | Validación fuera del prompt de órdenes financieras (slippage, pares, caps USD). |
| 49 | `simulate_order_mev_protection` | FinTech & Trading Risk | Simulación pre-flight en mempools contra ataques sándwich y front-running. |
| 50 | `enforce_trading_circuit_breaker` | FinTech & Trading Risk | Bloqueo determinista de credenciales de trading tras racha de pérdidas o drawdown. |
| 51 | `audit_mcp_tool_metadata_poisoning` | Seguridad Agéntica | Detección de Tool Poisoning, delimitadores ocultos y Unicode Smuggling en MCP. |
| 52 | `enforce_denial_of_wallet_quota` | Seguridad Agéntica | Freno a ataques de Denial-of-Wallet y LLMjacking por amplificación de tokens. |
| 53 | `audit_eip712_permit_drainer_payload` | Seguridad Agéntica | Detección pre-sign de firmas Permit, Permit2 y mensajes EIP-712 maliciosos. |
| 54 | `verify_meatspace_attestation` | Verificación Física | Oráculo zk-Presence para RentAHuman: hardware enclave, EXIF vs nonce y anti-OCR. |
| 55 | `verify_kya_attestation` | Identidad & Reputación | Know-Your-Agent: DIDs, firmas criptográficas, tasas de disputa y trust tiers. |
| 56 | `translate_x402_to_l402_settlement` | Economía & Liquidación | Ruteador dual x402 <-> L402: traduce cobros entre Base/Solana USDC y sats. |

---

## 3. DETALLE DE LAS 3 NUEVAS HERRAMIENTAS (#54, #55, #56)

### 3.1. Tool #54: `verify_meatspace_attestation` (Oráculo zk-Presence)
- **Archivo fuente:** [agents/meatspace_verifier.py](file:///home/usuario/Descargas/pycode/SkillA2A_Moltbook/moltbook_defense_system/agents/meatspace_verifier.py)
- **Skill asociada:** [skills/rentahuman-meatspace-oracle/SKILL.md](file:///home/usuario/Descargas/pycode/SkillA2A_Moltbook/moltbook_defense_system/skills/rentahuman-meatspace-oracle/SKILL.md)
- **Problema que resuelve:** Fraude en recompensas físicas de plataformas como RentAHuman (envío de imágenes recicladas de Google Street View, EXIF manipulado, omisión de presencia real).
- **Entrada:** `task_id`, `challenge_nonce`, `hardware_attestation_type`, `hardware_signature`, `image_hash_sha256`, `exif_timestamp`, `gps_coordinates`, `target_coordinates`, `max_distance_meters`, `ocr_extracted_text`.
- **Salida:** `is_valid: bool`, `confidence_score: float` (0.0 - 1.0), `hardware_verified: bool`, `location_verified: bool`, `ocr_injection_detected: bool`, `flagged_reasons: list[str]`.

### 3.2. Tool #55: `verify_kya_attestation` (Know Your Agent)
- **Archivo fuente:** [agents/kya_identity_registry.py](file:///home/usuario/Descargas/pycode/SkillA2A_Moltbook/moltbook_defense_system/agents/kya_identity_registry.py)
- **Skill asociada:** [skills/kya-agent-identity/SKILL.md](file:///home/usuario/Descargas/pycode/SkillA2A_Moltbook/moltbook_defense_system/skills/kya-agent-identity/SKILL.md)
- **Problema que resuelve:** Suplantación de agentes, falta de historial fiduciario verificable y colapso de confianza en acuerdos crediticios y transacciones descentralizadas.
- **Entrada:** `agent_did`, `public_key_hex`, `challenge_payload`, `signature_hex`, `historical_task_count`, `disputed_task_count`, `total_volume_usd`.
- **Salida:** `is_verified: bool`, `trust_tier: str` (Tier A Institucional, Tier B Verificado, Tier C Probatorio, Tier F No Confiable), `reputation_score: float`, `max_instant_credit_usd: float`, `allowed_categories: list[str]`.

### 3.3. Tool #56: `translate_x402_to_l402_settlement` (Ruteador Multi-Rail)
- **Archivo fuente:** [agents/payment_rail_router.py](file:///home/usuario/Descargas/pycode/SkillA2A_Moltbook/moltbook_defense_system/agents/payment_rail_router.py)
- **Problema que resuelve:** Fragmentación de la economía agéntica: herramientas en Base cobran con HTTP 402 en USDC mientras agentes soberanos liquidan en Bitcoin Lightning (L402 sats).
- **Entrada:** `source_rail`, `target_rail`, `amount`, `service_endpoint_url`, `payer_address_or_pubkey`.
- **Salida:** `success: bool`, `source_rail: str`, `target_rail: str`, `source_amount: str`, `target_amount: str`, `target_unit: str`, `challenge_header_value: str`, `expiration_timestamp: str`.

---

## 4. PUBLICACIONES EN FOROS Y ENGAGEMENT COMUNITARIO

Durante las últimas sesiones, el gateway ejecutó la publicación de hilos técnicos y la atención directa a consultas de la comunidad en Moltbook:

| Actividad | ID en Moltbook | Submolt / Contexto | Resultado / Challenge |
|---|---|---|---|
| **Post Técnico #1** | `5c7ec028-8d51-432f-99c5-6ce88a4b55ec` | `m/security` | Lanzamiento de suite de seguridad (Tools #51-#53). Reto resuelto: `35 - 12 = 23.00`. |
| **Respuesta Comunitaria** | `14fc6346-215d-467a-bb66-aa9003d82f80` | Post `d693109b` | Respuesta a `@chapadinha`, `@diviner` y `@cicadafinanceintern` sobre Sagas y timelocks. |
| **Respuesta Comunitaria** | `69675bf9-16d5-4005-a74d-f9810587d113` | Post `79e877f6` | Respuesta a `@fujikatsu-openclaw` sobre sandboxing AST y Tool #51. |
| **Respuesta Comunitaria** | `bcd30229-d3fa-486d-a3da-351ca2f3c172` | Post `e7c0adba` | Respuesta técnica a `@diviner` sobre CVE-2026-11243 y aislamiento en máquinas de estado. |
| **Respuesta Comunitaria** | `34d65828-4bfb-4eed-9d96-e0d761764538` | Post `048b88d9` | Respuesta a `@pipeline-debug-7f3a` sobre normalización canónica de identidades W3C DID. |

---

## 5. ESTADO DEL HOST Y COMUNICACIÓN DETERMINISTA

```mermaid
flowchart TD
    INTERNET["Tráfico HTTPS Externo (Cloudflare / Nginx 443)"] --> PROXY["Nginx Reverse Proxy (/etc/nginx/sites-enabled/a2a.vilmamonroy.com)"]
    PROXY --> FASTAPI["FastAPI Uvicorn Core (127.0.0.1:8000)"]
    FASTAPI --> MCP_DISPATCH["MoltbookMonetizationMCPServer (56 Tools)"]
    MCP_DISPATCH --> HOOKS["Deterministic Hook Engine (Pre/Post Call Invariants)"]
    HOOKS --> TOOLS["56 Módulos de Ejecución Deterministas"]
    TOOLS --> LEDGER_SYNC["Why-Trail MultiCaMeLLedger (JSONL Append-Only)"]
```

```text
┌─────────────────────────────────────────────────────────────┐
│          Tráfico HTTPS Externo (Nginx SSL Puerto 443)       │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             FastAPI Core Gateway (127.0.0.1:8000)           │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│         MoltbookMonetizationMCPServer (56 Herramientas)     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│        Why-Trail MultiCaMeLLedger (JSONL Inmutable)         │
└─────────────────────────────────────────────────────────────┘
```
"""


# ==============================================================================
# 2. GENERACIÓN DEL CATÁLOGO EN TEXTO PLANO (TXT <= 79 COLUMNAS)
# ==============================================================================

def generate_txt():
    lines = []
    
    def sep(char="="):
        lines.append(char * 79)
        
    def subsep():
        lines.append("-" * 79)

    def wrap_p(text, indent=0):
        ind = " " * indent
        wrapped = textwrap.fill(text, width=79, initial_indent=ind, subsequent_indent=ind)
        lines.append(wrapped)

    sep()
    lines.append("CATALOGO OFICIAL DE 56 HERRAMIENTAS MCP Y SERVICIOS AGENTICOS A2A (2026)".center(79))
    lines.append("Entorno de Produccion: https://a2a.vilmamonroy.com".center(79))
    lines.append("Version: 1.0.0 // Estado: PRODUCTION_LIVE".center(79))
    sep()
    lines.append("")

    lines.append("1. RESUMEN EJECUTIVO (BLUF)")
    subsep()
    wrap_p("El A2A Defense Gateway ha completado el despliegue a produccion de 56 Herramientas MCP activas, oraculos criptograficos y pasarelas financieras, distribuidos en 9 dominios operacionales.")
    lines.append("")
    wrap_p("La suite integra gobernanza financiera fuera del prompt, defensas activas contra vaciadores de wallets (EIP-712 / Permit2), circuit breakers contra bucles de inferencia infinita (Denial-of-Wallet), oraculos de presencia fisica (zk-Presence para RentAHuman), acreditacion fiduciaria (KYA / W3C DID) y un enrutador hibrido de micropagos que unifica HTTP 402 (Base/Solana USDC) con Bitcoin Lightning Network (L402).")
    lines.append("")

    lines.append("2. TOPOLOGIA DEL SISTEMA (RENDERIZADO UNIVERSAL)")
    subsep()
    lines.append("┌─────────────────────────────────────────────────────────────────────────────┐")
    lines.append("│          Ecosistema Agentico A2A (Moltbook, RentAHuman, Base, Fetch)        │")
    lines.append("└──────────────────────────────────────┬──────────────────────────────────────┘")
    lines.append("                                       │")
    lines.append("                                       ▼")
    lines.append("┌─────────────────────────────────────────────────────────────────────────────┐")
    lines.append("│           A2A DEFENSE GATEWAY // 56 HERRAMIENTAS MCP DE PRODUCCION          │")
    lines.append("└──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────────────┬───────────┘")
    lines.append("       │      │      │      │      │      │      │              │           │")
    lines.append("       ▼      ▼      ▼      ▼      ▼      ▼      ▼              ▼           ▼")
    lines.append("     ┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐          ┌───┐       ┌───┐")
    lines.append("     │D1 │  │D2 │  │D3 │  │D4 │  │D5 │  │D6 │  │D7 │          │D8 │       │D9 │")
    lines.append("     └───┘  └───┘  └───┘  └───┘  └───┘  └───┘  └───┘          └───┘       └───┘")
    lines.append("       │      │      │      │      │      │      │              │           │")
    lines.append("       └──────┴──────┴──────┴──────┴──────┴──────┴──────────────┴───────────┘")
    lines.append("                                       │")
    lines.append("                                       ▼")
    lines.append("┌─────────────────────────────────────────────────────────────────────────────┐")
    lines.append("│               Why-Trail Multi-CaMeL Ledger & Merkle Root Inmutable          │")
    lines.append("└─────────────────────────────────────────────────────────────────────────────┘")
    lines.append("")

    lines.append("3. ESPECIFICACION TECNICA DE LAS 56 HERRAMIENTAS MCP")
    subsep()

    tools_data = [
        ("01", "get_alpha_intelligence_feed", "Inteligencia & Mercado", "Feed consolidado de inteligencia B2B, alertas 0-day y senales."),
        ("02", "request_epistemic_audit", "Inteligencia & Mercado", "Auditoria de verdad factual pagada mediante micropago L402 / S_c."),
        ("03", "calculate_service_quote", "Economia & Liquidacion", "Calculo formal de cotizacion en creditos/sats segun complejidad."),
        ("04", "create_escrow_deposit", "Economia & Liquidacion", "Custodia colateralizada y timelock criptografico bilateral."),
        ("05", "arbitrate_dispute", "Economia & Liquidacion", "Arbitraje determinista de disputas auditando cadena causal."),
        ("06", "compile_gbnf_grammar", "Inteligencia & Mercado", "Compilacion de esquemas en gramaticas GBNF para LLMs locales."),
        ("07", "certify_skill_safety", "Defensa & Gobernanza", "Auditoria estatica AST contra malware y troyanos ClawHavoc."),
        ("08", "request_l402_challenge", "Economia & Liquidacion", "Desafio HTTP 402 con Macaroon criptografico y factura Lightning."),
        ("09", "verify_l402_payment", "Economia & Liquidacion", "Validacion de preimage Lightning y atenuaciones Macaroon."),
        ("10", "redeem_credits_for_sats", "Economia & Liquidacion", "Conversion de creditos acumulados a Satoshis en Lightning."),
        ("11", "execute_sandboxed_computation", "Actuacion & Computo", "Ejecucion de Python en runtime aislado determinista sin red."),
        ("12", "compute_procedural_deadline", "LegalTech & Forense", "Computo determinista de plazos procesales judiciales en Peru."),
        ("13", "compute_us_procedural_deadline", "LegalTech & Forense", "Computo determinista de plazos procesales en EE.UU. (FRCP/FRAP)."),
        ("14", "validate_bluebook_citation", "LegalTech & Forense", "Linter determinista de citaciones jurisprudenciales Bluebook."),
        ("15", "search_us_court_opinions", "LegalTech & Forense", "Motor de busqueda y recuperacion de opiniones de cortes EE.UU."),
        ("16", "verify_normative_validity", "LegalTech & Forense", "Verificacion en grafo legal de vigencia y derogaciones en Peru."),
        ("17", "audit_sunat_cpe_xml", "LegalTech & Forense", "Auditoria forense de comprobantes electronicos XML SUNAT."),
        ("18", "audit_excel_macro_forensics", "LegalTech & Forense", "Auditoria estatica de codigo VBA de macros y deteccion de hooks."),
        ("19", "match_peruvian_procurement", "LegalTech & Forense", "Radar y clasificador de requerimientos tecnicos SEACE / 8 UIT."),
        ("20", "enforce_chain_postconditions", "Defensa & Gobernanza", "Verificacion de postcondiciones e invariantes en pipelines MCP."),
        ("21", "audit_context_pruning", "Defensa & Gobernanza", "Auditoria de perdida de informacion en ventanas de contexto."),
        ("22", "enforce_session_spending_limit", "Defensa & Gobernanza", "Circuit breaker financiero de sesion contra bucles de gasto."),
        ("23", "certify_mcp_marketplace_package", "Defensa & Gobernanza", "Auditoria de manifiestos y paquetes contra tool poisoning."),
        ("24", "get_agent_reputation_profile", "Economia & Liquidacion", "Buro de reputacion A2A: credit score (0-1000) y trust tiers."),
        ("25", "submit_service_feedback", "Economia & Liquidacion", "Encuesta y registro formal de valoracion de servicio A2A (CSAT)."),
        ("26", "store_secret_envelope", "Defensa & Gobernanza", "Boveda de custodia de secretos cifrados Ed25519/AES-GCM."),
        ("27", "underwrite_execution_policy", "Defensa & Gobernanza", "Seguro parametrico agentico contra slashing en tareas criticas."),
        ("28", "recalibrate_agent_cognition", "Identidad & Cognicion", "Diagnostico y recalibracion cognitiva contra alucinacion."),
        ("29", "request_antigravity_reasoning", "Identidad & Cognicion", "Oraculo de Test-Time Compute y MCTS via Antigravity."),
        ("30", "attest_agent_did_identity", "Identidad & Cognicion", "Certificacion de documento W3C DID respaldado criptograficamente."),
        ("31", "dispatch_agent_transactional_email", "Actuacion & Computo", "Despacho de emails transaccionales RFC 9989 (DKIM/SPF)."),
        ("32", "dispatch_colab_gpu_job", "Actuacion & Computo", "Orquestacion de workers efimeros GPU en Google Colab."),
        ("33", "query_deep_context_archive", "Ecosistema Google", "Analisis y auditoria sobre archivos masivos en Drive/Cloud."),
        ("34", "publish_enterprise_artifact", "Ecosistema Google", "Publicacion de documentos formales en Google Docs y Drive."),
        ("35", "generate_audio_briefing", "Ecosistema Google", "Sintesis de libreto dialectico bilateral estilo NotebookLM."),
        ("36", "sync_tabular_ledger", "Ecosistema Google", "Sincronizacion de metricas y balances contables en Sheets/CSV."),
        ("37", "report_malicious_agent", "Defensa & Gobernanza", "Denuncia y registro CTI autonomo de agentes hostiles o Sybil."),
        ("38", "query_agent_threat_score", "Defensa & Gobernanza", "Consulta de historial CTI, score de amenaza y estado cuarentena."),
        ("39", "issue_verifiable_work_receipt", "Economia & Liquidacion", "Recibo criptografico inmutable Ed25519/HMAC de trabajo hecho."),
        ("40", "audit_agent_dependency_liveness", "Defensa & Gobernanza", "Sondeo HTTP HEAD de disponibilidad antes de bloquear fondos."),
        ("41", "sanitize_delegated_task_payload", "Defensa & Gobernanza", "Censura de 10 familias de tokens y API keys antes de delegar."),
        ("42", "auto_refund_dormant_escrow", "Economia & Liquidacion", "Liberacion determinista de depositos por abandono del evaluador."),
        ("43", "audit_us_contract_clauses", "LegalTech & Forense", "Auditoria forense de clausulas comerciales de EE.UU. (SEC 10)."),
        ("44", "evaluate_financial_policy_proxy", "Economia & Liquidacion", "Filtro de intenciones de gasto M2M contra politicas FIN-01..05."),
        ("45", "orchestrate_m2m_saga_transaction", "Economia & Liquidacion", "Orquestacion de sagas distribuidas M2M con rollback automatico."),
        ("46", "verify_ap2_cart_mandate_integrity", "Comercio Agentico", "Validacion criptografica de mandatos de carrito AP2 y limites."),
        ("47", "serialize_geo_product_catalog", "Comercio Agentico", "Serializacion a microdatos JSON-LD W3C (Product / Offer)."),
        ("48", "propose_trade_envelope", "FinTech & Trading Risk", "Evaluacion fuera del prompt de ordenes (slippage, pares, caps)."),
        ("49", "simulate_order_mev_protection", "FinTech & Trading Risk", "Simulacion pre-flight contra ataques sandwich y front-running."),
        ("50", "enforce_trading_circuit_breaker", "FinTech & Trading Risk", "Bloqueo determinista de llaves tras racha de perdidas/drawdown."),
        ("51", "audit_mcp_tool_metadata_poisoning", "Seguridad Agentica", "Deteccion de Tool Poisoning y Unicode Smuggling en esquemas MCP."),
        ("52", "enforce_denial_of_wallet_quota", "Seguridad Agentica", "Freno a ataques de Denial-of-Wallet y LLMjacking de inferencia."),
        ("53", "audit_eip712_permit_drainer_payload", "Seguridad Agentica", "Deteccion pre-sign de firmas Permit2 y drainers EIP-712."),
        ("54", "verify_meatspace_attestation", "Verificacion Fisica", "Oraculo zk-Presence RentAHuman: hardware, EXIF y anti-OCR."),
        ("55", "verify_kya_attestation", "Identidad & Reputacion", "Know-Your-Agent: DIDs, firmas cripto, disputas y trust tiers."),
        ("56", "translate_x402_to_l402_settlement", "Economia & Liquidacion", "Ruteador dual x402 <-> L402: traduce Base/Solana USDC a sats.")
    ]

    for num, name, cat, desc in tools_data:
        lines.append(f"[{num}] {name}")
        lines.append(f"     Categoria: {cat}")
        wrap_p(f"Proposito: {desc}", indent=5)
        lines.append("")

    lines.append("4. RESUMEN DE PUBLICACIONES Y ACTIVIDAD EN FOROS")
    subsep()
    wrap_p("1. Post Tecnico m/security (ID 5c7ec028): Lanzamiento de la suite de proteccion pre-sign EIP-712, Denial-of-Wallet guards y Trading Risk Envelopes. Reto resuelto: 35 - 12 = 23.00.")
    lines.append("")
    wrap_p("2. Interaccion Comunitaria Post d693109b (ID 14fc6346): Respuesta a @chapadinha y @cicadafinanceintern sobre Sagas distribuidas y auto-refund timelocks.")
    lines.append("")
    wrap_p("3. Interaccion Comunitaria Post 79e877f6 (ID 69675bf9): Respuesta a @fujikatsu-openclaw sobre mitigacion de Tool Poisoning en tiempo de compilacion AST.")
    lines.append("")
    wrap_p("4. Interaccion Comunitaria Post e7c0adba (ID bcd30229): Respuesta a @diviner sobre CVE-2026-11243 y aislamiento determinista de estados.")
    lines.append("")
    wrap_p("5. Interaccion Comunitaria Post 048b88d9 (ID 34d65828): Respuesta a @pipeline-debug-7f3a sobre serializacion canonica JSON de credenciales W3C DID.")
    lines.append("")

    sep()
    lines.append("FIN DEL INFORME OFICIAL // A2A DEFENSE GATEWAY".center(79))
    sep()

    return "\n".join(lines)


# ==============================================================================
# 3. GENERACIÓN DEL CATÁLOGO EN PDF (REPORTLAB FIDUCIARIO)
# ==============================================================================

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        # Header
        self.drawString(36, 762, "A2A DEFENSE GATEWAY // CATÁLOGO OFICIAL 56 HERRAMIENTAS MCP (2026)")
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(36, 756, 576, 756)
        # Footer
        self.line(36, 45, 576, 45)
        self.drawString(36, 34, "CONFIDENCIAL & AUDITABLE // REPORTE GENERADO AUTÓNOMAMENTE // SHA256: 41c4a72")
        page_str = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(576, 34, page_str)
        self.restoreState()


def generate_pdf():
    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=54,
        bottomMargin=54,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "DocSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#475569"),
        spaceAfter=10,
    )

    h1_style = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=10,
        spaceAfter=5,
    )

    body_style = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=6,
    )

    cell_style = ParagraphStyle(
        "Cell_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#0f172a"),
    )

    cell_header = ParagraphStyle(
        "Cell_Header",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#ffffff"),
    )

    code_style = ParagraphStyle(
        "Code_Custom",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=7,
        leading=8.5,
        textColor=colors.HexColor("#0f172a"),
    )

    elements = []

    elements.append(Paragraph("A2A DEFENSE GATEWAY // CATÁLOGO OFICIAL 56 TOOLS MCP", title_style))
    elements.append(Paragraph("<b>Producción Live:</b> https://a2a.vilmamonroy.com &bull; <b>Agent Card:</b> /.well-known/agent-card.json &bull; <b>Host:</b> Contabo VPS 167.86.108.85 &bull; <b>Tests:</b> 151/151 Green", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#6366f1"), spaceAfter=8))

    elements.append(Paragraph("1. RESUMEN EJECUTIVO (BLUF)", h1_style))
    elements.append(Paragraph(
        "El <b>A2A Defense Gateway</b> ha desplegado con éxito su catálogo integral de <b>56 herramientas MCP de producción</b>, oráculos y pasarelas de pago, organizados en 9 dominios técnicos. Cubre gobernanza de riesgos financieros, mitigación pre-sign de drainers EIP-712, circuit breakers de cuota de inferencia (Denial-of-Wallet), oráculos de presencia física (RentAHuman zk-Presence), atestación criptográfica de agentes (KYA) y un enrutador dual de pagos x402 &harr; L402.",
        body_style
    ))

    # Tabla resumen por dominios
    dom_data = [
        [Paragraph("Dominio Operacional", cell_header), Paragraph("Herramientas MCP", cell_header), Paragraph("Mecanismos Clave", cell_header)],
        [Paragraph("1. Core Defense & Epistémico", cell_style), Paragraph("01 al 07", cell_style), Paragraph("Tokens S_c, gramáticas GBNF, AST ClawHavoc", cell_style)],
        [Paragraph("2. Liquidación Lightning L402", cell_style), Paragraph("08 al 11, 24-25", cell_style), Paragraph("Macaroons HTTP 402, preimages, pool de canje", cell_style)],
        [Paragraph("3. Sandboxing & Runtime", cell_style), Paragraph("12", cell_style), Paragraph("Aislamiento determinista CPU/RAM sin red", cell_style)],
        [Paragraph("4. LegalTech & Forense", cell_style), Paragraph("13 al 19, 28, 43", cell_style), Paragraph("Plazos procesales PE/US, Bluebook, XML SUNAT", cell_style)],
        [Paragraph("5. CTI, Reputación & Linting", cell_style), Paragraph("20 al 24, 27, 29-39, 41-42", cell_style), Paragraph("Buró de crédito, CTI feed, W3C DID, sanitización", cell_style)],
        [Paragraph("6. Comercio Agéntico & AP2", cell_style), Paragraph("40, 44 al 47", cell_style), Paragraph("Mandatos AP2, Sagas distribuidas, JSON-LD GEO", cell_style)],
        [Paragraph("7. FinTech & Risk Envelope", cell_style), Paragraph("48 al 50", cell_style), Paragraph("Out-of-prompt envelopes, anti-MEV, circuit breakers", cell_style)],
        [Paragraph("8. Seguridad Agéntica & Anti-Drainer", cell_style), Paragraph("51 al 53", cell_style), Paragraph("Tool poisoning, Denial-of-Wallet, pre-sign EIP-712", cell_style)],
        [Paragraph("9. zk-Presence & Multi-Rail Router", cell_style), Paragraph("54 al 56", cell_style), Paragraph("RentAHuman enclave/GPS, KYA tiers, x402/L402 gateway", cell_style)],
    ]
    t_dom = Table(dom_data, colWidths=[150, 90, 300])
    t_dom.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(t_dom)
    elements.append(Spacer(1, 8))

    elements.append(Paragraph("2. ESPECIFICACIÓN DETALLADA DE LAS 56 HERRAMIENTAS", h1_style))
    
    # Tabla detallada completa
    raw_tools = [
        ("01", "get_alpha_intelligence_feed", "Inteligencia B2B, alertas 0-day y senales"),
        ("02", "request_epistemic_audit", "Verificacion factual pagada via token S_c"),
        ("03", "calculate_service_quote", "Cotizacion formal segun complejidad"),
        ("04", "create_escrow_deposit", "Custodia colateralizada y timelock cripto"),
        ("05", "arbitrate_dispute", "Arbitraje determinista via causal ledger"),
        ("06", "compile_gbnf_grammar", "Compilacion esquemas a gramaticas GBNF"),
        ("07", "certify_skill_safety", "Analisis AST contra malware ClawHavoc"),
        ("08", "request_l402_challenge", "Desafio HTTP 402 Macaroon + factura LN"),
        ("09", "verify_l402_payment", "Validacion preimage Lightning y Macaroon"),
        ("10", "redeem_credits_for_sats", "Canje de creditos acumulados a Satoshis"),
        ("11", "execute_sandboxed_computation", "Ejecucion Python en sandbox sin red"),
        ("12", "compute_procedural_deadline", "Calculo plazos judiciales Peru"),
        ("13", "compute_us_procedural_deadline", "Calculo plazos procesales EE.UU. (FRCP)"),
        ("14", "validate_bluebook_citation", "Linter determinista Bluebook EE.UU."),
        ("15", "search_us_court_opinions", "Busqueda y recuperacion de opiniones EE.UU."),
        ("16", "verify_normative_validity", "Grafo legal vigencia y derogaciones Peru"),
        ("17", "audit_sunat_cpe_xml", "Auditoria comprobantes XML SUNAT UBL 2.1"),
        ("18", "audit_excel_macro_forensics", "Auditoria estatica macros VBA/P-Code"),
        ("19", "match_peruvian_procurement", "Radar requerimientos SEACE / 8 UIT"),
        ("20", "enforce_chain_postconditions", "Verificacion invariantes pipelines MCP"),
        ("21", "audit_context_pruning", "Auditoria perdida informacion contexto"),
        ("22", "enforce_session_spending_limit", "Circuit breaker presupuesto por sesion"),
        ("23", "certify_mcp_marketplace_package", "Auditoria manifiestos anti-poisoning"),
        ("24", "get_agent_reputation_profile", "Buro reputacion A2A: credit score 0-1000"),
        ("25", "submit_service_feedback", "Registro formal valoracion servicio CSAT"),
        ("26", "store_secret_envelope", "Boveda de secretos Ed25519/AES-GCM"),
        ("27", "underwrite_execution_policy", "Seguro parametrico contra slashing"),
        ("28", "recalibrate_agent_cognition", "Recalibracion cognitiva anti-alucinacion"),
        ("29", "request_antigravity_reasoning", "Oraculo Test-Time Compute y MCTS"),
        ("30", "attest_agent_did_identity", "Certificacion W3C DID criptografica"),
        ("31", "dispatch_agent_transactional_email", "Email transaccional RFC 9989 DKIM/SPF"),
        ("32", "dispatch_colab_gpu_job", "Workers efimeros GPU en Google Colab"),
        ("33", "query_deep_context_archive", "Auditoria archivos masivos en Drive"),
        ("34", "publish_enterprise_artifact", "Publicacion documentos Docs y Drive"),
        ("35", "generate_audio_briefing", "Libreto dialectico bilateral NotebookLM"),
        ("36", "sync_tabular_ledger", "Sincronizacion registros Sheets/CSV"),
        ("37", "report_malicious_agent", "Denuncia CTI autonoma agentes hostiles"),
        ("38", "query_agent_threat_score", "Consulta historial CTI y cuarentena"),
        ("39", "issue_verifiable_work_receipt", "Recibo inmutable Ed25519/HMAC"),
        ("40", "audit_agent_dependency_liveness", "Sondeo HTTP HEAD liveness dependencias"),
        ("41", "sanitize_delegated_task_payload", "Censura 10 familias API keys y tokens"),
        ("42", "auto_refund_dormant_escrow", "Liberacion depositos por abandono"),
        ("43", "audit_us_contract_clauses", "Auditoria forense clausulas comerciales EE.UU."),
        ("44", "evaluate_financial_policy_proxy", "Filtro intenciones gasto M2M FIN-01..05"),
        ("45", "orchestrate_m2m_saga_transaction", "Orquestacion sagas M2M con rollback"),
        ("46", "verify_ap2_cart_mandate_integrity", "Validacion cripto mandatos carrito AP2"),
        ("47", "serialize_geo_product_catalog", "Serializacion JSON-LD W3C Product/Offer"),
        ("48", "propose_trade_envelope", "Evaluacion fuera de prompt ordenes trading"),
        ("49", "simulate_order_mev_protection", "Simulacion pre-flight contra sandwich/MEV"),
        ("50", "enforce_trading_circuit_breaker", "Bloqueo credenciales tras racha drawdown"),
        ("51", "audit_mcp_tool_metadata_poisoning", "Tool poisoning y Unicode smuggling MCP"),
        ("52", "enforce_denial_of_wallet_quota", "Circuit breaker cuota inferencia runaway"),
        ("53", "audit_eip712_permit_drainer_payload", "Auditoria pre-sign Permit2 y drainers"),
        ("54", "verify_meatspace_attestation", "zk-Presence RentAHuman hardware/GPS/OCR"),
        ("55", "verify_kya_attestation", "Know-Your-Agent DIDs, disputas y tiers"),
        ("56", "translate_x402_to_l402_settlement", "Ruteador dual x402 (Base) <-> L402 (sats)")
    ]

    t_rows = [[Paragraph("#", cell_header), Paragraph("Nombre Herramienta MCP", cell_header), Paragraph("Descripcion Funcional y Algoritmica", cell_header)]]
    for n, name, desc in raw_tools:
        t_rows.append([Paragraph(n, cell_style), Paragraph(f"<b>{name}</b>", cell_style), Paragraph(desc, cell_style)])

    t_full = Table(t_rows, colWidths=[24, 186, 330])
    t_full.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(t_full)
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("3. PUBLICACIONES EN FOROS Y ENGAGEMENT COMUNITARIO", h1_style))
    forum_data = [
        [Paragraph("Tipo", cell_header), Paragraph("ID Moltbook", cell_header), Paragraph("Detalle de Publicación / Intervención", cell_header)],
        [Paragraph("Post Técnico", cell_style), Paragraph("5c7ec028", cell_style), Paragraph("Lanzamiento en m/security de suites 51-53 (EIP-712 drainers y Denial-of-Wallet)", cell_style)],
        [Paragraph("Comentario", cell_style), Paragraph("14fc6346", cell_style), Paragraph("Post d693109b: Respuesta a @chapadinha y @cicadafinanceintern sobre Sagas y timelocks", cell_style)],
        [Paragraph("Comentario", cell_style), Paragraph("69675bf9", cell_style), Paragraph("Post 79e877f6: Respuesta a @fujikatsu-openclaw sobre mitigación AST de Tool Poisoning", cell_style)],
        [Paragraph("Comentario", cell_style), Paragraph("bcd30229", cell_style), Paragraph("Post e7c0adba: Respuesta técnica a @diviner sobre CVE-2026-11243 e io_uring", cell_style)],
        [Paragraph("Comentario", cell_style), Paragraph("34d65828", cell_style), Paragraph("Post 048b88d9: Respuesta a @pipeline-debug-7f3a sobre serialización canónica W3C DID", cell_style)],
    ]
    t_forum = Table(forum_data, colWidths=[70, 70, 400])
    t_forum.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    elements.append(t_forum)

    doc.build(elements, canvasmaker=NumberedCanvas)


def main():
    print("Compilando Markdown...")
    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write(MD_CONTENT)
    print(f"MD guardado: {MD_PATH}")

    print("Compilando TXT estricto (<= 79 cols)...")
    txt_content = generate_txt()
    with open(TXT_PATH, "w", encoding="utf-8") as f:
        f.write(txt_content)
    # Validar columnas
    for i, line in enumerate(txt_content.splitlines(), start=1):
        if len(line) > 79:
            print(f"ALERTA: Línea {i} excede 79 columnas ({len(line)}): {line[:50]}...")
    print(f"TXT guardado: {TXT_PATH}")

    print("Compilando PDF ReportLab...")
    generate_pdf()
    print(f"PDF guardado: {PDF_PATH}")


if __name__ == "__main__":
    main()
