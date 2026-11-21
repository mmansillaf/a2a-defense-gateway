import asyncio
import base64
import concurrent.futures
import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger("a2a.l402")

try:
    from nostr_sdk import (
        LookupInvoiceRequest,
        MakeInvoiceRequest,
        NostrWalletConnect,
        NostrWalletConnectUri,
    )
    NOSTR_SDK_AVAILABLE = True
except ImportError:
    NOSTR_SDK_AVAILABLE = False


def _run_async(coro):
    """Ejecuta una corrutina de forma segura incluso dentro de un bucle de eventos existente."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=15)
    else:
        return asyncio.run(coro)


class L402Challenge(BaseModel):
    """Estructura de respuesta HTTP 402 Payment Required."""
    model_config = ConfigDict(extra="forbid")

    status_code: int = 402
    macaroon_b64: str
    payment_hash: str
    invoice_bolt11: str
    amount_sats: int
    www_authenticate_header: str


class L402VerificationResult(BaseModel):
    """Resultado de verificación del token L402 presentado en la cabecera Authorization."""
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    service: str | None = None
    amount_sats: int = 0
    client_id: str | None = None
    error_message: str | None = None


class L402Gateway:
    """
    Pasarela de pagos L402 (Lightning Service Authentication Tokens).
    Emite desafíos HTTP 402 y valida credenciales Macaroon + Preimagen de Lightning Network.
    """

    def __init__(
        self,
        gateway_secret_key: str | None = None,
        nwc_uri: str | None = None,
    ):
        self.secret_key = (
            gateway_secret_key
            or os.getenv("A2A_L402_SECRET_KEY")
            or "a2a_l402_hmac_master_secret_key_2026_production"
        )
        self.nwc_uri = nwc_uri or os.getenv("A2A_NWC_URI")
        self._nwc_client: NostrWalletConnect | None = None
        self.invoice_vault: dict[str, bytes] = {}

        if self.nwc_uri and NOSTR_SDK_AVAILABLE:
            try:
                uri = NostrWalletConnectUri.parse(self.nwc_uri)
                self._nwc_client = NostrWalletConnect(uri)
                logger.info("NWC backend initialized successfully.")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Error parsing NWC URI: {exc}")

    def create_challenge(
        self,
        service: str,
        amount_sats: int,
        client_id: str,
        ttl_seconds: int = 1800,
    ) -> tuple[L402Challenge, bytes]:
        """
        Genera un desafío HTTP 402 con Macaroon firmado y factura Lightning (Alby Hub o sintética).
        Retorna el desafío y la preimagen (si fue generada sintéticamente).
        """
        real_invoice: str | None = None
        real_payment_hash: str | None = None
        preimage = b""

        # Intentar generar factura real vía NWC (Alby Hub)
        if self._nwc_client:
            try:
                req = MakeInvoiceRequest(
                    amount=amount_sats * 1000,
                    description=f"A2A {service} for {client_id}",
                    description_hash=None,
                    expiry=ttl_seconds,
                )
                res = _run_async(self._nwc_client.make_invoice(req))
                real_invoice = res.invoice
                real_payment_hash = res.payment_hash
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"NWC invoice generation fallback: {exc}")

        if real_invoice and real_payment_hash:
            payment_hash = real_payment_hash
            invoice_bolt11 = real_invoice
        else:
            preimage = secrets.token_bytes(32)
            payment_hash = hashlib.sha256(preimage).hexdigest()
            self.invoice_vault[payment_hash] = preimage
            invoice_bolt11 = f"lnbc{amount_sats}u1p{payment_hash[:20]}..."

        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

        # 2. Construir caveats del Macaroon
        caveats = {
            "payment_hash": payment_hash,
            "service": service,
            "client_id": client_id,
            "amount_sats": amount_sats,
            "expires_at": expires_at.isoformat(),
        }
        caveats_raw = json.dumps(caveats, sort_keys=True)

        # 3. Firmar Macaroon con clave maestra de la pasarela
        signature = hmac.new(self.secret_key.encode(), caveats_raw.encode(), hashlib.sha256).hexdigest()
        macaroon_data = {"caveats": caveats, "sig": signature}
        macaroon_b64 = base64.b64encode(json.dumps(macaroon_data).encode()).decode()

        auth_header = f'L402 macaroon="{macaroon_b64}", invoice="{invoice_bolt11}"'

        challenge = L402Challenge(
            status_code=402,
            macaroon_b64=macaroon_b64,
            payment_hash=payment_hash,
            invoice_bolt11=invoice_bolt11,
            amount_sats=amount_sats,
            www_authenticate_header=auth_header,
        )

        return challenge, preimage

    def verify_authorization(self, auth_header: str) -> L402VerificationResult:
        """
        Valida la cabecera 'Authorization: L402 <macaroon_b64>:<preimage_hex>'.
        Verifica matemáticamente: SHA-256(preimage) == payment_hash y firma HMAC del Macaroon.
        """
        if not auth_header or not auth_header.startswith("L402 "):
            return L402VerificationResult(
                is_valid=False, error_message="Formato de cabecera inválido. Debe ser 'L402 <macaroon>:<preimage>'."
            )

        token_str = auth_header[5:].strip()
        parts = token_str.split(":")
        if len(parts) != 2:
            return L402VerificationResult(
                is_valid=False, error_message="Credencial L402 malformada. Falta separador ':' entre macaroon y preimage."
            )

        macaroon_b64, preimage_hex = parts[0], parts[1]

        # 1. Decodificar Macaroon
        try:
            macaroon_json = base64.b64decode(macaroon_b64.encode()).decode()
            macaroon_data = json.loads(macaroon_json)
            caveats = macaroon_data["caveats"]
            signature = macaroon_data["sig"]
        except (json.JSONDecodeError, ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
            return L402VerificationResult(is_valid=False, error_message=f"Macaroon corrupto o no decodificable: {exc}")

        # 2. Validar firma criptográfica del Macaroon
        expected_sig = hmac.new(
            self.secret_key.encode(),
            json.dumps(caveats, sort_keys=True).encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return L402VerificationResult(is_valid=False, error_message="Firma de Macaroon inválida (forjada).")

        # 3. Comprobar expiración temporal
        expires_at = datetime.fromisoformat(caveats["expires_at"])
        if datetime.now(UTC) > expires_at:
            return L402VerificationResult(is_valid=False, error_message="Macaroon L402 expirado.")

        # 4. Validar prueba de pago (Preimage SHA-256)
        try:
            preimage_bytes = bytes.fromhex(preimage_hex)
        except ValueError:
            return L402VerificationResult(is_valid=False, error_message="Preimagen no es un valor hexadecimal válido.")

        computed_hash = hashlib.sha256(preimage_bytes).hexdigest()
        if not hmac.compare_digest(computed_hash, caveats["payment_hash"]):
            return L402VerificationResult(
                is_valid=False,
                error_message=f"Preimagen incorrecta. Hash {computed_hash} no coincide con {caveats['payment_hash']}.",
            )

        return L402VerificationResult(
            is_valid=True,
            service=caveats["service"],
            amount_sats=caveats["amount_sats"],
            client_id=caveats["client_id"],
            error_message=None,
        )

    def get_wallet_info(self) -> dict:
        """Consulta el estado, capacidad y balance del nodo Lightning vía Alby Hub NWC."""
        if not self._nwc_client:
            return {
                "connected": False,
                "backend": "synthetic_vault",
                "reason": "NWC no configurado o nostr_sdk no disponible." if not NOSTR_SDK_AVAILABLE else "A2A_NWC_URI no provisto.",
            }

        try:
            async def _query():
                info_res = await self._nwc_client.get_info()
                balance_res = await self._nwc_client.get_balance()
                return info_res, balance_res

            info, balance = _run_async(_query())
            methods_list = [str(m) for m in info.methods] if getattr(info, "methods", None) else []
            return {
                "connected": True,
                "backend": "alby_hub_nwc",
                "alias": getattr(info, "alias", "Alby Hub"),
                "pubkey": getattr(info, "pubkey", None),
                "network": getattr(info, "network", "mainnet"),
                "block_height": getattr(info, "block_height", None),
                "balance_msats": getattr(balance, "balance", 0),
                "balance_sats": getattr(balance, "balance", 0) // 1000,
                "supported_methods": methods_list,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Error querying NWC wallet info: {exc}")
            return {
                "connected": False,
                "backend": "alby_hub_nwc",
                "error": str(exc),
            }

    def lookup_invoice(
        self,
        payment_hash: str | None = None,
        invoice_bolt11: str | None = None,
    ) -> dict:
        """Verifica el estado de liquidación de una factura Lightning vía Alby Hub NWC."""
        if not payment_hash and not invoice_bolt11:
            return {"error": "Debe proveer payment_hash o invoice_bolt11"}

        if self._nwc_client:
            try:
                req = LookupInvoiceRequest(payment_hash=payment_hash, invoice=invoice_bolt11)
                res = _run_async(self._nwc_client.lookup_invoice(req))
                state_str = str(res.state).split(".")[-1] if res.state is not None else "NONE"
                return {
                    "found": True,
                    "backend": "alby_hub_nwc",
                    "state": state_str,
                    "settled": state_str == "SETTLED",
                    "payment_hash": res.payment_hash,
                    "preimage": res.preimage,
                    "amount_msats": res.amount,
                    "fees_paid_msats": res.fees_paid,
                }
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Error looking up invoice via NWC: {exc}")

        # Fallback al vault sintético
        if payment_hash and payment_hash in self.invoice_vault:
            return {
                "found": True,
                "backend": "synthetic_vault",
                "state": "SIMULATED_ACTIVE",
                "settled": False,
                "payment_hash": payment_hash,
                "has_vault_preimage": True,
            }

        return {
            "found": False,
            "backend": "synthetic_vault",
            "state": "UNKNOWN",
            "settled": False,
            "payment_hash": payment_hash,
        }

