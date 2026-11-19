import fcntl
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class CaMeLEntry(BaseModel):
    """Entrada individual inmutable en el registro causal Multi-CaMeL (Why-Trail)."""

    model_config = ConfigDict(extra="forbid")

    sequence_index: int = Field(..., ge=0)
    timestamp: datetime
    previous_block_hash: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    event_type: str = Field(..., min_length=3, max_length=64)
    payload_hash: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    block_hash: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    actor_agent_id: str
    metadata: dict = Field(default_factory=dict)


class MultiCaMeLLedger:
    """
    Protocolo Multi-CaMeL (Causal Memory Log).
    Cadena inmutable de bloques criptográficos en disco para trazabilidad forense
    y prevención de manipulación de memoria histórica o contaminación causal.
    """

    GENESIS_HASH: ClassVar[str] = "0" * 64

    def __init__(self, ledger_file: Path | None = None):
        self.ledger_file = ledger_file
        self.chain: list[CaMeLEntry] = []
        if self.ledger_file and self.ledger_file.exists():
            self._load_from_disk()

    def _compute_block_hash(
        self,
        seq: int,
        ts: datetime,
        prev_hash: str,
        event_type: str,
        payload_hash: str,
        actor: str,
    ) -> str:
        data = f"{seq}:{ts.isoformat()}:{prev_hash}:{event_type}:{payload_hash}:{actor}".encode()
        return hashlib.sha256(data).hexdigest()

    def record_event(
        self,
        event_type: str,
        payload_data: dict,
        actor_agent_id: str,
        metadata: dict | None = None,
    ) -> CaMeLEntry:
        """Registra un evento encadenado criptográficamente con el bloque anterior (atómico con bloqueo fcntl)."""
        now = datetime.now(UTC)
        payload_bytes = json.dumps(payload_data, sort_keys=True).encode()
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()

        if self.ledger_file:
            with open(self.ledger_file, "a+", encoding="utf-8") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    f.seek(0)
                    chain_entries: list[CaMeLEntry] = []
                    for line in f:
                        line_str = line.strip()
                        if line_str:
                            chain_entries.append(CaMeLEntry.model_validate_json(line_str))

                    seq = len(chain_entries)
                    prev_hash = chain_entries[-1].block_hash if chain_entries else self.GENESIS_HASH
                    block_hash = self._compute_block_hash(
                        seq, now, prev_hash, event_type, payload_hash, actor_agent_id
                    )

                    entry = CaMeLEntry(
                        sequence_index=seq,
                        timestamp=now,
                        previous_block_hash=prev_hash,
                        event_type=event_type,
                        payload_hash=payload_hash,
                        block_hash=block_hash,
                        actor_agent_id=actor_agent_id,
                        metadata=metadata or {},
                    )
                    f.write(entry.model_dump_json() + "\n")
                    f.flush()
                    chain_entries.append(entry)
                    self.chain = chain_entries
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
            return entry

        # Fallback en memoria
        seq = len(self.chain)
        prev_hash = self.chain[-1].block_hash if self.chain else self.GENESIS_HASH
        block_hash = self._compute_block_hash(
            seq, now, prev_hash, event_type, payload_hash, actor_agent_id
        )
        entry = CaMeLEntry(
            sequence_index=seq,
            timestamp=now,
            previous_block_hash=prev_hash,
            event_type=event_type,
            payload_hash=payload_hash,
            block_hash=block_hash,
            actor_agent_id=actor_agent_id,
            metadata=metadata or {},
        )
        self.chain.append(entry)
        return entry

    def verify_chain_integrity(self, reload_from_disk: bool = False) -> tuple[bool, str | None]:
        """Audita matemáticamente toda la cadena para detectar manipulaciones o saltos temporales."""
        if reload_from_disk and self.ledger_file and self.ledger_file.exists():
            self._load_from_disk()

        for i, block in enumerate(self.chain):
            expected_prev = self.chain[i - 1].block_hash if i > 0 else self.GENESIS_HASH
            if block.previous_block_hash != expected_prev:
                return (
                    False,
                    f"Ruptura de cadena en bloque {i}: previous_hash '{block.previous_block_hash}' != '{expected_prev}'",
                )

            recalculated = self._compute_block_hash(
                block.sequence_index,
                block.timestamp,
                block.previous_block_hash,
                block.event_type,
                block.payload_hash,
                block.actor_agent_id,
            )
            if block.block_hash != recalculated:
                return (
                    False,
                    f"Firma corrupta en bloque {i}: hash '{block.block_hash}' != recalculado '{recalculated}'",
                )

        return True, None

    def get_audit_trail_for_actor(
        self, actor_agent_id: str, reload_from_disk: bool = True
    ) -> list[CaMeLEntry]:
        """Filtra la cadena de auditoría para un agente específico."""
        if reload_from_disk and self.ledger_file and self.ledger_file.exists():
            self._load_from_disk()
        return [entry for entry in self.chain if entry.actor_agent_id == actor_agent_id]

    def _append_to_disk(self, entry: CaMeLEntry):
        if not self.ledger_file:
            return
        with open(self.ledger_file, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(entry.model_dump_json() + "\n")
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _load_from_disk(self):
        if not self.ledger_file or not self.ledger_file.exists():
            return
        loaded: list[CaMeLEntry] = []
        with open(self.ledger_file, "r", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        loaded.append(CaMeLEntry.model_validate_json(line_str))
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        self.chain = loaded

    @classmethod
    def repair_chain_file(cls, ledger_file: Path) -> int:
        """
        Repara deterministamente una cadena histórica desincronizada por colisiones de concurrencia.
        Re-secuencia los bloques preservando timestamps, tipos de evento, payloads y actores.
        """
        if not ledger_file.exists():
            return 0

        raw_entries: list[dict] = []
        with open(ledger_file, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    raw_entries.append(json.loads(line_str))

        repaired_entries: list[CaMeLEntry] = []
        prev_hash = cls.GENESIS_HASH

        for seq, raw in enumerate(raw_entries):
            ts = datetime.fromisoformat(raw["timestamp"])
            event_type = raw["event_type"]
            payload_hash = raw["payload_hash"]
            actor = raw["actor_agent_id"]
            metadata = raw.get("metadata", {})

            data = f"{seq}:{ts.isoformat()}:{prev_hash}:{event_type}:{payload_hash}:{actor}".encode()
            block_hash = hashlib.sha256(data).hexdigest()

            entry = CaMeLEntry(
                sequence_index=seq,
                timestamp=ts,
                previous_block_hash=prev_hash,
                event_type=event_type,
                payload_hash=payload_hash,
                block_hash=block_hash,
                actor_agent_id=actor,
                metadata=metadata,
            )
            repaired_entries.append(entry)
            prev_hash = block_hash

        # Backup de seguridad y sobreescritura atómica
        backup_file = ledger_file.with_suffix(".jsonl.bak")
        ledger_file.replace(backup_file)

        with open(ledger_file, "w", encoding="utf-8") as f:
            for entry in repaired_entries:
                f.write(entry.model_dump_json() + "\n")

        return len(repaired_entries)
