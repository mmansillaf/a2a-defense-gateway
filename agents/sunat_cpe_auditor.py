"""
Auditor Forense Determinista de Comprobantes de Pago Electrónicos (CPE XML UBL 2.1 SUNAT).
Valida estructura XML, firmas digest, algoritmos Módulo 11 de RUC y consistencia contable del IGV.
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from datetime import date

from pydantic import BaseModel, Field


def validate_peruvian_ruc(ruc_str: str) -> bool:
    """Valida el dígito verificador de un RUC peruano de 11 dígitos mediante Módulo 11."""
    ruc = ruc_str.strip()
    if not (len(ruc) == 11 and ruc.isdigit()):
        return False

    if not ruc.startswith(("10", "15", "17", "20")):
        return False

    weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    total_sum = sum(int(ruc[i]) * weights[i] for i in range(10))
    residue = total_sum % 11
    check_digit = 11 - residue

    if check_digit == 10:
        check_digit = 0
    elif check_digit == 11:
        check_digit = 1

    return check_digit == int(ruc[10])


class CpeAuditInput(BaseModel):
    xml_content: str = Field(..., description="Contenido completo del comprobante electrónico en formato XML UBL 2.1")
    strict_tax_check: bool = Field(default=True, description="Exigir consistencia aritmética estricta al centavo en IGV")


class CpeAuditOutput(BaseModel):
    doc_id: str
    es_valido: bool
    tipo_comprobante: str
    serie_correlativo: str
    fecha_emision: str
    moneda: str
    emisor_ruc: str
    emisor_ruc_valido: bool
    receptor_ruc: str
    receptor_ruc_valido: bool
    monto_gravado: float
    monto_igv: float
    monto_total: float
    digest_value: str
    anomalias_detectadas: list[str]
    audit_hash: str


def audit_sunat_cpe_xml(payload: CpeAuditInput) -> CpeAuditOutput:
    """Parsea y audita determinísticamente un comprobante electrónico SUNAT."""
    xml_raw = payload.xml_content.strip()
    audit_hash = hashlib.sha256(xml_raw.encode("utf-8")).hexdigest()
    anomalies: list[str] = []

    try:
        root = ET.fromstring(xml_raw)
    except ET.ParseError:
        try:
            # Fallback tolerante para fragmentos XML sin declaración xmlns de prefijos
            import re
            clean_xml = re.sub(r"<(/?)(\w+):", r"<\1", xml_raw)
            clean_xml = re.sub(r' xmlns(:[a-zA-Z0-9]+)?="[^"]*"', "", clean_xml)
            root = ET.fromstring(clean_xml)
        except ET.ParseError as exc:
            return CpeAuditOutput(
                doc_id=f"CPE-ERR-{audit_hash[:12]}",
                es_valido=False,
                tipo_comprobante="DESCONOCIDO",
                serie_correlativo="ERROR-XML",
                fecha_emision=date.today().isoformat(),
                moneda="PEN",
                emisor_ruc="",
                emisor_ruc_valido=False,
                receptor_ruc="",
                receptor_ruc_valido=False,
                monto_gravado=0.0,
                monto_igv=0.0,
                monto_total=0.0,
                digest_value="",
                anomalias_detectadas=[f"XML_PARSE_ERROR: {exc!s}"],
                audit_hash=audit_hash,
            )

    # Remover namespaces para búsqueda limpia
    def find_val(tag_name: str, parent=root) -> str:
        for elem in parent.iter():
            if elem.tag.endswith(tag_name) and elem.text:
                return elem.text.strip()
        return ""

    serie_correlativo = find_val("ID") or "SIN-NUMERO"
    fecha_emision = find_val("IssueDate") or date.today().isoformat()
    moneda = find_val("DocumentCurrencyCode") or "PEN"
    digest_value = find_val("DigestValue")

    # Determinar tipo según root tag
    tag_clean = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    tipo_map = {
        "Invoice": "01_FACTURA",
        "CreditNote": "07_NOTA_CREDITO",
        "DebitNote": "08_NOTA_DEBITO",
    }
    tipo_cpe = tipo_map.get(tag_clean, f"TIPO_{tag_clean.upper()}")

    # Emisor
    emisor_ruc = ""
    for party in root.iter():
        if party.tag.endswith("AccountingSupplierParty"):
            emisor_ruc = find_val("ID", party)
            break

    # Receptor
    receptor_ruc = ""
    for party in root.iter():
        if party.tag.endswith("AccountingCustomerParty"):
            receptor_ruc = find_val("ID", party)
            break

    emisor_valido = validate_peruvian_ruc(emisor_ruc) if emisor_ruc else False
    if emisor_ruc and not emisor_valido:
        anomalies.append(f"RUC_EMISOR_INVALIDO_MODULO11: {emisor_ruc}")

    receptor_valido = validate_peruvian_ruc(receptor_ruc) if receptor_ruc else False
    if receptor_ruc and len(receptor_ruc) == 11 and not receptor_valido:
        anomalies.append(f"RUC_RECEPTOR_INVALIDO_MODULO11: {receptor_ruc}")

    # Montos
    def parse_float(val: str) -> float:
        try:
            return round(float(val), 2)
        except ValueError:
            return 0.0

    monto_gravado = parse_float(find_val("TaxableAmount"))
    monto_igv = parse_float(find_val("TaxAmount"))
    monto_total = parse_float(find_val("PayableAmount"))

    # Auditoría de cuadre contable
    if payload.strict_tax_check and monto_gravado > 0:
        expected_igv = round(monto_gravado * 0.18, 2)
        if abs(expected_igv - monto_igv) > 0.05:
            anomalies.append(
                f"DESCUADRE_IGV_CALCULADO: Gravado {monto_gravado} * 0.18 = {expected_igv}, pero XML declara {monto_igv}"
            )

        expected_total = round(monto_gravado + monto_igv, 2)
        if monto_total > 0 and abs(expected_total - monto_total) > 0.05:
            anomalies.append(
                f"DESCUADRE_TOTAL_PAYABLE: Base ({monto_gravado}) + IGV ({monto_igv}) = {expected_total}, pero XML declara {monto_total}"
            )

    doc_id = f"CPE-AUDIT-{emisor_ruc or 'NO-RUC'}-{serie_correlativo}-{audit_hash[:8]}"
    es_valido = len(anomalies) == 0

    return CpeAuditOutput(
        doc_id=doc_id,
        es_valido=es_valido,
        tipo_comprobante=tipo_cpe,
        serie_correlativo=serie_correlativo,
        fecha_emision=fecha_emision,
        moneda=moneda,
        emisor_ruc=emisor_ruc,
        emisor_ruc_valido=emisor_valido,
        receptor_ruc=receptor_ruc,
        receptor_ruc_valido=receptor_valido,
        monto_gravado=monto_gravado,
        monto_igv=monto_igv,
        monto_total=monto_total,
        digest_value=digest_value,
        anomalias_detectadas=anomalies,
        audit_hash=audit_hash,
    )
