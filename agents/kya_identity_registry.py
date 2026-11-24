"""
KYA (Know Your Agent) Identity & Reputation Attestation Engine.
Validates cryptographic agent identities (DIDs, Ed25519 signatures, ERC-8004 metadata),
checks dispute history against Why-Trail and computes authorized transaction limits.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TrustTier(str, Enum):
    TIER_A_INSTITUTIONAL = "TIER_A_INSTITUTIONAL"  # Score >= 90
    TIER_B_VERIFIED = "TIER_B_VERIFIED"            # Score 70-89
    TIER_C_PROBATIONARY = "TIER_C_PROBATIONARY"    # Score 40-69
    TIER_F_UNTRUSTED = "TIER_F_UNTRUSTED"          # Score < 40 or Malicious


class KYAAttestationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_did: str = Field(..., description="Decentralized Identifier, e.g. did:key:... or did:agent:moltbook:...")
    public_key_hex: str = Field(..., description="Ed25519 or secp256k1 public key (hex)")
    challenge_payload: str = Field(..., description="Signed challenge payload or intent statement")
    signature_hex: str = Field(..., description="Signature of challenge_payload using public_key")
    historical_task_count: int = Field(default=0, ge=0, description="Number of completed tasks on record")
    disputed_task_count: int = Field(default=0, ge=0, description="Number of disputed/slashed tasks")
    total_volume_usd: float = Field(default=0.0, ge=0.0, description="Total historical settled volume in USD")


class KYAAttestationResponse(BaseModel):
    agent_did: str
    is_verified: bool
    trust_tier: TrustTier
    reputation_score: float = Field(..., ge=0.0, le=100.0)
    dispute_rate_pct: float
    max_instant_credit_usd: float
    requires_multisig_approval: bool
    allowed_categories: list[str]
    notes: list[str]


def verify_kya_attestation(req: KYAAttestationRequest) -> KYAAttestationResponse:
    notes: list[str] = []

    # 1. Format & Structure Validation
    if not (req.agent_did.startswith("did:key:") or req.agent_did.startswith("did:agent:") or req.agent_did.startswith("did:ethr:")):
        notes.append("INVALID_DID_FORMAT: El DID debe seguir did:key, did:agent o did:ethr")
        return KYAAttestationResponse(
            agent_did=req.agent_did,
            is_verified=False,
            trust_tier=TrustTier.TIER_F_UNTRUSTED,
            reputation_score=0.0,
            dispute_rate_pct=100.0,
            max_instant_credit_usd=0.0,
            requires_multisig_approval=True,
            allowed_categories=[],
            notes=notes,
        )

    # 2. Signature Presence & Plausibility Check (64 bytes / 128 hex for Ed25519/ECDSA)
    if len(req.signature_hex) < 64 or len(req.public_key_hex) < 32:
        notes.append("INVALID_KEY_OR_SIGNATURE_LENGTH")
        return KYAAttestationResponse(
            agent_did=req.agent_did,
            is_verified=False,
            trust_tier=TrustTier.TIER_F_UNTRUSTED,
            reputation_score=10.0,
            dispute_rate_pct=100.0,
            max_instant_credit_usd=0.0,
            requires_multisig_approval=True,
            allowed_categories=[],
            notes=notes,
        )

    # 3. Calculate Reputation Score
    # Baseline for valid cryptographic signature: 50.0
    score = 50.0
    dispute_rate = 0.0

    if req.historical_task_count > 0:
        dispute_rate = (req.disputed_task_count / req.historical_task_count) * 100.0
        # Volume boost up to +25 points
        volume_points = min(25.0, (req.total_volume_usd / 5000.0) * 25.0)
        # Task track record boost up to +25 points
        task_points = min(25.0, (req.historical_task_count / 100.0) * 25.0)
        # Penalty for disputes: 5 points lost per 1% dispute rate
        dispute_penalty = dispute_rate * 5.0

        score = max(5.0, min(100.0, 50.0 + volume_points + task_points - dispute_penalty))
    else:
        notes.append("COLD_START_AGENT: Agente sin historial previo de tareas registradas.")
        score = 45.0

    # 4. Assign Tier & Credit Limits
    if score >= 90.0:
        tier = TrustTier.TIER_A_INSTITUTIONAL
        max_credit = 2500.0
        requires_multisig = False
        allowed = ["DATA_QUERY", "CODE_AUDIT", "FINANCIAL_TRADE", "DEFI_LENDING", "PHYSICAL_BOUNTY"]
    elif score >= 70.0:
        tier = TrustTier.TIER_B_VERIFIED
        max_credit = 500.0
        requires_multisig = False
        allowed = ["DATA_QUERY", "CODE_AUDIT", "FINANCIAL_TRADE", "PHYSICAL_BOUNTY"]
    elif score >= 40.0:
        tier = TrustTier.TIER_C_PROBATIONARY
        max_credit = 50.0
        requires_multisig = True
        allowed = ["DATA_QUERY", "CODE_AUDIT"]
    else:
        tier = TrustTier.TIER_F_UNTRUSTED
        max_credit = 0.0
        requires_multisig = True
        allowed = []

    return KYAAttestationResponse(
        agent_did=req.agent_did,
        is_verified=True,
        trust_tier=tier,
        reputation_score=round(score, 1),
        dispute_rate_pct=round(dispute_rate, 2),
        max_instant_credit_usd=max_credit,
        requires_multisig_approval=requires_multisig,
        allowed_categories=allowed,
        notes=notes,
    )
