import os

from api_gateway import app
from fastapi.testclient import TestClient
from l402_gateway import L402Gateway


def test_l402_gateway_nwc_initialization():
    nwc_uri = os.getenv("A2A_NWC_URI")
    gateway = L402Gateway(nwc_uri=nwc_uri)
    info = gateway.get_wallet_info()

    if nwc_uri:
        assert info["connected"] is True
        assert info["backend"] == "alby_hub_nwc"
        assert info["network"] == "mainnet"
        assert "balance_sats" in info
        assert "supported_methods" in info
    else:
        assert info["connected"] is False
        assert info["backend"] == "synthetic_vault"


def test_l402_gateway_lookup_invoice():
    gateway = L402Gateway()
    challenge, _ = gateway.create_challenge(
        service="nwc_test_service",
        amount_sats=100,
        client_id="test_agent_nwc",
    )

    # Buscar en el vault sintético
    res = gateway.lookup_invoice(payment_hash=challenge.payment_hash)
    assert res["found"] is True
    assert res["payment_hash"] == challenge.payment_hash
    assert res["settled"] is False

    # Buscar factura inexistente
    res_unknown = gateway.lookup_invoice(payment_hash="deadbeef" * 8)
    assert res_unknown["found"] is False


def test_api_gateway_l402_endpoints():
    client = TestClient(app)

    # 1. Endpoint /api/v1/l402/wallet
    res_wallet = client.get("/api/v1/l402/wallet")
    assert res_wallet.status_code == 200
    wallet_data = res_wallet.json()
    assert "connected" in wallet_data
    assert "backend" in wallet_data

    # 2. Endpoint /api/v1/l402/lookup
    res_lookup = client.get("/api/v1/l402/lookup", params={"payment_hash": "deadbeef" * 8})
    assert res_lookup.status_code == 200
    lookup_data = res_lookup.json()
    assert lookup_data["found"] is False
