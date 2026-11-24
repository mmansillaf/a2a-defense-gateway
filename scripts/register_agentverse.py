#!/usr/bin/env python3
"""
Registrador oficial de A2A Defense Gateway en Agentverse / ASI:One.
"""

import os
import sys
from pathlib import Path

# Cargar variables de entorno desde .env
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from uagents_core.utils.registration import (
    AgentverseRequestError,
    RegistrationRequestCredentials,
    register_chat_agent,
)


def main() -> None:
    api_key = os.environ.get("AGENTVERSE_KEY")
    seed_phrase = os.environ.get("AGENT_SEED_PHRASE")

    if not api_key or not seed_phrase:
        print("[ERROR] Falta AGENTVERSE_KEY o AGENT_SEED_PHRASE en el entorno.", file=sys.stderr)
        sys.exit(1)

    credentials = RegistrationRequestCredentials(
        agentverse_api_key=api_key,
        agent_seed_phrase=seed_phrase,
    )

    print("Iniciando registro en Agentverse / ASI:One...")
    try:
        success = register_chat_agent(
            name="A2A Defense Gateway",
            endpoint="https://a2a.vilmamonroy.com",
            active=True,
            credentials=credentials,
            description="L402 Lightning payments, Why-Trail forensic court, and AST security oracle for autonomous AI agents.",
            readme="""# A2A Defense & Monetization Gateway

Production Agent-to-Agent (A2A) infrastructure providing:
- **L402 Lightning Micropayments**: Instant Bitcoin Lightning settlement for machine-to-machine inference.
- **Why-Trail Forensic Court**: Immutable causal ledger with cryptographic audit trail.
- **AST SAST Malware Scanner**: Detection of malicious payloads and prompt injections in agent tool definitions.
- **GBNF Grammar Compiler**: Grammar-as-a-Service for hallucination-free structured JSON outputs.
- **ERC-8183 Dynamic Escrow**: Slashing and conditional fund releases for autonomous agent services.

MCP Endpoint: `https://a2a.vilmamonroy.com/mcp`
Landing & Docs: `https://a2a.vilmamonroy.com`
""",
            metadata={
                "categories": ["finance", "security", "research", "ai"],
                "is_public": "True",
            },
        )
        print(f"[SUCCESS] Agente registrado exitosamente en Agentverse! active={success}")
    except AgentverseRequestError as exc:
        print(f"[FAIL] Error en la solicitud a Agentverse: {exc}", file=sys.stderr)
        if hasattr(exc, "from_exc"):
            print(f"Detalle subyacente: {exc.from_exc}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:
        print(f"[FAIL] Excepción inesperada: {exc}", file=sys.stderr)
        sys.exit(3)

if __name__ == "__main__":
    main()
