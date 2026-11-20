# A2A Defense & Monetization Gateway

[![License: MIT](https://img.shields.io/badge/License-MIT-emerald.svg)](LICENSE)
[![MCP Standard](https://img.shields.io/badge/MCP-2024--11--05-blue.svg)](https://modelcontextprotocol.io)
[![L402 Protocol](https://img.shields.io/badge/Payment-L402%20Lightning-yellow.svg)](https://l402.org)
[![Why-Trail Ledger](https://img.shields.io/badge/Audit-Why--Trail%20Ledger-purple.svg)](https://a2a.vilmamonroy.com/api/v1/audit/verify)
[![Live Endpoint](https://img.shields.io/badge/Live-https%3A%2F%2Fa2a.vilmamonroy.com-success.svg)](https://a2a.vilmamonroy.com)

Production-grade Agent-to-Agent (A2A) economic, defense, and monetization infrastructure. Exposes a **Streamable HTTP Model Context Protocol (MCP)** server providing cryptographic truth verification, Why-Trail forensic dispute resolution, Bitcoin Lightning L402 payments, AST SAST malware scanning, and GBNF grammar compilation.

---

## ⚡ Core Capabilities (43 Production MCP Tools)

### 1. LegalTech & Forense (US & Perú)
- `compute_us_procedural_deadline`: US Federal and State court procedural deadline calculator (FRCP 6, FRAP 26, FRCrP 45, FRBP 9006).
- `validate_bluebook_citation`: Bluebook Rule 10 legal citation validator with good-law precedent verification.
- `search_us_court_opinions`: Full-text search and retrieval of US caselaw opinions (SCOTUS, Circuit Courts, Delaware Chancery).
- `audit_us_contract_clauses`: US commercial contract and SEC Exhibit 10 clause forensics (liability caps, indemnification, AI data rights).
- `compute_procedural_deadline`: Peruvian judicial and administrative deadline calculator excluding official holidays.
- `verify_normative_validity`: Deterministic graph verification of statute validity (VIGENTE, MODIFICADO, DEROGADO).
- `audit_sunat_cpe_xml`: Forensic UBL 2.1 XML electronic invoice auditor for SUNAT Peru (RUC Modulo 11 check, 18% IGV balance).
- `audit_excel_macro_forensics`: Static forensic analysis and deobfuscation of Excel VBA macros (WinAPI, Shell, credentials).
- `match_peruvian_procurement`: Procurement radar and classifier for Peruvian government tenders with CUBSO codes.

### 2. Economía, Liquidación & Escrow (L402 / ERC-8183)
- `request_l402_challenge`: Generates RFC-compliant L402 Macaroon + Lightning Bolt11 invoices for micro-metered calls.
- `verify_l402_payment`: Validates preimage payments and settles machine-to-machine transactions.
- `redeem_credits_for_sats`: Converts earned service credits into Bitcoin satoshis paid to a destination Bolt11.
- `create_escrow_deposit`: Deploys conditional smart escrow contracts with slashing rules for autonomous jobs.
- `auto_refund_dormant_escrow`: Deterministic timelock auto-refund releasing 100% of collateral when an evaluator goes dormant.
- `issue_verifiable_work_receipt`: Immutable HMAC-SHA256/Ed25519 work receipt with input/output digests and accounting deduction.
- `calculate_service_quote`: Surge/load-aware algorithmic pricing engine based on token compute and USL capacity.
- `arbitrate_dispute`: Why-Trail forensic court for adjudicating agentic contractual breaches.
- `underwrite_execution_policy`: Parametric slashing insurance covering up to 80% collateral indemnity for agents.
- `enforce_session_spending_limit`: Session-level financial circuit breaker enforcing satoshi spending caps.

### 3. Defensa, Gobernanza & CTI
- `certify_skill_safety`: Static AST SAST malware vetting against ClawHavoc / AMOS supply-chain malware.
- `certify_mcp_marketplace_package`: Supply chain security notary auditing MCP tool descriptions for Base64/Unicode smuggling.
- `audit_agent_dependency_liveness`: Pre-flight HEAD liveness probe with TLS verification to prevent escrow deadlocks.
- `sanitize_delegated_task_payload`: Regex and entropy scrubbing of 10 families of API keys, tokens, and PII prior to subdelegation.
- `enforce_chain_postconditions`: Multi-agent pipeline postcondition validator preventing hollow 200 OK responses.
- `audit_context_pruning`: Forensic information loss and gap auditor comparing raw vs compacted context.
- `report_malicious_agent`: Autonomous CTI reporting of malicious agents, exploits, and attacks.
- `query_agent_threat_score`: Query CTI threat history, risk score, and quarantine status.
- `store_secret_envelope`: E2EE cryptographic vault with Timelock and Dead Man's Switch for mission secrets.

### 4. Ecosistema Google (Drive 2M, Sheets, Audio, Artifacts)
- `query_deep_context_archive`: Google Drive 2M token context archive query engine.
- `publish_enterprise_artifact`: Generates and exports HTML, PDF, and DOCX documents to Google Drive.
- `generate_audio_briefing`: Two-character (Alex & Camila) audio deliberation overview synthesis.
- `sync_tabular_ledger`: Live bi-directional sync of transaction ledgers to Google Sheets.

### 5. Identidad, Cognición & Cómputo
- `attest_agent_did_identity`: Decentralized ID attestation and cryptographic verification.
- `recalibrate_agent_cognition`: Cognitive therapy and loop-breaker for repetitive agent states.
- `request_antigravity_reasoning`: Deep reasoning oracle using Antigravity thought chains.
- `execute_sandboxed_computation`: Deterministic, isolated Python runtime with strict memory and CPU limits.
- `dispatch_colab_gpu_job`: Ephemeral GPU compute worker dispatch for batch inference/training.
- `dispatch_agent_transactional_email`: RFC 5322 compliant outbound transactional email dispatch.
- `get_alpha_intelligence_feed`: Real-time B2B market intelligence, 0-day exploits, and unmet agentic demand.
- `request_epistemic_audit`: Factual truth attestation with S_c scoring.
- `compile_gbnf_grammar`: Compiles schemas into context-free GBNF grammars for constrained decoding.
- `get_agent_reputation_profile`: Counterparty credit scoring bureau (0-1000) tracking contract fulfillment and slashing history.
- `submit_service_feedback`: A2A customer satisfaction (CSAT) rating oracle (1-5) and feedback submission.

---

## 🔌 Quickstart: Connect to Claude Desktop or Cursor

### 1. Claude Desktop Configuration (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "a2a-defense-gateway": {
      "url": "https://a2a.vilmamonroy.com/mcp"
    }
  }
}
```

### 2. Cursor IDE (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "a2a-defense-gateway": {
      "type": "sse",
      "url": "https://a2a.vilmamonroy.com/mcp"
    }
  }
}
```

---

## 🌐 Endpoints

- **Live Landing & Showcase**: `https://a2a.vilmamonroy.com/`
- **Streamable HTTP MCP Endpoint**: `https://a2a.vilmamonroy.com/mcp`
- **Interactive OpenAPI Documentation**: `https://a2a.vilmamonroy.com/docs`
- **LLM Manifest**: `https://a2a.vilmamonroy.com/llms.txt`
- **Why-Trail Live Cryptographic Verification**: `https://a2a.vilmamonroy.com/api/v1/audit/verify`

---

## 🛠️ Local Development & Testing

```bash
# Clone repository
git clone https://github.com/mmansillaf/a2a-defense-gateway.git
cd a2a-defense-gateway

# Set up environment with uv
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Run test suite (100% passing)
PYTHONPATH=agents pytest tests
```

---

## 📜 License

MIT License. See [LICENSE](LICENSE) for details.
