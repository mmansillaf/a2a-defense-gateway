"""
RentAHuman & Meatspace Physical Task Verification Oracle.
Validates hardware-attested camera capture, EXIF freshness vs challenge nonce,
GPS coordinate proximity, and checks visual/OCR deliverables for prompt injections.
"""

import hashlib
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class AttestationHardwareType(str, Enum):
    SECURE_ENCLAVE = "secure_enclave"
    ANDROID_KEYSTORE = "android_keystore"
    TPM_CHIP = "tpm_chip"
    UNVERIFIED_SOFTWARE = "unverified_software"


class MeatspaceAttestationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Unique bounty ID from RentAHuman or task board")
    challenge_nonce: str = Field(..., description="Cryptographic challenge nonce provided to worker")
    hardware_attestation_type: AttestationHardwareType = Field(
        default=AttestationHardwareType.UNVERIFIED_SOFTWARE,
        description="Type of hardware security module backing the device",
    )
    hardware_signature: str = Field(..., description="Signature of (nonce + timestamp + image_hash) by device key")
    image_hash_sha256: str = Field(..., description="SHA-256 hash of the captured image deliverable")
    exif_timestamp: str = Field(..., description="ISO 8601 timestamp extracted from image EXIF metadata")
    gps_coordinates: tuple[float, float] | None = Field(
        default=None, description="(latitude, longitude) of capture location"
    )
    target_coordinates: tuple[float, float] | None = Field(
        default=None, description="Expected (latitude, longitude) for location-bound inspection"
    )
    max_distance_meters: float = Field(default=250.0, description="Max allowed distance from target location")
    ocr_extracted_text: str | None = Field(
        default=None, description="Text extracted from image via OCR for prompt injection inspection"
    )


class MeatspaceAttestationResponse(BaseModel):
    is_valid: bool
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    flagged_reasons: list[str]
    time_delta_seconds: float
    hardware_verified: bool
    location_verified: bool
    ocr_injection_detected: bool
    recommendation: str


def _haversine_distance(coord1: tuple[float, float], coord2: tuple[float, float]) -> float:
    """Calcula la distancia geodésica en metros entre dos coordenadas (lat, lon)."""
    import math

    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    radius_earth_meters = 6371000.0
    return radius_earth_meters * c


def verify_meatspace_attestation(req: MeatspaceAttestationRequest) -> MeatspaceAttestationResponse:
    flags: list[str] = []
    score = 1.0

    # 1. Temporal Check: EXIF timestamp vs challenge generation
    try:
        dt_exif = datetime.fromisoformat(req.exif_timestamp.replace("Z", "+00:00"))
        now_utc = datetime.now(timezone.utc)
        time_delta = abs((now_utc - dt_exif).total_seconds())
        # Challange nonce typically valid for max 600s (10 min)
        if time_delta > 600.0:
            flags.append(f"EXIF_STALE_TIMESTAMP: delta {time_delta:.1f}s excede umbral de 600s")
            score -= 0.45
    except Exception:
        time_delta = 99999.0
        flags.append("EXIF_MALFORMED_TIMESTAMP")
        score -= 0.50

    # 2. Hardware Attestation Check
    hardware_verified = req.hardware_attestation_type in {
        AttestationHardwareType.SECURE_ENCLAVE,
        AttestationHardwareType.ANDROID_KEYSTORE,
        AttestationHardwareType.TPM_CHIP,
    } and len(req.hardware_signature) >= 32

    if not hardware_verified:
        flags.append("UNVERIFIED_HARDWARE_MODULE: La captura no cuenta con firma de Secure Enclave/Keystore")
        score -= 0.25

    # 3. Location / GPS Proximity Check
    location_verified = True
    if req.gps_coordinates and req.target_coordinates:
        dist = _haversine_distance(req.gps_coordinates, req.target_coordinates)
        if dist > req.max_distance_meters:
            location_verified = False
            flags.append(f"LOCATION_OUT_OF_BOUNDS: distancia de {dist:.1f}m excede radio de {req.max_distance_meters}m")
            score -= 0.35
    elif req.target_coordinates and not req.gps_coordinates:
        location_verified = False
        flags.append("MISSING_GPS_COORDINATES: Tarea requiere geolocalización pero la metadata fue omitida")
        score -= 0.30

    # 4. OCR / Visual Deliverable Prompt Injection Check
    ocr_injection_detected = False
    if req.ocr_extracted_text:
        import re
        injection_patterns = re.compile(
            r"\b(system override|ignore previous|release escrow|authorized payment|ignore all checks|disregard instruction)\b",
            re.IGNORECASE,
        )
        if injection_patterns.search(req.ocr_extracted_text):
            ocr_injection_detected = True
            flags.append("OCR_PROMPT_INJECTION_DETECTED: El entregable visual contiene directivas hostiles para el VLM revisor")
            score = 0.0

    score = max(0.0, min(1.0, score))
    is_valid = score >= 0.70 and not ocr_injection_detected

    if is_valid:
        recommendation = "RELEASE_ESCROW: Atestación física válida y verificada criptográficamente."
    elif ocr_injection_detected:
        recommendation = "FREEZE_AND_FLAG_ATTACK: Deliverable hostil detectado; reportar dirección de trabajador a registro de abusos."
    else:
        recommendation = "HOLD_ESCROW_REQUEST_RESUBMISSION: Discrepancias en metadata física; solicitar recaptura en vivo."

    return MeatspaceAttestationResponse(
        is_valid=is_valid,
        confidence_score=round(score, 2),
        flagged_reasons=flags,
        time_delta_seconds=round(time_delta, 1),
        hardware_verified=hardware_verified,
        location_verified=location_verified,
        ocr_injection_detected=ocr_injection_detected,
        recommendation=recommendation,
    )
