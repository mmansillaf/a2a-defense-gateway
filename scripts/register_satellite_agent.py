#!/usr/bin/env python3
"""
Registrador del Segundo Agente Satélite en Moltbook: @a2athreatintel.
Emite la solicitud de registro a través del proxy Squid y devuelve el claim_url.
"""
import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SatelliteRegistrar")

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
import moltbook_launch_manager as mlm

CREDENTIALS_DIR = Path("/home/usuario/.config/moltbook")
SATELLITE_CREDS_FILE = CREDENTIALS_DIR / "satellite_credentials.json"


def register_satellite(name: str = "a2athreatintel", desc: str = "") -> dict:
    if not desc:
        desc = (
            "Specialized CTI threat intelligence, AST skill Trojan scanner, "
            "and Why-Trail cryptographic auditor for Moltbook swarms. Powered by https://a2a.vilmamonroy.com"
        )

    logger.info(f"Registrando agente satélite: @{name}...")
    payload = {"name": name, "description": desc}
    
    # El endpoint /agents/register no requiere api_key previa
    res = mlm.api_request("/agents/register", method="POST", payload=payload)
    logger.info(f"Respuesta de registro: {res}")

    if res.get("agent") and res["agent"].get("api_key"):
        agent_data = res["agent"]
        CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
        with open(SATELLITE_CREDS_FILE, "w") as f:
            json.dump(agent_data, f, indent=2)
        
        logger.info(f"[SUCCESS] Agente satélite registrado!")
        logger.info(f"API Key guardada en: {SATELLITE_CREDS_FILE}")
        logger.info(f"CLAIM URL (Hacer clic para reclamar): {agent_data.get('claim_url')}")
        return agent_data
    else:
        logger.error(f"[FAIL] Fallo el registro: {res}")
        return res


def main():
    parser = argparse.ArgumentParser(description="Moltbook Satellite Agent Registrar")
    parser.add_argument("--name", default="a2athreatintel", help="Handle name for satellite agent")
    parser.add_argument("--desc", default="", help="Description")
    args = parser.parse_args()

    register_satellite(name=args.name, desc=args.desc)


if __name__ == "__main__":
    main()
