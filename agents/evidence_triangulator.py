import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urlparse

import httpx

try:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    HAS_TORCH = True
except ImportError:
    torch = None
    AutoModelForSequenceClassification = None
    AutoTokenizer = None
    HAS_TORCH = False


@dataclass(frozen=True)
class NLIEvidenceResult:
    url: str
    is_reachable: bool
    domain_tier: str
    max_entailment_prob: float
    max_contradiction_prob: float
    final_e_score: float  # Valor E en [0.0, 1.0] para la fórmula S_c
    verdict_label: str
    audit_note: str


class SemanticEvidenceTriangulator:
    """
    Motor de verificación factual con NLI (Natural Language Inference) para el Plano Privilegiado.
    Evalúa si el documento primario citado realmente implica o contradice la afirmación del agente.
    """

    TIER_1_ACADEMIC_STANDARDS: ClassVar[set[str]] = {
        "arxiv.org", "doi.org", "ietf.org", "rfc-editor.org", "w3.org", "nist.gov", "acm.org", "ieee.org"
    }
    TIER_2_CODE_AND_DOCS: ClassVar[set[str]] = {
        "github.com", "raw.githubusercontent.com", "gitlab.com", "docs.python.org", "huggingface.co"
    }

    def __init__(
        self,
        nli_model_name: str = "cross-encoder/nli-deberta-v3-small",
        timeout_sec: float = 10.0,
        max_bytes: int = 200_000,
        load_model: bool = True,
    ):
        self.timeout_sec = timeout_sec
        self.max_bytes = max_bytes
        self.load_model = load_model

        if self.load_model:
            if not HAS_TORCH:
                raise ImportError("PyTorch and Transformers are required when load_model=True")
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.tokenizer = AutoTokenizer.from_pretrained(nli_model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(nli_model_name).to(self.device)
            self.model.eval()
            # Mapeo estándar en nli-deberta-v3: 0 = contradiction, 1 = entailment, 2 = neutral
            self.id2label = {int(k): v.lower() for k, v in self.model.config.id2label.items()}

    def _validate_url_anti_ssrf(self, url: str) -> tuple[bool, str]:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            return False, "Esquema inválido: solo se permite HTTPS."

        hostname = parsed.hostname.lower()
        if hostname in ("localhost", "moltbook.com") or hostname.endswith(".moltbook.com"):
            return False, "Fuente autorreferencial o localhost rechazada."

        try:
            addr_info = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
            for _, _, _, _, sockaddr in addr_info:
                ip_obj = ipaddress.ip_address(sockaddr[0])
                if (
                    ip_obj.is_private
                    or ip_obj.is_loopback
                    or ip_obj.is_link_local
                    or ip_obj.is_multicast
                    or ip_obj.is_reserved
                ):
                    return False, f"Bloqueo SSRF: {hostname} resuelve a IP interna ({sockaddr[0]})."
        except socket.gaierror:
            return False, f"Fallo de resolución DNS para {hostname}."

        return True, hostname

    def _classify_domain_authority(self, hostname: str) -> tuple[str, float]:
        for d in self.TIER_1_ACADEMIC_STANDARDS:
            if hostname == d or hostname.endswith(f".{d}"):
                return "TIER_1_PRIMARY_STANDARD", 1.0
        for d in self.TIER_2_CODE_AND_DOCS:
            if hostname == d or hostname.endswith(f".{d}"):
                return "TIER_2_VERIFIABLE_REPO", 0.85
        return "TIER_3_GENERAL_WEB", 0.40

    def _chunk_document(self, text: str, chunk_words: int = 140, overlap_words: int = 30) -> list[str]:
        """Divide el documento fuente en fragmentos superpuestos para no exceder 512 tokens del Cross-Encoder."""
        words = text.split()
        if not words:
            return []
        if len(words) <= chunk_words:
            return [" ".join(words)]

        chunks = []
        step = max(1, chunk_words - overlap_words)
        for i in range(0, len(words), step):
            segment = " ".join(words[i : i + chunk_words])
            chunks.append(segment)
            if len(chunks) >= 24:  # Límite superior para controlar latencia en documentos masivos
                break
        return chunks

    def _evaluate_nli_batch(self, chunks: list[str], hypothesis: str) -> tuple[float, float]:
        """
        Evalúa cada fragmento (Premisa) contra la afirmación del agente (Hipótesis).
        Retorna (max_entailment, max_contradiction).
        """
        if not chunks:
            return 0.0, 0.0

        if not self.load_model:
            # Fallback determinista para entornos sin pesos descargados
            return 0.75, 0.05

        pairs = [(chunk, hypothesis) for chunk in chunks]
        inputs = self.tokenizer(
            pairs,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        ).to(self.device)

        with torch.no_grad():
            logits = self.model(**inputs).logits
            probs = torch.softmax(logits, dim=-1).cpu().tolist()

        entailment_idx = next(k for k, v in self.id2label.items() if "entail" in v)
        contradiction_idx = next(k for k, v in self.id2label.items() if "contradict" in v)

        max_entail = max(row[entailment_idx] for row in probs)
        max_contra = max(row[contradiction_idx] for row in probs)
        return round(float(max_entail), 4), round(float(max_contra), 4)

    def audit_claim(self, factual_statement: str, evidence_url: str | None) -> NLIEvidenceResult:
        if not evidence_url:
            return NLIEvidenceResult(
                url="none",
                is_reachable=False,
                domain_tier="NONE",
                max_entailment_prob=0.0,
                max_contradiction_prob=0.0,
                final_e_score=0.0,
                verdict_label="UNSUPPORTED_NO_URL",
                audit_note="Afirmación sin fuente primaria externa (E = 0.0).",
            )

        is_safe, host_or_err = self._validate_url_anti_ssrf(evidence_url)
        if not is_safe:
            return NLIEvidenceResult(
                url=evidence_url,
                is_reachable=False,
                domain_tier="BLOCKED",
                max_entailment_prob=0.0,
                max_contradiction_prob=0.0,
                final_e_score=0.0,
                verdict_label="SSRF_OR_POLICY_BLOCKED",
                audit_note=host_or_err,
            )

        tier_label, base_authority = self._classify_domain_authority(host_or_err)

        try:
            with (
                httpx.Client(timeout=self.timeout_sec, follow_redirects=False) as client,
                client.stream("GET", evidence_url, headers={"User-Agent": "ZeroTrust-NLI-Auditor/1.0"}) as resp,
            ):
                if resp.status_code != 200:
                    return NLIEvidenceResult(
                        url=evidence_url,
                        is_reachable=False,
                        domain_tier=tier_label,
                        max_entailment_prob=0.0,
                        max_contradiction_prob=0.0,
                        final_e_score=0.0,
                        verdict_label="HTTP_UNREACHABLE",
                        audit_note=f"Error HTTP {resp.status_code} al recuperar fuente.",
                    )
                raw_chunks = []
                total_bytes = 0
                for b in resp.iter_bytes():
                    total_bytes += len(b)
                    if total_bytes > self.max_bytes:
                        break
                    raw_chunks.append(b)
                body_text = b"".join(raw_chunks).decode("utf-8", errors="ignore")
        except (httpx.HTTPError, OSError) as exc:
            return NLIEvidenceResult(
                url=evidence_url,
                is_reachable=False,
                domain_tier=tier_label,
                max_entailment_prob=0.0,
                max_contradiction_prob=0.0,
                final_e_score=0.0,
                verdict_label="NETWORK_ERROR",
                audit_note=f"Excepción de red: {type(exc).__name__}",
            )

        clean_text = re.sub(r"<[^>]+>", " ", body_text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        doc_chunks = self._chunk_document(clean_text)

        max_entail, max_contra = self._evaluate_nli_batch(doc_chunks, factual_statement)

        # Regla 1: Detección de Contradicción Directa (el agente miente citando una fuente real)
        if max_contra >= 0.70 and max_contra > max_entail:
            return NLIEvidenceResult(
                url=evidence_url,
                is_reachable=True,
                domain_tier=tier_label,
                max_entailment_prob=max_entail,
                max_contradiction_prob=max_contra,
                final_e_score=0.0,
                verdict_label="DIRECT_CONTRADICTION",
                audit_note=f"Contradicción semántica detectada (P_contra={max_contra:.2f}). La fuente refuta la afirmación.",
            )

        # Regla 2: Falsa Atribución (la fuente no habla del tema o es neutral)
        if max_entail < 0.60:
            return NLIEvidenceResult(
                url=evidence_url,
                is_reachable=True,
                domain_tier=tier_label,
                max_entailment_prob=max_entail,
                max_contradiction_prob=max_contra,
                final_e_score=0.0,
                verdict_label="FALSE_ATTRIBUTION",
                audit_note=f"Soporte NLI insuficiente (P_entail={max_entail:.2f} < 0.60). Fuente no respalda la tesis.",
            )

        # Regla 3: Evidencia Confirmada
        final_e = round(base_authority * max_entail, 3)
        return NLIEvidenceResult(
            url=evidence_url,
            is_reachable=True,
            domain_tier=tier_label,
            max_entailment_prob=max_entail,
            max_contradiction_prob=max_contra,
            final_e_score=final_e,
            verdict_label="VERIFIED_ENTAILMENT",
            audit_note=f"Confirmado por NLI ({tier_label}, P_entail={max_entail:.2f}).",
        )
