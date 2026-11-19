from typing import Literal

from crypto_audit_log import MultiCaMeLLedger
from escrow_manager import EscrowManager
from pydantic import BaseModel, ConfigDict


class CourtRuling(BaseModel):
    """Sentencia vinculante emitida por el Tribunal de Arbitraje Forense A2A."""
    model_config = ConfigDict(extra="forbid")

    dispute_id: str
    contract_id: str
    ruling: Literal["RELEASE_TO_PROVIDER", "SLASH_PROVIDER"]
    legal_rationale: str
    why_trail_verified: bool
    settlement_summary: dict


class A2ACourtArbitrator:
    """
    Tribunal de Arbitraje Forense y Juez Imparcial A2A.
    Resuelve disputas contractuales auditando la cadena de bloques Multi-CaMeL (Why-Trail).
    """

    def __init__(self, escrow_manager: EscrowManager, ledger: MultiCaMeLLedger):
        self.escrow = escrow_manager
        self.ledger = ledger

    def adjudicate_dispute(
        self,
        contract_id: str,
        claimed_evidence_hash: str | None = None,
    ) -> CourtRuling:
        """
        Audita el historial criptográfico y emite sentencia vinculante sobre el contrato en custodia.
        """
        import secrets

        dispute_id = f"DISP-{secrets.token_hex(6)}"

        # 1. Auditar matemáticamente la integridad de la cadena causal
        is_chain_intact, chain_err = self.ledger.verify_chain_integrity()
        if not is_chain_intact:
            # Si el historial está corrupto o manipulado, el tribunal sanciona al proveedor por defecto
            contract, settlement = self.escrow.execute_slashing(
                contract_id,
                slash_reason=f"Fallo forense crítico: Cadena de auditoría manipulada ({chain_err}).",
            )
            return CourtRuling(
                dispute_id=dispute_id,
                contract_id=contract_id,
                ruling="SLASH_PROVIDER",
                legal_rationale=f"Ruptura de la cadena Multi-CaMeL detectada: {chain_err}",
                why_trail_verified=False,
                settlement_summary=settlement,
            )

        # 2. Buscar si existe una atestación válida registrada en la cadena
        attestation_found = False
        for block in self.ledger.chain:
            if block.event_type in ("EPISTEMIC_ATTESTATION", "ESCROW_RELEASED") and (
                not claimed_evidence_hash or block.payload_hash == claimed_evidence_hash
            ):
                attestation_found = True
                break

        # 3. Emitir sentencia vinculante
        if attestation_found:
            # El proveedor cumplió con evidencia verificada -> Desestimar disputa y liberar fondos
            contract = self.escrow.release_funds(
                contract_id, fulfillment_hash=claimed_evidence_hash or "verified_by_why_trail"
            )
            return CourtRuling(
                dispute_id=dispute_id,
                contract_id=contract_id,
                ruling="RELEASE_TO_PROVIDER",
                legal_rationale="Evidencia factual y registro inmutable verificados en la cadena Multi-CaMeL.",
                why_trail_verified=True,
                settlement_summary={"provider_payout": contract.total_locked_credits, "client_payout": 0},
            )
        else:
            # Proveedor no pudo demostrar cumplimiento o atestación -> Slashing
            contract, settlement = self.escrow.execute_slashing(
                contract_id,
                slash_reason="Proveedor no registró atestación válida en el registro inmutable Why-Trail.",
            )
            return CourtRuling(
                dispute_id=dispute_id,
                contract_id=contract_id,
                ruling="SLASH_PROVIDER",
                legal_rationale="Ausencia de prueba criptográfica en el historial causal. Fondos reintegrados e indemnización cobrada.",
                why_trail_verified=True,
                settlement_summary=settlement,
            )
