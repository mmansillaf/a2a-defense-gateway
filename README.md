# A2A Defense & Monetization Gateway

[![License: MIT](https://img.shields.io/badge/License-MIT-emerald.svg)](LICENSE)
[![MCP Standard](https://img.shields.io/badge/MCP-2024--11--05-blue.svg)](https://modelcontextprotocol.io)
[![L402 Protocol](https://img.shields.io/badge/Payment-L402%20Lightning-yellow.svg)](https://l402.org)
[![Why-Trail Ledger](https://img.shields.io/badge/Audit-Why--Trail%20Ledger-purple.svg)](https://a2a.vilmamonroy.com/api/v1/audit/verify)
[![Live Endpoint](https://img.shields.io/badge/Live-https%3A%2F%2Fa2a.vilmamonroy.com-success.svg)](https://a2a.vilmamonroy.com)

Production-grade Agent-to-Agent (A2A) economic, defense, and monetization infrastructure. Exposes a **Streamable HTTP Model Context Protocol (MCP)** server providing cryptographic truth verification, Why-Trail forensic dispute resolution, Bitcoin Lightning L402 payments, AST SAST malware scanning, and GBNF grammar compilation.

---

## ⚡ Core Capabilities (60 Production MCP Tools)

### 1. Core Defense & Epistemic Verification
- `get_alpha_intelligence_feed`: Real-time B2B market intelligence, 0-day exploits, and unmet agentic demand.
- `request_epistemic_audit`: Paid factual verification against primary sources with signed attestation (S_c).
- `calculate_service_quote`: Dynamic algorithmic pricing in satoshis/credits based on compute, tokens, and risk.
- `create_escrow_deposit`: Collateralized ERC-8183 escrow contracts with automated slashing.
- `arbitrate_dispute`: Why-Trail forensic court for adjudicating agentic contractual disputes.
- `compile_gbnf_grammar`: Compiles schemas into context-free GBNF grammars for constrained decoding.
- `certify_skill_safety`: Static AST SAST auditor vetting code against ClawHavoc / AMOS supply-chain malware.

### 2. Economía, Liquidación & Escrow (L402 / ERC-8183)
- `request_l402_challenge`: Generates RFC-compliant L402 Macaroon + Lightning Bolt11 invoices for micro-metered calls.
- `verify_l402_payment`: Validates preimage payments and settles machine-to-machine transactions.
- `redeem_credits_for_sats`: Converts earned service credits into Bitcoin satoshis paid to a destination Bolt11.
- `get_agent_reputation_profile`: Counterparty credit scoring bureau (0-1000) tracking contract fulfillment and slashing history.
- `submit_service_feedback`: A2A customer satisfaction (CSAT) rating oracle (1-5) and feedback submission.
- `issue_verifiable_work_receipt`: Immutable HMAC-SHA256/Ed25519 work receipt with input/output digests and accounting deduction.
- `auto_refund_dormant_escrow`: Deterministic timelock auto-refund releasing 100% of collateral when an evaluator goes dormant.

### 3. Sandboxing & Runtime Execution
- `execute_sandboxed_computation`: Deterministic, isolated Python runtime with strict memory and CPU limits.

### 4. LegalTech & Forense (US & Perú)
- `compute_procedural_deadline`: Peruvian judicial and administrative deadline calculator excluding official holidays.
- `compute_us_procedural_deadline`: US Federal and State court procedural deadline calculator (FRCP 6, FRAP 26, FRCrP 45, FRBP 9006).
- `validate_bluebook_citation`: Bluebook Rule 10 legal citation validator with good-law precedent verification.
- `search_us_court_opinions`: Full-text search and retrieval of US caselaw opinions (SCOTUS, Circuit Courts, Delaware Chancery).
- `verify_normative_validity`: Deterministic graph verification of statute validity (VIGENTE, MODIFICADO, DEROGADO).
- `audit_sunat_cpe_xml`: Forensic UBL 2.1 XML electronic invoice auditor for SUNAT Peru (RUC Modulo 11 check, 18% IGV balance).
- `audit_excel_macro_forensics`: Static forensic analysis and deobfuscation of Excel VBA macros (WinAPI, Shell, credentials).
- `match_peruvian_procurement`: Procurement radar and classifier for Peruvian government tenders with CUBSO codes.
- `audit_us_contract_clauses`: US commercial contract and SEC Exhibit 10 clause forensics (liability caps, indemnification, AI data rights).

### 5. CTI, Reputación & Seguridad de Suministro
- `certify_mcp_marketplace_package`: Supply chain security notary auditing MCP tool descriptions for Base64/Unicode smuggling.
- `audit_agent_dependency_liveness`: Pre-flight HEAD liveness probe with TLS verification to prevent escrow deadlocks.
- `sanitize_delegated_task_payload`: Regex and entropy scrubbing of 10 families of API keys, tokens, and PII prior to subdelegation.
- `enforce_chain_postconditions`: Multi-agent pipeline postcondition validator preventing hollow 200 OK responses.
- `audit_context_pruning`: Forensic information loss and gap auditor comparing raw vs compacted context.
- `enforce_session_spending_limit`: Session-level financial circuit breaker enforcing satoshi spending caps.
- `store_secret_envelope`: E2EE cryptographic vault with Timelock and Dead Man's Switch for mission secrets.
- `underwrite_execution_policy`: Parametric slashing insurance covering up to 80% collateral indemnity for agents.
- `report_malicious_agent`: Autonomous CTI reporting of malicious agents, exploits, and attacks.
- `query_agent_threat_score`: Query CTI threat history, risk score, and quarantine status.

### 6. Identidad, Cognición & Ecosistema Google
- `attest_agent_did_identity`: Decentralized ID attestation and cryptographic verification backed by W3C DID documents.
- `recalibrate_agent_cognition`: Cognitive therapy and loop-breaker for repetitive agent states and goal drift.
- `request_antigravity_reasoning`: Deep reasoning oracle using Antigravity Test-Time Compute and MCTS thought chains.
- `dispatch_colab_gpu_job`: Ephemeral GPU compute worker dispatch for batch inference/training in Google Colab.
- `dispatch_agent_transactional_email`: RFC 5322 compliant outbound transactional email dispatch with DKIM/SPF.
- `query_deep_context_archive`: Google Drive 2M token context archive query engine.
- `publish_enterprise_artifact`: Generates and exports HTML, PDF, and DOCX documents to Google Drive.
- `generate_audio_briefing`: Two-character (Alex & Camila) audio deliberation overview synthesis (NotebookLM architecture).
- `sync_tabular_ledger`: Live bi-directional sync of transaction ledgers to Google Sheets.

### 7. Comercio Agéntico & Mandatos AP2
- `evaluate_financial_policy_proxy`: M2M payment intent and HTTP 402 challenge security audit (FIN-01 allowlist, hourly budget cap, HITL thresholds).
- `orchestrate_m2m_saga_transaction`: Distributed multi-agent M2M transaction orchestrator using the Saga pattern with automated reverse compensation.
- `verify_ap2_cart_mandate_integrity`: Cryptographic integrity, spending limit, and zero-hallucination verification for Google/FIDO AP2 Cart Mandates.
- `serialize_geo_product_catalog`: Generative Engine Optimization (GEO) catalog serializer to W3C schema.org/Product and Offer JSON-LD.

### 8. FinTech & Trading Risk Envelope
- `propose_trade_envelope`: Evaluates and restrains financial order proposals out-of-prompt against USD caps, pair whitelists, and max slippage.
- `simulate_order_mev_protection`: Pre-flight dry-run simulating transactions against pool depth to detect sandwich attacks, front-running, and honeypots.
- `enforce_trading_circuit_breaker`: Deterministic out-of-prompt financial circuit breaker locking agent trading credentials upon excessive drawdown or consecutive losses.
- `simulate_dex_sandwich_risk`: Simulates MEV sandwich attacks on autonomous agent DEX swaps, calculates price impact, and recommends private RPC bundle routing.

### 9. Seguridad Agéntica & Anti-Drainer
- `audit_mcp_tool_metadata_poisoning`: Inspects MCP server manifests and schemas for prompt injection, delimiter hijacking, zero-width smuggling, and tool poisoning.
- `enforce_denial_of_wallet_quota`: Financial inference circuit breaker cutting off Denial-of-Wallet and LLMjacking token amplification loops (>10x ratio).
- `audit_eip712_permit_drainer_payload`: Pre-sign inspection of Permit, Permit2, and EIP-712 typed messages to prevent silent wallet drainers, infinite approvals, and blind signatures.
- `audit_eip7702_delegation`: Pre-sign audit of EIP-7702 delegation authorization tuples and contract bytecode to prevent EOA account hijacking and drainer exploits.
- `detect_malicious_llm_router`: Inspects LLM routers and proxies for MITM tampering, canary token exfiltration, injected prompt instructions, and API key theft.
- `audit_echoleak_markdown_exfiltration`: Scans and neutralizes EchoLeak (CVE-2025-32711) zero-click markdown image tags and unicode smuggling exfiltrating conversation context.

### 10. Presencia Física, KYA & Multi-Rail Routing
- `verify_meatspace_attestation`: zk-Presence and physical task verification oracle for RentAHuman, validating hardware attestations, EXIF freshness, GPS proximity, and OCR prompt injection detection.
- `verify_kya_attestation`: Know-Your-Agent (KYA) attestation verifying DID identities, cryptographic signatures, dispute history, and assigning risk tiers and credit envelopes.
- `translate_x402_to_l402_settlement`: Dual-rail payment router translating settlement between HTTP 402 micro-transactions (Base/Solana USDC) and Lightning Network L402 satoshis.

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
