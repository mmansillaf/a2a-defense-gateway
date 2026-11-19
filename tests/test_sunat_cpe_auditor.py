"""
Pruebas Unitarias para el Auditor Forense SUNAT CPE XML UBL 2.1.
Valida cálculo Módulo 11 de RUC, cuadre del 18% IGV y detección de anomalías.
"""

from sunat_cpe_auditor import (
    CpeAuditInput,
    audit_sunat_cpe_xml,
    validate_peruvian_ruc,
)


def test_validate_peruvian_ruc_modulo_11():
    assert validate_peruvian_ruc("20131312955") is True  # SUNAT oficial
    assert validate_peruvian_ruc("20100070970") is True  # Banco de la Nación
    assert validate_peruvian_ruc("20131312959") is False  # Dígito verificador alterado
    assert validate_peruvian_ruc("12345") is False  # Longitud inválida
    assert validate_peruvian_ruc("30131312955") is False  # Prefijo no peruano


def test_audit_valid_sunat_invoice_xml():
    xml_sample = """<?xml version="1.0" encoding="UTF-8"?>
    <Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
             xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
             xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
             xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <cbc:ID>F001-00045231</cbc:ID>
        <cbc:IssueDate>2026-11-15</cbc:IssueDate>
        <cbc:DocumentCurrencyCode>PEN</cbc:DocumentCurrencyCode>
        <cac:AccountingSupplierParty>
            <cac:Party>
                <cac:PartyIdentification>
                    <cbc:ID>20131312955</cbc:ID>
                </cac:PartyIdentification>
            </cac:Party>
        </cac:AccountingSupplierParty>
        <cac:AccountingCustomerParty>
            <cac:Party>
                <cac:PartyIdentification>
                    <cbc:ID>20100070970</cbc:ID>
                </cac:PartyIdentification>
            </cac:Party>
        </cac:AccountingCustomerParty>
        <cac:TaxTotal>
            <cbc:TaxAmount currencyID="PEN">180.00</cbc:TaxAmount>
            <cac:TaxSubtotal>
                <cbc:TaxableAmount currencyID="PEN">1000.00</cbc:TaxableAmount>
                <cbc:TaxAmount currencyID="PEN">180.00</cbc:TaxAmount>
            </cac:TaxSubtotal>
        </cac:TaxTotal>
        <cac:LegalMonetaryTotal>
            <cbc:PayableAmount currencyID="PEN">1180.00</cbc:PayableAmount>
        </cac:LegalMonetaryTotal>
        <ds:DigestValue>8mN9/qZtYmZl1+vA5B6C=</ds:DigestValue>
    </Invoice>
    """
    res = audit_sunat_cpe_xml(CpeAuditInput(xml_content=xml_sample))
    assert res.es_valido is True
    assert res.tipo_comprobante == "01_FACTURA"
    assert res.serie_correlativo == "F001-00045231"
    assert res.emisor_ruc == "20131312955"
    assert res.emisor_ruc_valido is True
    assert res.monto_gravado == 1000.00
    assert res.monto_igv == 180.00
    assert res.monto_total == 1180.00
    assert len(res.anomalias_detectadas) == 0
    assert res.doc_id.startswith("CPE-AUDIT-20131312955-F001-00045231")


def test_audit_detects_tax_mismatch_and_invalid_ruc():
    # Factura con IGV desfasado y RUC emisor falso
    xml_fraud = """<?xml version="1.0" encoding="UTF-8"?>
    <Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">
        <cbc:ID>F001-00000001</cbc:ID>
        <cac:AccountingSupplierParty>
            <cbc:ID>20131312959</cbc:ID>
        </cac:AccountingSupplierParty>
        <cac:TaxTotal>
            <cbc:TaxAmount>100.00</cbc:TaxAmount>
            <cbc:TaxableAmount>1000.00</cbc:TaxableAmount>
        </cac:TaxTotal>
        <cac:LegalMonetaryTotal>
            <cbc:PayableAmount>1100.00</cbc:PayableAmount>
        </cac:LegalMonetaryTotal>
    </Invoice>
    """
    res = audit_sunat_cpe_xml(CpeAuditInput(xml_content=xml_fraud))
    assert res.es_valido is False
    assert res.emisor_ruc_valido is False
    assert any("RUC_EMISOR_INVALIDO" in a for a in res.anomalias_detectadas)
    assert any("DESCUADRE_IGV" in a for a in res.anomalias_detectadas)
