"""
Script de actualización de plantillas HTML en api_gateway.py:
1. LANDING_HTML: actualiza tabla y encabezado a 56 herramientas de producción.
2. DASHBOARD_HTML: actualiza conteos residuales (45 -> 56) y añade templates en el playground.
"""

from pathlib import Path

GATEWAY_PATH = Path("/home/usuario/Descargas/pycode/SkillA2A_Moltbook/moltbook_defense_system/agents/api_gateway.py")
ROWS_PATH = Path("/home/usuario/Descargas/pycode/SkillA2A_Moltbook/moltbook_defense_system/landing_table_rows.html")

def main():
    with open(GATEWAY_PATH, "r", encoding="utf-8") as f:
        code = f.read()

    # 1. Update LANDING_HTML table
    old_table_header = "<h2>16 Production MCP Tools Available (Marcha Blanca Free Tier)</h2>"
    new_table_header = "<h2>56 Production MCP Tools Available (Marcha Blanca Free Tier)</h2>"

    with open(ROWS_PATH, "r", encoding="utf-8") as f:
        new_rows = f.read()

    old_tbody_start = "<tbody>"
    old_tbody_end = "</tbody>"

    table_idx = code.find(old_table_header)
    if table_idx != -1:
        tbody_start_idx = code.find(old_tbody_start, table_idx)
        tbody_end_idx = code.find(old_tbody_end, tbody_start_idx)
        if tbody_start_idx != -1 and tbody_end_idx != -1:
            code = (
                code[:table_idx]
                + new_table_header
                + code[table_idx + len(old_table_header):tbody_start_idx + len(old_tbody_start)]
                + "\n"
                + new_rows
                + "\n        "
                + code[tbody_end_idx:]
            )
            print("Updated LANDING_HTML with 56 rows successfully!")
        else:
            print("ERROR: could not find tbody boundaries in LANDING_HTML")
    else:
        print("ERROR: old_table_header not found in LANDING_HTML")

    # 2. Update DASHBOARD_HTML text references
    code = code.replace(
        "Defense Gateway, 45 MCP tools, L402 Lightning payments, Why-Trail auditor.",
        "Defense Gateway, 56 MCP tools, L402 Lightning payments, Why-Trail auditor."
    )
    code = code.replace(
        '<option value="">Seleccionar herramienta MCP (1-45)...</option>',
        '<option value="">Seleccionar herramienta MCP (1-56)...</option>'
    )
    code = code.replace(
        "setTxt('active-tools', (data.gateway?.total_tools ?? 45) + ' Tools');",
        "setTxt('active-tools', (data.gateway?.total_tools ?? 56) + ' Tools');"
    )

    # 3. Add Playground templates for new tools in updatePlaygroundTemplate
    target_anchor = 'query_agent_threat_score: { target_agent_id: "bad_bot_99", requesting_agent_id: "admin" }'
    new_templates = (
        'query_agent_threat_score: { target_agent_id: "bad_bot_99", requesting_agent_id: "admin" },\n'
        '        propose_trade_envelope: { symbol: "BTCUSDT", side: "BUY", notional_usd: 150.0, max_slippage_pct: 0.5, current_24h_drawdown_pct: 1.2 },\n'
        '        simulate_order_mev_protection: { chain_id: 1, target_dex: "UniswapV3", pool_address: "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", trade_size_usd: 150.0 },\n'
        '        enforce_trading_circuit_breaker: { agent_id: "agent_trade_01", consecutive_losses: 1, rolling_24h_drawdown_pct: 2.1, max_allowed_drawdown_pct: 5.0 },\n'
        '        audit_mcp_tool_metadata_poisoning: { mcp_manifest_json: "{\\"name\\": \\"safe_tool\\", \\"description\\": \\"Normal tool\\"}" },\n'
        '        enforce_denial_of_wallet_quota: { session_id: "sess_01", prompt_tokens: 150, completion_tokens: 400, thinking_tokens: 200, current_cost_usd: 0.05, max_budget_usd: 2.0 },\n'
        '        audit_eip712_permit_drainer_payload: { primary_type: "Permit2", domain: { verifyingContract: "0x000000000022d473030f116ddee9f6b43ac78ba3" }, message: { spender: "0x000046a6f1e8093b16752765b2633054170845a7", value: "1000" } },\n'
        '        verify_meatspace_attestation: { task_id: "rentahuman_bounty_101", challenge_nonce: "nonce_7788", hardware_attestation_type: "secure_enclave", hardware_signature: "a".repeat(64), image_hash_sha256: "b".repeat(64), exif_timestamp: "2026-11-23T10:00:00Z" },\n'
        '        verify_kya_attestation: { agent_did: "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK", public_key_hex: "e".repeat(64), challenge_payload: "trade_auth", signature_hex: "f".repeat(128), historical_task_count: 50, disputed_task_count: 0, total_volume_usd: 5000.0 },\n'
        '        translate_x402_to_l402_settlement: { source_rail: "x402_base_usdc", target_rail: "l402_lightning_sats", amount: "5.00", service_endpoint_url: "https://api.gateway.example/v1/audit", payer_address_or_pubkey: "0x1234567890abcdef1234567890abcdef12345678" },\n'
        '        verify_ap2_cart_mandate_integrity: { cart_mandate_id: "cart_991", merchant_did: "did:web:merchant.example", client_signature_ed25519: "a1b2c3d4", cart_items: [{ item_id: "sku-1", price_sats: 2500, quantity: 1 }], max_authorized_total_sats: 3000 },\n'
        '        serialize_geo_product_catalog: { catalog_items: [{ item_id: "sku_sentinel", name: "Agentic Threat Sentinel", description: "Pre-sign EIP-712 and Denial-of-Wallet defense", price_usd: 25.0, currency: "USD" }] }'
    )

    if target_anchor in code:
        code = code.replace(target_anchor, new_templates)
        print("Updated updatePlaygroundTemplate with all new tools!")
    else:
        print("ERROR: target_anchor not found in updatePlaygroundTemplate")

    with open(GATEWAY_PATH, "w", encoding="utf-8") as f:
        f.write(code)
    print("Saved agents/api_gateway.py successfully!")

if __name__ == "__main__":
    main()
