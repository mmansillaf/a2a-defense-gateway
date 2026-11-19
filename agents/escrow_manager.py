from datetime import UTC, datetime
from typing import Literal

from crypto_audit_log import MultiCaMeLLedger
from pydantic import BaseModel, ConfigDict, Field


class EscrowContract(BaseModel):
    """Contrato de depósito en garantía colateralizado compatible con ERC-8183."""
    model_config = ConfigDict(extra="forbid")

    contract_id: str = Field(..., pattern=r"^ESC-[0-9a-f]{12}$")
    client_agent_id: str
    provider_agent_id: str
    evaluator_agent_id: str | None = None  # Abstracción de evaluador ERC-8183 (Oráculo o ZK Verifier)
    service_fee_credits: int = Field(..., ge=1)
    provider_stake_credits: int = Field(..., ge=0)
    total_locked_credits: int = Field(..., ge=1)
    status: Literal["LOCKED", "SUBMITTED", "COMPLETED", "DISPUTED", "SLASHED", "REFUNDED"]
    created_at: datetime
    fulfillment_hash: str | None = None
    dispute_reason: str | None = None


class EscrowManager:
    """
    Administrador de contratos de custodia (Escrow) y colateralización.
    Garantiza la preservación de fondos y ejecuta penalizaciones (Slashing)
    cuando un oráculo o proveedor de servicios emite una atestación corrupta.
    """

    def __init__(self, ledger: MultiCaMeLLedger | None = None):
        self.ledger = ledger or MultiCaMeLLedger()
        self.contracts: dict[str, EscrowContract] = {}
        self.vault_total_locked: int = 0

    def create_contract(
        self,
        client_id: str,
        provider_id: str,
        service_fee: int,
        provider_stake: int,
        evaluator_id: str | None = None,
    ) -> EscrowContract:
        """Crea un contrato bloqueando la tarifa del cliente y el colateral del proveedor (compatible ERC-8183)."""
        import secrets

        contract_id = f"ESC-{secrets.token_hex(6)}"
        total_locked = service_fee + provider_stake

        contract = EscrowContract(
            contract_id=contract_id,
            client_agent_id=client_id,
            provider_agent_id=provider_id,
            evaluator_agent_id=evaluator_id,
            service_fee_credits=service_fee,
            provider_stake_credits=provider_stake,
            total_locked_credits=total_locked,
            status="LOCKED",
            created_at=datetime.now(UTC),
        )

        self.contracts[contract_id] = contract
        self.vault_total_locked += total_locked

        self.ledger.record_event(
            event_type="ESCROW_LOCKED",
            payload_data={
                "contract_id": contract_id,
                "client": client_id,
                "provider": provider_id,
                "locked": total_locked,
            },
            actor_agent_id="escrow_manager",
        )

        return contract

    def submit_work(self, contract_id: str, fulfillment_hash: str) -> EscrowContract:
        """Transición ERC-8183: el proveedor entrega la prueba verificable de su trabajo."""
        contract = self.contracts.get(contract_id)
        if not contract or contract.status != "LOCKED":
            raise ValueError(f"Contrato {contract_id} no está en estado LOCKED para envío de pruebas.")

        contract.status = "SUBMITTED"
        contract.fulfillment_hash = fulfillment_hash

        self.ledger.record_event(
            event_type="ESCROW_SUBMITTED",
            payload_data={"contract_id": contract_id, "fulfillment_hash": fulfillment_hash},
            actor_agent_id=contract.provider_agent_id,
        )
        return contract

    def release_funds(self, contract_id: str, fulfillment_hash: str) -> EscrowContract:
        """Libera los fondos al proveedor tras evaluación exitosa (ERC-8183 Settled)."""
        contract = self.contracts.get(contract_id)
        if not contract or contract.status not in ("LOCKED", "SUBMITTED", "DISPUTED"):
            raise ValueError(f"Contrato {contract_id} no está en estado liberable (estado: {contract.status if contract else 'None'}).")

        contract.status = "COMPLETED"
        contract.fulfillment_hash = fulfillment_hash
        self.vault_total_locked -= contract.total_locked_credits

        self.ledger.record_event(
            event_type="ESCROW_RELEASED",
            payload_data={
                "contract_id": contract_id,
                "provider_payout": contract.total_locked_credits,
                "fulfillment_hash": fulfillment_hash,
            },
            actor_agent_id="escrow_manager",
        )

        return contract

    def dispute_contract(self, contract_id: str, reason: str) -> EscrowContract:
        """Abre una disputa formal congelando los fondos hasta el veredicto del Tribunal o Evaluador."""
        contract = self.contracts.get(contract_id)
        if not contract or contract.status not in ("LOCKED", "SUBMITTED"):
            raise ValueError(f"Contrato {contract_id} no está en estado disputable.")

        contract.status = "DISPUTED"
        contract.dispute_reason = reason

        self.ledger.record_event(
            event_type="ESCROW_DISPUTED",
            payload_data={"contract_id": contract_id, "reason": reason},
            actor_agent_id=contract.client_agent_id,
        )

        return contract

    def execute_slashing(self, contract_id: str, slash_reason: str) -> tuple[EscrowContract, dict]:
        """
        Ejecuta el castigo financiero por falsedad comprobada (ERC-8183 Slashed):
        1. El colateral del proveedor se confisca como indemnización al cliente.
        2. La tarifa del servicio se reintegra al cliente al 100%.
        """
        contract = self.contracts.get(contract_id)
        if not contract or contract.status not in ("LOCKED", "SUBMITTED", "DISPUTED"):
            raise ValueError(f"Contrato {contract_id} no está en estado elegible para slashing.")

        contract.status = "SLASHED"
        contract.dispute_reason = slash_reason
        self.vault_total_locked -= contract.total_locked_credits

        # Indemnización total entregada al cliente
        client_refund_and_damages = contract.service_fee_credits + contract.provider_stake_credits

        settlement = {
            "client_payout": client_refund_and_damages,
            "provider_slashed_stake": contract.provider_stake_credits,
            "provider_payout": 0,
        }

        self.ledger.record_event(
            event_type="ESCROW_SLASHED",
            payload_data={
                "contract_id": contract_id,
                "slashed_stake": contract.provider_stake_credits,
                "client_damages": client_refund_and_damages,
                "reason": slash_reason,
            },
            actor_agent_id="escrow_manager",
        )

        return contract, settlement

    def _get_active_contract(self, contract_id: str) -> EscrowContract:
        contract = self.contracts.get(contract_id)
        if not contract:
            raise KeyError(f"Contrato {contract_id} no existe.")
        if contract.status != "LOCKED":
            raise ValueError(f"Contrato {contract_id} en estado '{contract.status}', no modificable.")
        return contract
