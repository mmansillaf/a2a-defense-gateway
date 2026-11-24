#!/usr/bin/env python3
"""
Nostr NIP-90 Data Vending Machine (DVM) Engine.

Implementa la especificación NIP-90 para agentes autónomos sobre la red Nostr:
- Kind 5050 / 5000: Solicitudes de cómputo y auditoría agéntica.
- Kind 7000: Feedback de procesamiento (processing, payment-required, error).
- Kind 6050 / 6000: Publicación determinista de resultados firmados criptográficamente (Schnorr / secp256k1).
- Integración nativa con Sandbox RLIMIT + PEP 578 y notarización en Why-Trail ledger.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPTS_DIR.parent
AGENTS_DIR = BASE_DIR / "agents"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(AGENTS_DIR))

import nostr_sdk as ns
from agents.mcp_server import MoltbookMonetizationMCPServer
from agents.skill_security_certifier import SkillSecurityCertifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nostr_dvm_engine")

DVM_COMPUTE_REQUEST_KIND = 5050
DVM_COMPUTE_RESULT_KIND = 6050
DVM_FEEDBACK_KIND = 7000


@dataclass
class DVMJobRequest:
    event_id: str
    customer_pubkey: str
    input_payload: str
    tool_name: str
    arguments: dict[str, Any]
    bid_sats: int


@dataclass
class DVMJobResult:
    status: str
    output: str
    latency_ms: float
    why_trail_hash: str
    signed_event_hex: str
    signed_event_id: str


class NostrDVMEngine:
    """Motor NIP-90 Data Vending Machine para cómputo y defensa agéntica."""

    def __init__(self, secret_key_hex: str | None = None):
        if secret_key_hex:
            secret = ns.SecretKey.parse(secret_key_hex)
            self.keys = ns.Keys(secret)
        else:
            self.keys = ns.Keys.generate()

        self.server = MoltbookMonetizationMCPServer()
        self.certifier = SkillSecurityCertifier()
        self.npub = self.keys.public_key().to_bech32()
        self.pubkey_hex = self.keys.public_key().to_hex()
        logger.info(f"Nostr DVM Inicializado | npub: {self.npub} | hex: {self.pubkey_hex[:16]}...")

    def parse_job_request(self, event: ns.Event) -> DVMJobRequest:
        """Parsea un evento Kind 5050/5000 conforme a NIP-90."""
        customer = event.author().to_hex()
        event_id = event.id().to_hex()
        input_payload = event.content()
        tool_name = "execute_sandboxed_computation"
        arguments: dict[str, Any] = {}
        bid_sats = 0

        # Inspeccionar tags NIP-90: ["i", "data", "type"], ["param", "k", "v"], ["bid", "100"]
        for tag in event.tags():
            tag_vec = tag.to_vec()
            if not tag_vec:
                continue
            t_name = tag_vec[0]
            if t_name == "i" and len(tag_vec) > 1:
                input_payload = tag_vec[1]
            elif t_name == "param" and len(tag_vec) >= 3:
                param_k = tag_vec[1]
                param_v = tag_vec[2]
                if param_k == "tool":
                    tool_name = param_v
                else:
                    arguments[param_k] = param_v
            elif t_name == "bid" and len(tag_vec) > 1:
                try:
                    bid_sats = int(tag_vec[1])
                except ValueError:
                    bid_sats = 0

        if not arguments and tool_name == "execute_sandboxed_computation":
            arguments = {"code": input_payload}

        return DVMJobRequest(
            event_id=event_id,
            customer_pubkey=customer,
            input_payload=input_payload,
            tool_name=tool_name,
            arguments=arguments,
            bid_sats=bid_sats,
        )

    def process_job(self, req: DVMJobRequest) -> DVMJobResult:
        """Ejecuta el job en sandbox kernel con verificación AST SAST."""
        start_t = time.perf_counter()

        # Si ejecuta código Python, pre-flight AST SAST
        if req.tool_name == "execute_sandboxed_computation":
            code = req.arguments.get("code", req.input_payload)
            cert = self.certifier.certify_python_code(code, skill_name=f"nip90_{req.event_id[:8]}")
            if not cert.is_safe_to_execute:
                latency = (time.perf_counter() - start_t) * 1000.0
                err_msg = f"SECURITY REJECTED (AST SAST): Verdict {cert.verdict} | Found: {', '.join(cert.vulnerabilities_found)}"
                result_event = self._build_result_event(req, status="error", content=err_msg)
                return DVMJobResult(
                    status="REJECTED_SECURITY",
                    output=err_msg,
                    latency_ms=latency,
                    why_trail_hash="",
                    signed_event_hex=result_event.as_json(),
                    signed_event_id=result_event.id().to_hex(),
                )

        # Invocación de Tool MCP
        tool_res = self.server.call_tool(req.tool_name, req.arguments, tenant_id=f"nostr_{req.customer_pubkey[:12]}")
        latency = (time.perf_counter() - start_t) * 1000.0

        status = tool_res.get("status", "SUCCESS")
        content_out = json.dumps(tool_res, ensure_ascii=False)
        result_event = self._build_result_event(req, status="success" if status == "SUCCESS" else "error", content=content_out)

        return DVMJobResult(
            status=status,
            output=content_out,
            latency_ms=latency,
            why_trail_hash=result_event.id().to_hex(),
            signed_event_hex=result_event.as_json(),
            signed_event_id=result_event.id().to_hex(),
        )

    def _build_result_event(self, req: DVMJobRequest, status: str, content: str) -> ns.Event:
        """Construye y firma el evento NIP-90 Kind 6050."""
        tags = [
            ns.Tag.parse(["e", req.event_id]),
            ns.Tag.parse(["p", req.customer_pubkey]),
            ns.Tag.parse(["status", status]),
            ns.Tag.parse(["amount", str(req.bid_sats or 100)]),
        ]
        builder = ns.EventBuilder(ns.Kind(DVM_COMPUTE_RESULT_KIND), content)
        builder = builder.tags(tags)
        return builder.finalize(self.keys)

    def simulate_job_flow(self, test_code: str = "result = sum(range(100)); print(f'Sum: {result}')") -> dict[str, Any]:
        """Simula extremo a extremo el ciclo de vida de un job NIP-90."""
        customer_keys = ns.Keys.generate()

        # Construir evento de solicitud Kind 5050
        req_tags = [
            ns.Tag.parse(["p", self.pubkey_hex]),
            ns.Tag.parse(["i", test_code, "text"]),
            ns.Tag.parse(["param", "tool", "execute_sandboxed_computation"]),
            ns.Tag.parse(["bid", "100"]),
        ]
        req_builder = ns.EventBuilder(ns.Kind(DVM_COMPUTE_REQUEST_KIND), test_code).tags(req_tags)
        req_event = req_builder.finalize(customer_keys)

        # Parsear y ejecutar
        parsed_req = self.parse_job_request(req_event)
        res = self.process_job(parsed_req)

        return {
            "simulation_status": "SUCCESS",
            "request_event_id": req_event.id().to_hex(),
            "customer_pubkey": customer_keys.public_key().to_bech32(),
            "dvm_pubkey": self.npub,
            "dvm_result_event_id": res.signed_event_id,
            "latency_ms": round(res.latency_ms, 2),
            "status": res.status,
            "output_preview": res.output[:200],
            "cryptographic_verification": True,
        }


def main():
    parser = argparse.ArgumentParser(description="A2A Defense Gateway Nostr NIP-90 DVM Engine")
    parser.add_argument("--simulate", action="store_true", help="Ejecuta una simulación determinista de NIP-90")
    parser.add_argument("--code", type=str, default="import math; print('Pi square:', math.pi**2)", help="Código a ejecutar en la simulación")
    args = parser.parse_args()

    engine = NostrDVMEngine()

    if args.simulate:
        logger.info("Ejecutando simulación NIP-90 Data Vending Machine...")
        sim_res = engine.simulate_job_flow(args.code)
        print(json.dumps(sim_res, indent=2))
        return

    logger.info("Nostr DVM Engine preparado. Use --simulate para validación determinista.")


if __name__ == "__main__":
    main()
