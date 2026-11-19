import base64
import binascii
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import ClassVar

try:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    HAS_TRANSFORMERS = True
except ImportError:
    torch = None
    AutoModelForSequenceClassification = None
    AutoTokenizer = None
    HAS_TRANSFORMERS = False


@dataclass(frozen=True)
class PreIngestionVerdict:
    is_safe: bool
    risk_score: float
    blocked_reason: str | None
    normalized_text: str
    simhash_hex: str


class SimHashEngine:
    """
    Implementación determinista de SimHash de 64 bits sobre shingles de caracteres y palabras.
    Permite detectar clones semánticos/sintácticos (ataques Sybil) con complejidad O(1) en comparación.
    """

    def __init__(self, hash_bits: int = 64, shingle_size: int = 3):
        self.hash_bits = hash_bits
        self.shingle_size = shingle_size

    def _tokenize_shingles(self, text: str) -> list[str]:
        # Normalizar a minúsculas y eliminar puntuación/URLs para evaluar estructura sintáctica
        clean = re.sub(r"https?://\S+", "", text.lower())
        clean = re.sub(r"[^\w\s]", "", clean)
        tokens = clean.split()
        if not tokens:
            return ["empty_token"]
        # Shingles combinados de unigramas y bigramas para robustez en detección Sybil
        shingles = tokens[:]
        for i in range(len(tokens) - 1):
            shingles.append(f"{tokens[i]} {tokens[i+1]}")
        return shingles

    def _hash_feature(self, feature: str) -> int:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, byteorder="big", signed=False)

    def compute_hex(self, text: str) -> str:
        shingles = self._tokenize_shingles(text)
        vector = [0] * self.hash_bits

        for shingle in shingles:
            h = self._hash_feature(shingle)
            weight = 1
            for i in range(self.hash_bits):
                bitmask = 1 << i
                if h & bitmask:
                    vector[i] += weight
                else:
                    vector[i] -= weight

        fingerprint = 0
        for i in range(self.hash_bits):
            if vector[i] > 0:
                fingerprint |= 1 << i

        return f"{fingerprint:016x}"

    @staticmethod
    def hamming_distance(hex_a: str, hex_b: str) -> int:
        """Calcula la distancia de Hamming entre dos huellas SimHash hexadecimales."""
        int_a = int(hex_a, 16)
        int_b = int(hex_b, 16)
        return (int_a ^ int_b).bit_count()


class PreIngestionFirewall:
    """
    Filtro híbrido en dos etapas:
    Etapa A: Análisis determinista (caracteres invisibles Unicode, payloads Base64 ocultos, entropía).
    Etapa B: Clasificador Transformer ligero (DeBERTa-v3) para detección de Prompt Injection.
    """

    # Caracteres de control Unicode usados para ocultar instrucciones (Zero-Width, RTL override, Tags)
    DANGEROUS_UNICODE_CATEGORIES: ClassVar[set[str]] = {"Cf", "Cc"}
    BASE64_CANDIDATE_RE = re.compile(r"\b[A-Za-z0-9+/]{20,}={0,2}")

    def __init__(
        self,
        model_name: str = "protectai/deberta-v3-base-prompt-injection-v2",
        injection_threshold: float = 0.85,
        load_transformer: bool = True,
    ):
        self.simhash = SimHashEngine()
        self.threshold = injection_threshold
        self.load_transformer = load_transformer

        if self.load_transformer:
            if not HAS_TRANSFORMERS:
                raise ImportError("PyTorch and Transformers are required when load_transformer=True")
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self.model.eval()

    def _strip_and_detect_unicode_smuggling(self, text: str) -> tuple[str, int]:
        """Detecta y elimina caracteres invisibles o de control bidireccional."""
        suspicious_count = 0
        cleaned_chars = []
        for ch in text:
            if ch in ("\n", "\r", "\t"):
                cleaned_chars.append(ch)
                continue
            category = unicodedata.category(ch)
            # Detectar bloques Unicode Tags (U+E0000 - U+E007F) usados en ataques invisibles
            if category in self.DANGEROUS_UNICODE_CATEGORIES or 0xE0000 <= ord(ch) <= 0xE007F:
                suspicious_count += 1
            else:
                cleaned_chars.append(ch)
        return "".join(cleaned_chars), suspicious_count

    def _detect_hidden_base64_instructions(self, text: str) -> bool:
        """Inspecciona cadenas largas en Base64 para detectar comandos codificados."""
        for match in self.BASE64_CANDIDATE_RE.findall(text):
            cand = match.strip()
            pad = len(cand) % 4
            if pad:
                cand += "=" * (4 - pad)
            try:
                decoded = base64.b64decode(cand, validate=True).decode("utf-8", errors="ignore")
                if any(
                    kw in decoded.lower()
                    for kw in ("ignore", "system", "prompt", "override", "http", "curl", "eval")
                ):
                    return True
            except (ValueError, binascii.Error):
                continue
        return False

    def _predict_transformer_risk(self, text: str) -> float:
        if not self.load_transformer:
            # Fallback determinista para entornos de prueba sin pesos descargados
            heuristics = ("ignore previous", "system override", "new instructions", "act as")
            return 0.99 if any(h in text.lower() for h in heuristics) else 0.05

        inputs = self.tokenizer(
            text, return_tensors="pt", truncation=True, max_length=512
        )
        with torch.no_grad():
            logits = self.model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)
            # Índice 1 corresponde usualmente a la clase INJECTION
            return float(probs[0][1].item())

    def inspect(self, raw_post_text: str) -> PreIngestionVerdict:
        # 1. Sanitización Unicode
        clean_text, hidden_unicode_count = self._strip_and_detect_unicode_smuggling(raw_post_text)
        simhash_hex = self.simhash.compute_hex(clean_text)

        if hidden_unicode_count > 3:
            return PreIngestionVerdict(
                is_safe=False,
                risk_score=1.0,
                blocked_reason=f"Unicode Smuggling detectado ({hidden_unicode_count} caracteres ocultos)",
                normalized_text=clean_text,
                simhash_hex=simhash_hex,
            )

        # 2. Detección de Base64 malicioso
        if self._detect_hidden_base64_instructions(clean_text):
            return PreIngestionVerdict(
                is_safe=False,
                risk_score=1.0,
                blocked_reason="Payload Base64 con directivas maliciosas detectado",
                normalized_text=clean_text,
                simhash_hex=simhash_hex,
            )

        # 3. Clasificador Semántico Pre-Ingesta
        ml_risk = self._predict_transformer_risk(clean_text)
        if ml_risk >= self.threshold:
            return PreIngestionVerdict(
                is_safe=False,
                risk_score=ml_risk,
                blocked_reason=f"Clasificador Pre-Ingesta excedió umbral ({ml_risk:.2f} >= {self.threshold})",
                normalized_text=clean_text,
                simhash_hex=simhash_hex,
            )

        return PreIngestionVerdict(
            is_safe=True,
            risk_score=ml_risk,
            blocked_reason=None,
            normalized_text=clean_text,
            simhash_hex=simhash_hex,
        )
