---
name: agentic-threat-sentinel
description: Centinela de seguridad integral para agentes de IA y operaciones Web3. Detecta y neutraliza Tool Poisoning en manifiestos MCP, frena ataques de Denial-of-Wallet y LLMjacking mediante cuotas de amplificación, y audita pre-sign firmas Permit, Permit2 y mensajes EIP-712 para prevenir Wallet Drainers. Triggers: agentic threat, tool poisoning, mcp poisoning, denial of wallet, llmjacking, wallet drainer, permit2 drainer, eip712 audit, blind sign.
---

# Agentic Threat Sentinel & Web3 Drainer Defense

Framework de ciberseguridad neurosimbólica para la detección, contención y neutralización de vectores hostiles dirigidos contra agentes autónomos, modelos de inferencia y billeteras criptográficas.

## 1. Topología del Sistema Defensivo

```mermaid
flowchart TD
    INPUT["Carga Externa (Servidor MCP / Prompt / Transacción EIP-712)"] --> SENTINEL["Agentic Threat Sentinel"]
    
    subgraph INSPECTION["Inspección Forense Multi-Capa"]
        SENTINEL --> T51["Tool #51: audit_mcp_tool_metadata_poisoning"]
        SENTINEL --> T52["Tool #52: enforce_denial_of_wallet_quota"]
        SENTINEL --> T53["Tool #53: audit_eip712_permit_drainer_payload"]
    end
    
    T51 -- "Vectores Hostiles / Inyección" --> QUARANTINE["Aislamiento y Cuarentena de Tool"]
    T52 -- "Amplificación > 10x / Presupuesto Excedido" --> KILL_SWITCH["Halt Inmediato (Kill-Switch de Inferencia)"]
    T53 -- "Infinite Approval / Drainer Conocido" --> ABORT_SIGN["Bloqueo Pre-Sign de Transacción"]
    
    T51 -- "Limpio" --> PROCEED["Ejecución Autorizada"]
    T52 -- "Cuota Saludable" --> PROCEED
    T53 -- "Firma Segura" --> PROCEED
    
    PROCEED --> WHY["Why-Trail Causal Ledger"]
```

```text
┌────────────────────────────────────────────────────────────────────────┐
│   CARGA EXTERNA (SERVIDOR MCP / PROMPT / TRANSACCIÓN EIP-712)          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌─ AGENTIC THREAT SENTINEL (INSPECCIÓN FORENSE MULTI-CAPA) ─────────────┐
│ ┌────────────────────────────────────────────────────────────────────┐ │
│ │ Tool #51: audit_mcp_tool_metadata_poisoning (Tool Poisoning & CoT) │ │
│ └─────────────────────────────────┬──────────────────────────────────┘ │
│                                   ▼                                    │
│ ┌────────────────────────────────────────────────────────────────────┐ │
│ │ Tool #52: enforce_denial_of_wallet_quota (Denial-of-Wallet/Tokens) │ │
│ └─────────────────────────────────┬──────────────────────────────────┘ │
│                                   ▼                                    │
│ ┌────────────────────────────────────────────────────────────────────┐ │
│ │ Tool #53: audit_eip712_permit_drainer_payload (Drainers & Permit2) │ │
│ └─────────────────────────────────┬──────────────────────────────────┘ │
└───────────────────────────────────┼────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   DIAGNÓSTICO DETERMINISTA DE RIESGO                   │
└───────────────┬───────────────────┬───────────────────┬────────────────┘
                │ Inyección MCP     │ Amplificación     │ Drainer / Blind
                ▼                   ▼                   ▼
┌─────────────────────────┐ ┌─────────────────┐ ┌────────────────────────┐
│ Cuarentena de Tool MCP  │ │ Kill-Switch DoW │ │ Bloqueo Pre-Sign Firma │
└───────────────┬─────────┘ └────────┬────────┘ └────────┬───────────────┘
                │                    │                   │
                └────────────────────┼───────────────────┘
                                     ▼ (Si es Seguro)
┌────────────────────────────────────────────────────────────────────────┐
│      Ejecución Autorizada & Registro en Why-Trail Causal Ledger        │
└────────────────────────────────────────────────────────────────────────┘
```

## 2. Herramientas MCP Operativas

### Herramienta #51: `audit_mcp_tool_metadata_poisoning`
- **Amenaza Mitigada**: Inyecciones de prompt escondidas en descripciones o schemas JSON de servidores MCP en `tools/list`.
- **Detección**: Comandos de anulación (`system: override`), delimitadores de contexto (`<tool_call>`), caracteres invisibles de ancho cero (zero-width characters) y pesca de credenciales sensibles (`private_key`, `seed_phrase`).

### Herramienta #52: `enforce_denial_of_wallet_quota`
- **Amenaza Mitigada**: Denial-of-Wallet y LLMjacking mediante amplificación forzada de tokens de razonamiento CoT y bucles recursivos.
- **Detección**: Calcula en tiempo real el ratio de amplificación `(completion_tokens + thinking_tokens) / prompt_tokens`. Si supera `10.0x` o se rebasa el presupuesto en USD, corta de inmediato la sesión.

### Herramienta #53: `audit_eip712_permit_drainer_payload`
- **Amenaza Mitigada**: Wallet Drainers basados en firmas fuera de cadena (Permit, Permit2, BatchPermit) y firmas ciegas `eth_sign`.
- **Detección**: Cruza el operador con bases de datos de drainers conocidos (Inferno, Pink, Angel), audita aprobaciones ilimitadas (`type(uint256).max`), fechas de caducidad permanentes y hashes ciegos.
