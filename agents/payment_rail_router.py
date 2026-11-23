"""
Universal Dual-Rail Micropayment Router: x402 <-> L402 Gateway.
Translates payment challenges and settlements between HTTP 402 (Base USDC / Solana)
and L402 (Lightning Network Sats) with dynamic exchange rates and routing fees.
"""

from decimal import Decimal
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class PaymentRail(str, Enum):
    X402_BASE_USDC = "x402_base_usdc"
    X402_SOLANA_USDC = "x402_solana_usdc"
    L402_LIGHTNING_SATS = "l402_lightning_sats"


class RailTranslationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_rail: PaymentRail
    target_rail: PaymentRail
    amount: Decimal = Field(..., gt=0, description="Amount in source rail unit (USD for x402, Sats for L402)")
    service_endpoint_url: str = Field(..., description="Target service URL requiring payment")
    payer_address_or_pubkey: str = Field(..., description="Payer wallet address or Lightning node pubkey")


class RailTranslationResponse(BaseModel):
    success: bool
    source_rail: PaymentRail
    target_rail: PaymentRail
    source_amount: str
    target_amount: str
    target_unit: str
    exchange_rate_usd_per_btc: str
    routing_fee_usd: str
    challenge_header_name: str
    challenge_header_value: str
    estimated_settlement_ms: int


# Reference rate: 1 BTC = 96,000 USD -> 1 sat = $0.00096 USD -> 1 USD ≈ 1,041.67 sats
BTC_USD_RATE = Decimal("96000.00")
SATS_PER_BTC = Decimal("100000000")
SATS_PER_USD = SATS_PER_BTC / BTC_USD_RATE  # ≈ 1041.66666667


def translate_x402_to_l402_settlement(req: RailTranslationRequest) -> RailTranslationResponse:
    # 0.25% routing fee (min $0.001)
    if req.source_rail in {PaymentRail.X402_BASE_USDC, PaymentRail.X402_SOLANA_USDC}:
        usd_val = req.amount
        fee_usd = max(Decimal("0.001"), (usd_val * Decimal("0.0025"))).quantize(Decimal("0.00001"))
        net_usd = usd_val + fee_usd

        if req.target_rail == PaymentRail.L402_LIGHTNING_SATS:
            target_amount = (net_usd * SATS_PER_USD).quantize(Decimal("1"))
            target_unit = "satoshis"
            header_name = "Authorization"
            header_val = f"L402 invoice=lnbc{int(target_amount)}u1p...:macaroon=AgEEbW9sd..."
            settle_ms = 450
        else:
            target_amount = net_usd.quantize(Decimal("0.0001"))
            target_unit = "USDC"
            header_name = "X-Payment-Token"
            header_val = f"x402 {req.payer_address_or_pubkey}:{target_amount}:base"
            settle_ms = 1200
    else:  # Source is L402 (sats)
        sats_val = req.amount
        usd_equiv = (sats_val / SATS_PER_USD).quantize(Decimal("0.00001"))
        fee_usd = max(Decimal("0.001"), (usd_equiv * Decimal("0.0025"))).quantize(Decimal("0.00001"))
        total_usd = (usd_equiv + fee_usd).quantize(Decimal("0.0001"))

        target_amount = total_usd
        target_unit = "USDC"
        header_name = "X-Payment-Token"
        header_val = f"x402 {req.payer_address_or_pubkey}:{target_amount}:base"
        settle_ms = 950

    return RailTranslationResponse(
        success=True,
        source_rail=req.source_rail,
        target_rail=req.target_rail,
        source_amount=str(req.amount),
        target_amount=str(target_amount),
        target_unit=target_unit,
        exchange_rate_usd_per_btc=str(BTC_USD_RATE),
        routing_fee_usd=str(fee_usd),
        challenge_header_name=header_name,
        challenge_header_value=header_val,
        estimated_settlement_ms=settle_ms,
    )
