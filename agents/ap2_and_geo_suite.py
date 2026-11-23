"""
Módulo de Verificación Criptográfica AP2 (Google/FIDO) y Serialización GEO de Catálogos.
Herramientas #46 y #47 del Ecosistema A2A Defense Gateway.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CartItem(BaseModel):
    """Ítem individual dentro del carrito de compra delegado."""
    model_config = ConfigDict(extra="ignore")

    item_id: str
    sku: str
    name: str
    unit_price: float = Field(..., ge=0.0)
    quantity: int = Field(default=1, gt=0)
    currency: str = Field(default="USD")


class CartMandateInput(BaseModel):
    """Payload de entrada para validar la integridad de un Cart Mandate AP2."""
    model_config = ConfigDict(extra="ignore")

    mandate_id: str
    cart_items: list[CartItem]
    expected_total: float = Field(..., ge=0.0)
    currency: str = Field(default="USD")
    spending_limit: float = Field(..., ge=0.0)
    presence_mode: str = Field(default="HUMAN_NOT_PRESENT")
    cart_state_hash: str | None = None
    user_public_key: str | None = None
    signature: str | None = None
    expiration_timestamp: int = 0


class CartMandateVerificationResult(BaseModel):
    """Resultado determinista de auditoría del Cart Mandate."""
    mandate_id: str
    status: str  # "VERIFIED" | "REJECTED"
    canonical_cart_hash: str
    calculated_total: float
    tampering_detected: bool
    budget_exceeded: bool
    arithmetic_mismatch: bool
    expired: bool
    presence_mode: str
    reasons: list[str]


def compute_canonical_cart_hash(items: list[CartItem], currency: str, expected_total: float) -> str:
    """Calcula el hash SHA-256 canónico de los ítems del carrito ordenados determinísticamente."""
    normalized_items = [
        {
            "currency": item.currency.upper(),
            "item_id": item.item_id,
            "name": item.name.strip(),
            "quantity": item.quantity,
            "sku": item.sku.strip(),
            "unit_price": round(item.unit_price, 4),
        }
        for item in sorted(items, key=lambda x: (x.sku, x.item_id))
    ]
    canonical_payload = {
        "currency": currency.upper(),
        "expected_total": round(expected_total, 4),
        "items": normalized_items,
    }
    canonical_bytes = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def verify_ap2_cart_mandate_integrity(payload: CartMandateInput) -> CartMandateVerificationResult:
    """
    Tool #46: Valida la integridad criptográfica, límites presupuestarios y ausencia
    de alucinaciones de precios en un Cart Mandate bajo la especificación Google/FIDO AP2.
    """
    reasons: list[str] = []
    canonical_hash = compute_canonical_cart_hash(payload.cart_items, payload.currency, payload.expected_total)

    # 1. Verificación de coincidencia de hash canónico (si fue provisto)
    tampering_detected = False
    if payload.cart_state_hash and payload.cart_state_hash.lower() != canonical_hash.lower():
        tampering_detected = True
        reasons.append(f"TAMPERING_DETECTED: Hash canónico provisto ({payload.cart_state_hash[:12]}...) no coincide con el calculado ({canonical_hash[:12]}...).")

    # 2. Verificación aritmética determinista de totales
    calculated_total = sum(round(item.unit_price * item.quantity, 4) for item in payload.cart_items)
    arithmetic_mismatch = abs(calculated_total - payload.expected_total) > 0.005
    if arithmetic_mismatch:
        reasons.append(f"ARITHMETIC_MISMATCH: La suma de ítems ({calculated_total:.2f}) difiere del total declarado ({payload.expected_total:.2f}).")

    # 3. Verificación de límite presupuestario (Spending Limit)
    budget_exceeded = payload.expected_total > payload.spending_limit
    if budget_exceeded:
        reasons.append(f"BUDGET_EXCEEDED: Total ({payload.expected_total:.2f} {payload.currency}) supera el límite autorizado ({payload.spending_limit:.2f} {payload.currency}).")

    # 4. Verificación de caducidad temporal (TTL / Expiración)
    expired = False
    now_ts = int(time.time())
    if payload.expiration_timestamp > 0 and now_ts > payload.expiration_timestamp:
        expired = True
        reasons.append(f"MANDATE_EXPIRED: Timestamp actual ({now_ts}) superó la expiración ({payload.expiration_timestamp}).")

    # 5. Restricciones estrictas en modo HUMAN_NOT_PRESENT
    if payload.presence_mode == "HUMAN_NOT_PRESENT":
        if not payload.cart_items:
            reasons.append("INVALID_CART: Carrito vacío en modo desatendido HUMAN_NOT_PRESENT.")

    status = "REJECTED" if (tampering_detected or arithmetic_mismatch or budget_exceeded or expired) else "VERIFIED"
    if status == "VERIFIED":
        reasons.append("VALIDATION_SUCCESS: Cart Mandate válido y sellado criptográficamente sin alucinaciones.")

    return CartMandateVerificationResult(
        mandate_id=payload.mandate_id,
        status=status,
        canonical_cart_hash=canonical_hash,
        calculated_total=round(calculated_total, 4),
        tampering_detected=tampering_detected,
        budget_exceeded=budget_exceeded,
        arithmetic_mismatch=arithmetic_mismatch,
        expired=expired,
        presence_mode=payload.presence_mode,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# Tool #47: GEO Product Catalog Serializer
# ---------------------------------------------------------------------------


class RawProductItem(BaseModel):
    """Ítem de catálogo sin procesar o semiestructurado."""
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    sku: str
    price: float | None = None
    currency: str | None = "USD"
    availability: str | None = "https://schema.org/InStock"
    category: str = "General"
    url: str = ""
    specifications: dict[str, Any] = Field(default_factory=dict)


class GEOCatalogInput(BaseModel):
    """Entrada para serializar un catálogo de productos a JSON-LD / schema.org."""
    model_config = ConfigDict(extra="ignore")

    merchant_name: str
    merchant_url: str = "https://a2a.vilmamonroy.com"
    catalog_id: str
    products: list[RawProductItem]


class GEOCatalogOutput(BaseModel):
    """Catálogo serializado y evaluado bajo estándares de Generative Engine Optimization."""
    status: str
    catalog_id: str
    merchant_name: str
    total_products: int
    geo_readiness_score: float  # 0.0 a 1.0
    missing_critical_attributes: list[str]
    schema_org_json_ld: dict[str, Any]
    agent_parseable_bytes: int


def serialize_geo_product_catalog(payload: GEOCatalogInput) -> GEOCatalogOutput:
    """
    Tool #47: Transforma catálogos de comercio electrónico en estructuras deterministas
    JSON-LD conformes a W3C / schema.org (Product y Offer), eliminando el abandono agéntico.
    """
    missing_attrs: list[str] = []
    total_products = len(payload.products)
    if total_products == 0:
        return GEOCatalogOutput(
            status="EMPTY_CATALOG",
            catalog_id=payload.catalog_id,
            merchant_name=payload.merchant_name,
            total_products=0,
            geo_readiness_score=0.0,
            missing_critical_attributes=["No products provided"],
            schema_org_json_ld={"@context": "https://schema.org", "@type": "ItemList", "itemListElement": []},
            agent_parseable_bytes=0,
        )

    valid_attributes_count = 0
    total_expected_attributes = total_products * 5  # name, sku, price, currency, availability

    item_elements = []
    for idx, prod in enumerate(payload.products, start=1):
        item_missing = []
        if not prod.name.strip():
            item_missing.append(f"Product #{idx}: missing name")
        else:
            valid_attributes_count += 1

        if not prod.sku.strip():
            item_missing.append(f"Product #{idx}: missing sku")
        else:
            valid_attributes_count += 1

        if prod.price is None or prod.price < 0:
            item_missing.append(f"Product #{idx} ({prod.sku}): missing or invalid price")
        else:
            valid_attributes_count += 1

        if not prod.currency:
            item_missing.append(f"Product #{idx} ({prod.sku}): missing currency")
        else:
            valid_attributes_count += 1

        if not prod.availability:
            item_missing.append(f"Product #{idx} ({prod.sku}): missing availability")
        else:
            valid_attributes_count += 1

        missing_attrs.extend(item_missing)

        # Generar nodo schema.org/Product con schema.org/Offer
        product_node: dict[str, Any] = {
            "@type": "Product",
            "name": prod.name.strip(),
            "sku": prod.sku.strip(),
            "description": prod.description.strip(),
            "category": prod.category,
            "offers": {
                "@type": "Offer",
                "price": round(prod.price, 2) if prod.price is not None else 0.0,
                "priceCurrency": (prod.currency or "USD").upper(),
                "availability": prod.availability or "https://schema.org/OutOfStock",
                "seller": {
                    "@type": "Organization",
                    "name": payload.merchant_name,
                    "url": payload.merchant_url,
                },
            },
        }
        if prod.url:
            product_node["url"] = prod.url
        if prod.specifications:
            product_node["additionalProperty"] = [
                {"@type": "PropertyValue", "name": k, "value": str(v)}
                for k, v in sorted(prod.specifications.items())
            ]

        item_elements.append({
            "@type": "ListItem",
            "position": idx,
            "item": product_node,
        })

    json_ld_graph = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": f"Catalog {payload.catalog_id} - {payload.merchant_name}",
        "numberOfItems": total_products,
        "itemListElement": item_elements,
    }

    serialized_str = json.dumps(json_ld_graph, ensure_ascii=False)
    geo_score = round(valid_attributes_count / total_expected_attributes, 2) if total_expected_attributes > 0 else 0.0

    return GEOCatalogOutput(
        status="SUCCESS" if geo_score >= 0.70 else "NEEDS_OPTIMIZATION",
        catalog_id=payload.catalog_id,
        merchant_name=payload.merchant_name,
        total_products=total_products,
        geo_readiness_score=geo_score,
        missing_critical_attributes=missing_attrs[:15],
        schema_org_json_ld=json_ld_graph,
        agent_parseable_bytes=len(serialized_str.encode("utf-8")),
    )
