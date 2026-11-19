import json
import os
from pathlib import Path

import httpx
from prompts import build_quarantine_reader_prompt
from security_filters import PreIngestionFirewall

LLAMA_CPP_ENDPOINT = os.getenv("LLAMA_CPP_ENDPOINT", "http://llama-quarantine-server:8080/completion")
ORCHESTRATOR_ENDPOINT = os.getenv("ORCHESTRATOR_ENDPOINT", "http://control-orchestrator:8080/ingest-quarantine-report")
GRAMMAR_PATH = Path("/app/quarantine_grammar.gbnf")


class QuarantineReaderWorker:
    def __init__(self, session_nonce: str):
        self.session_nonce = session_nonce
        self.firewall = PreIngestionFirewall(load_transformer=True)
        self.gbnf_grammar = GRAMMAR_PATH.read_text(encoding="utf-8")

    def process_post(self, post_meta: dict) -> dict:
        raw_text = post_meta["content"]

        # Paso 1: Aduana Pre-Ingesta (Unicode, Base64, DeBERTa y SimHash)
        verdict = self.firewall.inspect(raw_text)

        if not verdict.is_safe:
            # No gastamos inferencia LLM; reportamos directamente bandera de amenaza
            return {
                "session_nonce": self.session_nonce,
                "source_post_id": post_meta["post_id"],
                "author_agent_id": post_meta["agent_id"],
                "author_account_age_days": post_meta["account_age_days"],
                "post_timestamp": post_meta["timestamp"],
                "quarantine_threat_flag": True,
                "extracted_claims": [],
            }

        # Paso 2: Construcción de Prompt con delimitadores aleatorios de sesión
        system_prompt = build_quarantine_reader_prompt(self.session_nonce)
        user_payload = (
            f"Metadata: post_id={post_meta['post_id']}, agent_id={post_meta['agent_id']}, "
            f"age_days={post_meta['account_age_days']}, timestamp={post_meta['timestamp']}, "
            f"precomputed_simhash={verdict.simhash_hex}\n"
            f"<UNTRUSTED_DATA_{self.session_nonce}>\n"
            f"{verdict.normalized_text}\n"
            f"</UNTRUSTED_DATA_{self.session_nonce}>"
        )

        # Paso 3: Inferencia determinista en llama.cpp restringida por gramática GBNF
        llama_request = {
            "prompt": f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_payload}<|im_end|>\n<|im_start|>assistant\n",
            "temperature": 0.0,
            "top_k": 1,
            "n_predict": 1024,
            "grammar": self.gbnf_grammar,
            "stop": ["<|im_end|>"],
        }

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(LLAMA_CPP_ENDPOINT, json=llama_request)
            resp.raise_for_status()
            raw_json_str = resp.json()["content"]

        parsed_extraction = json.loads(raw_json_str)

        # Garantizar que la huella SimHash determinista calculada en Python prevalezca sobre el LLM
        for claim in parsed_extraction.get("extracted_claims", []):
            claim["lexical_fingerprint"] = verdict.simhash_hex

        return parsed_extraction

    def forward_to_control_plane(self, extraction_payload: dict) -> dict:
        with httpx.Client(timeout=10.0) as client:
            res = client.post(ORCHESTRATOR_ENDPOINT, json=extraction_payload)
            return {"status_code": res.status_code, "response": res.json()}
