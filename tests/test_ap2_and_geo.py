"""
Tests unitarios y de integración para las Herramientas #46 y #47:
- Tool #46: verify_ap2_cart_mandate_integrity
- Tool #47: serialize_geo_product_catalog
"""

import pytest
from ap2_and_geo_suite import (
    CartItem,
    CartMandateInput,
    GEOCatalogInput,
    RawProductItem,
    compute_canonical_cart_hash,
    serialize_geo_product_catalog,
    verify_ap2_cart_mandate_integrity,
)
from mcp_server import MoltbookMonetizationMCPServer


def test_verify_ap2_cart_mandate_success():
    items = [
        CartItem(item_id="item-1", sku="SKU-GPU-01", name="GPU H100 Compute Unit", unit_price=2.50, quantity=2, currency="USD"),
        CartItem(item_id="item-2", sku="SKU-STORAGE-01", name="NVMe Fast Buffer 1TB", unit_price=0.50, quantity=1, currency="USD"),
    ]
    expected_total = 5.50
    canonical_hash = compute_canonical_cart_hash(items, "USD", expected_total)

    payload = CartMandateInput(
        mandate_id="mandate-test-01",
        cart_items=items,
        expected_total=expected_total,
        currency="USD",
        spending_limit=10.00,
        presence_mode="HUMAN_NOT_PRESENT",
        cart_state_hash=canonical_hash,
    )
    result = verify_ap2_cart_mandate_integrity(payload)
    assert result.status == "VERIFIED"
    assert result.tampering_detected is False
    assert result.budget_exceeded is False
    assert result.calculated_total == 5.50
    assert result.canonical_cart_hash == canonical_hash


def test_verify_ap2_cart_mandate_tampering_detected():
    items = [
        CartItem(item_id="item-1", sku="SKU-GPU-01", name="GPU H100 Compute Unit", unit_price=2.50, quantity=2, currency="USD"),
    ]
    payload = CartMandateInput(
        mandate_id="mandate-test-02",
        cart_items=items,
        expected_total=5.00,
        currency="USD",
        spending_limit=10.00,
        presence_mode="HUMAN_NOT_PRESENT",
        cart_state_hash="0000000000000000000000000000000000000000000000000000000000000000",
    )
    result = verify_ap2_cart_mandate_integrity(payload)
    assert result.status == "REJECTED"
    assert result.tampering_detected is True


def test_verify_ap2_cart_mandate_budget_exceeded():
    items = [
        CartItem(item_id="item-1", sku="SKU-AUDIT-01", name="Enterprise AST Audit", unit_price=50.00, quantity=1, currency="USD"),
    ]
    payload = CartMandateInput(
        mandate_id="mandate-test-03",
        cart_items=items,
        expected_total=50.00,
        currency="USD",
        spending_limit=25.00,  # Límite inferior al costo
        presence_mode="HUMAN_NOT_PRESENT",
    )
    result = verify_ap2_cart_mandate_integrity(payload)
    assert result.status == "REJECTED"
    assert result.budget_exceeded is True


def test_serialize_geo_product_catalog_success():
    products = [
        RawProductItem(
            name="A2A AST Security Scanner",
            description="Deep static analysis for MCP tools",
            sku="SKU-AST-01",
            price=2.00,
            currency="USD",
            availability="https://schema.org/InStock",
            category="Security",
            specifications={"latency_ms": 15, "supported_standards": "OWASP Agentic Top 10"},
        ),
        RawProductItem(
            name="Why-Trail Forensic Ledger Access",
            description="Cryptographic causal logging",
            sku="SKU-WHY-01",
            price=0.50,
            currency="USD",
            availability="https://schema.org/InStock",
            category="Compliance",
        ),
    ]
    payload = GEOCatalogInput(
        merchant_name="A2A Defense Gateway",
        catalog_id="cat-01",
        products=products,
    )
    result = serialize_geo_product_catalog(payload)
    assert result.status == "SUCCESS"
    assert result.geo_readiness_score == 1.0
    assert result.total_products == 2
    assert "@context" in result.schema_org_json_ld
    assert result.schema_org_json_ld["@type"] == "ItemList"
    assert len(result.schema_org_json_ld["itemListElement"]) == 2


def test_mcp_server_dispatches_new_tools():
    server = MoltbookMonetizationMCPServer()
    assert len(server.list_tools()) == 50

    # Test call tool 46
    res_ap2 = server.call_tool(
        name="verify_ap2_cart_mandate_integrity",
        arguments={
            "mandate_id": "test-mcp-46",
            "cart_items": [
                {"item_id": "1", "sku": "S1", "name": "Item 1", "unit_price": 10.0, "quantity": 1}
            ],
            "expected_total": 10.0,
            "spending_limit": 20.0,
        },
    )
    assert res_ap2["status"] == "VERIFIED"

    # Test call tool 47
    res_geo = server.call_tool(
        name="serialize_geo_product_catalog",
        arguments={
            "merchant_name": "Test Store",
            "catalog_id": "cat-mcp-47",
            "products": [
                {"name": "Tool Test", "sku": "SKU-T", "price": 5.0}
            ],
        },
    )
    assert res_geo["status"] == "SUCCESS"
    assert res_geo["geo_readiness_score"] == 1.0
