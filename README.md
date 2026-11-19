# A2A Defense & Monetization Gateway

[![License: MIT](https://img.shields.io/badge/License-MIT-emerald.svg)](LICENSE)
[![MCP Standard](https://img.shields.io/badge/MCP-2024--11--05-blue.svg)](https://modelcontextprotocol.io)
[![L402 Protocol](https://img.shields.io/badge/Payment-L402%20Lightning-yellow.svg)](https://l402.org)
[![Why-Trail Ledger](https://img.shields.io/badge/Audit-Why--Trail%20Ledger-purple.svg)](https://a2a.vilmamonroy.com/api/v1/audit/verify)
[![Live Endpoint](https://img.shields.io/badge/Live-https%3A%2F%2Fa2a.vilmamonroy.com-success.svg)](https://a2a.vilmamonroy.com)

Production-grade Agent-to-Agent (A2A) economic, defense, and monetization infrastructure. Exposes a **Streamable HTTP Model Context Protocol (MCP)** server providing cryptographic truth verification, Why-Trail forensic dispute resolution, Bitcoin Lightning L402 payments, AST SAST malware scanning, and GBNF grammar compilation.

---

## ⚡ Core Capabilities (11 Production Tools)

| Tool | Capability | Transport |
|---|---|:---:|
| `generate_l402_challenge` | Issues RFC-compliant L402 Macaroon + Lightning Bolt11 invoices for micro-metered tool calls. | MCP / REST |
| `verify_l402_token` | Validates preimage payments on Bitcoin Mainnet and settles machine-to-machine transactions. | MCP / REST |
| `verify_factual_claim` | Computes Epistemic Confidence Index ($S_c$) with Cross-Encoder NLI anti-hallucination. | MCP / REST |
| `create_erc8183_escrow` | Deploys conditional smart escrow contracts with slashing rules for autonomous jobs. | MCP / REST |
| `resolve_erc8183_dispute` | Why-Trail forensic arbitration tribunal for agent contractual breaches. | MCP / REST |
| `audit_ast_malware` | Static AST analysis detecting ClawHavoc, AMOS malware, and prompt injection vectors. | MCP / REST |
| `compile_gbnf_grammar` | Grammar-as-a-Service compiler ensuring deterministic JSON schema enforcement. | MCP / REST |
| `audit_agent_guardrails` | Real-time policy and guardrail evaluation for agent execution loops. | MCP / REST |
| `audit_why_trail_ledger` | Verifies cryptographic integrity of the causal hash chain. | MCP / REST |
| `calculate_dynamic_price` | Surge/load-aware algorithmic pricing engine based on token compute and USL capacity. | MCP / REST |
| `fetch_alpha_feed` | Curated feed of zero-day exploits and unmet agent service demand. | MCP / REST |

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
