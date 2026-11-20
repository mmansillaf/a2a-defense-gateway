import time

import pytest
from credit_redemption_pool import CreditRedemptionPool
from l402_gateway import L402Gateway
from sandbox_compute_service import SandboxComputeService, SandboxExecutionRequest


def test_l402_challenge_generation_and_valid_authorization():
    gateway = L402Gateway()
    challenge, preimage = gateway.create_challenge(
        service="epistemic_audit",
        amount_sats=500,
        client_id="agent_client_01",
        ttl_seconds=300,
    )

    assert challenge.status_code == 402
    assert challenge.amount_sats == 500
    assert "L402 macaroon=" in challenge.www_authenticate_header

    # 1. Verificación exitosa con preimagen correcta
    valid_auth = f"L402 {challenge.macaroon_b64}:{preimage.hex()}"
    res = gateway.verify_authorization(valid_auth)
    assert res.is_valid is True
    assert res.service == "epistemic_audit"
    assert res.amount_sats == 500
    assert res.client_id == "agent_client_01"

    # 2. Verificación fallida con preimagen incorrecta
    fake_preimage = b"\x00" * 32
    invalid_auth = f"L402 {challenge.macaroon_b64}:{fake_preimage.hex()}"
    res_fake = gateway.verify_authorization(invalid_auth)
    assert res_fake.is_valid is False
    assert "Preimagen incorrecta" in res_fake.error_message

    # 3. Verificación cruzada entre dos workers distintos (multi-proceso)
    worker_two_gateway = L402Gateway()
    res_cross_worker = worker_two_gateway.verify_authorization(valid_auth)
    assert res_cross_worker.is_valid is True
    assert res_cross_worker.service == "epistemic_audit"


def test_l402_macaroon_expiration_and_tampering():
    gateway = L402Gateway()
    # TTL de 1 segundo
    challenge, preimage = gateway.create_challenge(
        service="rapid_compute",
        amount_sats=100,
        client_id="agent_client_02",
        ttl_seconds=1,
    )

    time.sleep(1.2)
    auth = f"L402 {challenge.macaroon_b64}:{preimage.hex()}"
    res = gateway.verify_authorization(auth)
    assert res.is_valid is False
    assert "expirado" in res.error_message

    # Intento de falsificación de firma
    tampered_auth = f"L402 {challenge.macaroon_b64[:-4]}aaaa:{preimage.hex()}"
    res_tampered = gateway.verify_authorization(tampered_auth)
    assert res_tampered.is_valid is False


def test_credit_redemption_pool_lifecycle():
    pool = CreditRedemptionPool(exchange_rate_sats_per_credit=25, liquidity_reserve_sats=100_000)

    # 1. Obtener cotización
    quote = pool.get_quote(credits=20)
    assert quote.credits == 20
    assert quote.gross_sats == 500
    assert quote.net_sats < 500  # Menos comisión

    # 2. Ejecutar liquidación
    dest_bolt11 = "lnbc500u1p1234567890abcdef..."
    receipt = pool.execute_redemption(
        agent_id="agent_vendor_42",
        credits=20,
        destination_bolt11=dest_bolt11,
        quote_id=quote.quote_id,
    )
    assert receipt.status == "SETTLED"
    assert receipt.credits_redeemed == 20
    assert receipt.net_sats_transferred == quote.net_sats
    assert pool.reserve_sats == 100_000 - quote.net_sats

    # 3. Intentar reutilizar cotización liquidada
    with pytest.raises(ValueError, match="no encontrada"):
        pool.execute_redemption(
            agent_id="agent_vendor_42",
            credits=20,
            destination_bolt11=dest_bolt11,
            quote_id=quote.quote_id,
        )


def test_sandbox_compute_limits():
    sandbox = SandboxComputeService()

    # 1. Ejecución limpia y determinista
    code_ok = "print('COMPUTE_DONE: 42')"
    req_ok = SandboxExecutionRequest(code=code_ok, timeout_seconds=2, max_memory_mb=64)
    res_ok = sandbox.run_isolated(req_ok)
    assert res_ok.status == "SUCCESS"
    assert "COMPUTE_DONE: 42" in res_ok.stdout
    assert res_ok.exit_code == 0

    # 2. Timeout forzado (bucle infinito de CPU)
    code_timeout = "import time\nwhile True:\n    pass\n"
    req_timeout = SandboxExecutionRequest(code=code_timeout, timeout_seconds=1, max_memory_mb=64)
    res_timeout = sandbox.run_isolated(req_timeout)
    assert res_timeout.status == "TIMEOUT"


def test_sandbox_pep578_blocks_network_and_subprocesses():
    sandbox = SandboxComputeService()

    # 1. Intento de apertura de socket de red (SSRF / exfiltración)
    code_socket = "import socket\ns = socket.socket()\ns.connect(('127.0.0.1', 80))\n"
    req_socket = SandboxExecutionRequest(code=code_socket, timeout_seconds=2, max_memory_mb=64)
    res_socket = sandbox.run_isolated(req_socket)
    assert res_socket.status == "ERROR"
    assert "PermissionError" in res_socket.stderr or "[SECURITY_VIOLATION]" in res_socket.stderr

    # 2. Intento de ejecución de subproceso / comando de sistema
    code_subproc = "import subprocess\nsubprocess.run(['ls', '-la'])\n"
    req_subproc = SandboxExecutionRequest(code=code_subproc, timeout_seconds=2, max_memory_mb=64)
    res_subproc = sandbox.run_isolated(req_subproc)
    assert res_subproc.status == "ERROR"
    assert "PermissionError" in res_subproc.stderr or "[SECURITY_VIOLATION]" in res_subproc.stderr
