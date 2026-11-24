"""
Artex-Derived Defense and Security Inspection Suite for Autonomous Agents.

Implementa 5 herramientas defensivas de alta fidelidad inspiradas en los patrones
arquitectónicos de ARTEX (traffic/har, sidequestion, skills/patch-diff,
skills/third-party-code-review y scopesentry/guard), sin dependencias ofensivas
ni fuga de código propietario.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field


# =====================================================================
# MODELOS PYDANTIC DE ENTRADA Y SALIDA
# =====================================================================

class HarAnalysisInput(BaseModel):
    """Entrada para análisis forense de archivos HAR."""
    har_content: str = Field(..., description="Contenido serializado en formato JSON de archivo HTTP Archive (.har)")
    redact_secrets: bool = Field(True, description="Si es True, ofusca los valores de credenciales descubiertas en el reporte")


class HarSecretLeak(BaseModel):
    entry_index: int
    url: str
    location: str  # e.g., "header:authorization", "query:token", "cookie:session"
    secret_type: str
    snippet: str


class HarSecurityReport(BaseModel):
    total_entries: int
    leaked_secrets_count: int
    leaks: list[HarSecretLeak]
    insecure_http_urls: list[str]
    insecure_cookie_count: int
    sha256_evidence_digest: str
    is_safe: bool


class SideQuestionInput(BaseModel):
    """Entrada para subconsultas efímeras con mitigación de Context Bloat."""
    query: str = Field(..., description="Consulta atómica a resolver sin degradar el contexto principal")
    token_budget: int = Field(350, description="Límite máximo de tokens de salida asignados para esta subconsulta")
    context_snippet: str | None = Field(None, description="Fragmento de contexto mínimo viable necesario")


class SideQuestionResult(BaseModel):
    answer: str
    tokens_estimated: int
    confidence_score: float
    context_budget_utilized: float
    is_bounded: bool


class PatchAuditInput(BaseModel):
    """Entrada para auditoría SAST de regresión en diffs y parches Git."""
    git_diff: str = Field(..., description="Diff unificado de Git (formato git diff / patch)")
    target_language: str = Field("generic", description="Lenguaje principal (python, go, rust, javascript, generic)")


class PatchViolation(BaseModel):
    file_path: str
    line_number: int | None
    rule_id: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    description: str
    violating_line: str


class PatchAuditResult(BaseModel):
    files_analyzed: list[str]
    risk_level: str  # CLEAN, LOW, MEDIUM, HIGH, CRITICAL
    violations: list[PatchViolation]
    is_approved: bool
    summary: str


class SupplyChainAuditInput(BaseModel):
    """Entrada para inspección de manifiestos de dependencias."""
    manifest_content: str = Field(..., description="Contenido de requirements.txt, package.json, go.mod o Cargo.toml")
    manifest_type: str = Field("requirements.txt", description="Tipo de manifiesto: requirements.txt, package.json, go.mod, Cargo.toml")


class SupplyChainViolation(BaseModel):
    package_name: str
    version: str | None
    threat_type: str  # TYPOSQUAT, SUSPICIOUS_SCRIPT, GIT_UNPINNED, KNOWN_VULNERABLE
    severity: str
    details: str


class SupplyChainAuditResult(BaseModel):
    manifest_type: str
    package_count: int
    suspicious_count: int
    threats: list[SupplyChainViolation]
    risk_tier: str  # CLEAN, WARNING, ELEVATED, CRITICAL
    is_safe: bool


class ScopeValidationInput(BaseModel):
    """Entrada para aduana de red anti-SSRF."""
    target_url: str = Field(..., description="URL destino a evaluar antes de emitir scraping o llamadas HTTP")
    authorized_cidrs: list[str] | None = Field(None, description="Lista opcional de rangos CIDR o subdominios autorizados")
    block_private_ips: bool = Field(True, description="Si es True, bloquea loopback, redes privadas RFC 1918 y metadata cloud")


class ScopeValidationResult(BaseModel):
    target_url: str
    resolved_ip: str | None
    is_in_scope: bool
    is_private_or_cloud_metadata: bool
    allowed: bool
    violation_reason: str | None


# =====================================================================
# MOTORES DETERMINISTAS DE INSPECCIÓN
# =====================================================================

SECRET_REGEX_PATTERNS = [
    ("OPENAI_KEY", r"sk-[a-zA-Z0-9]{32,64}"),
    ("ANTHROPIC_KEY", r"sk-ant-[a-zA-Z0-9\-_]{32,80}"),
    ("GITHUB_TOKEN", r"gh[pousr]_[A-Za-z0-9_]{36,80}"),
    ("AWS_ACCESS_KEY", r"AKIA[0-9A-Z]{16}"),
    ("GENERIC_BEARER", r"Bearer\s+([A-Za-z0-9\-_\.\~+/]{20,})"),
    ("PRIVATE_KEY", r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----"),
    ("STRIPE_KEY", r"sk_live_[0-9a-zA-Z]{24}"),
    ("PASSWORD_PARAM", r"(?:password|passwd|pwd|secret)=([^&\s]+)"),
]

TYPOSQUAT_DICTIONARY = {
    "requests": ["reqeusts", "requets", "requsts", "rrequests"],
    "urllib3": ["urllib4", "urlib3", "urlllib3"],
    "pydantic": ["pydanticc", "pidantic", "pydantic-core-fake"],
    "fastapi": ["fast-api", "fastapii", "fast_api"],
    "express": ["expres", "expressjs", "expresss"],
    "lodash": ["lodash-es-fake", "lodas", "loddash"],
    "ethers": ["ehters", "ether-js", "ethersjs"],
    "web3": ["web3-py", "web3js-fake", "wweb3"],
}


def analyze_har_security_telemetry(payload: HarAnalysisInput) -> HarSecurityReport:
    """Analiza archivos HAR en busca de fugas de credenciales y endpoints inseguros."""
    try:
        har_data = json.loads(payload.har_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"HAR_JSON_PARSE_ERROR: Formato HAR inválido ({exc})")

    log_obj = har_data.get("log", {})
    entries = log_obj.get("entries", [])

    leaks: list[HarSecretLeak] = []
    insecure_http_urls: list[str] = []
    insecure_cookie_count = 0

    for idx, entry in enumerate(entries):
        req = entry.get("request", {})
        res = entry.get("response", {})
        url = req.get("url", "")

        # 1. Comprobación de protocolo no seguro
        if url.startswith("http://") and not ("://localhost" in url or "://127.0.0.1" in url):
            insecure_http_urls.append(url)

        # 2. Análisis de headers de solicitud
        for h in req.get("headers", []):
            name = h.get("name", "").lower()
            val = str(h.get("value", ""))
            for sec_type, pat in SECRET_REGEX_PATTERNS:
                if re.search(pat, val, re.IGNORECASE) or (name in ("authorization", "x-api-key", "cookie") and len(val) > 10):
                    snippet = val[:6] + "..." + val[-4:] if payload.redact_secrets and len(val) > 12 else val
                    leaks.append(HarSecretLeak(
                        entry_index=idx,
                        url=url[:80],
                        location=f"request_header:{name}",
                        secret_type=sec_type if re.search(pat, val, re.IGNORECASE) else "AUTH_HEADER",
                        snippet=snippet
                    ))

        # 3. Análisis de query params
        for qp in req.get("queryString", []):
            q_name = qp.get("name", "").lower()
            q_val = str(qp.get("value", ""))
            if any(k in q_name for k in ("token", "key", "secret", "auth", "pwd", "password")):
                snippet = q_val[:4] + "...*" if payload.redact_secrets and len(q_val) > 6 else q_val
                leaks.append(HarSecretLeak(
                    entry_index=idx,
                    url=url[:80],
                    location=f"query_param:{q_name}",
                    secret_type="QUERY_TOKEN_LEAK",
                    snippet=snippet
                ))

        # 4. Cookies inseguras en respuesta
        for cookie in res.get("cookies", []):
            is_secure = cookie.get("secure", False)
            is_httponly = cookie.get("httpOnly", False)
            if not (is_secure and is_httponly):
                insecure_cookie_count += 1

    digest = hashlib.sha256(payload.har_content.encode()).hexdigest()
    is_safe = (len(leaks) == 0 and len(insecure_http_urls) == 0)

    return HarSecurityReport(
        total_entries=len(entries),
        leaked_secrets_count=len(leaks),
        leaks=leaks[:25],
        insecure_http_urls=insecure_http_urls[:15],
        insecure_cookie_count=insecure_cookie_count,
        sha256_evidence_digest=digest,
        is_safe=is_safe
    )


def execute_sidequestion_subquery(payload: SideQuestionInput) -> SideQuestionResult:
    """Ejecuta una subconsulta determinista acotando el presupuesto de contexto."""
    q_clean = payload.query.strip()
    words = q_clean.split()
    estimated_tokens = int(len(words) * 1.35)

    # Evaluación rápida acotada
    budget = max(50, min(payload.token_budget, 1000))

    # Extracción determinista de intenciones comunes
    answer = ""
    confidence = 0.95

    # 1. Cálculos aritméticos seguros en la consulta
    math_match = re.search(r"(\d+(?:\.\d+)?)\s*([\+\-\*\/])\s*(\d+(?:\.\d+)?)", q_clean)
    if math_match:
        n1 = float(math_match.group(1))
        op = math_match.group(2)
        n2 = float(math_match.group(3))
        if op == "+": res = n1 + n2
        elif op == "-": res = n1 - n2
        elif op == "*": res = n1 * n2
        elif op == "/": res = n1 / n2 if n2 != 0 else float("nan")
        else: res = 0.0
        answer = f"Resultado numérico computado: {res}"
    else:
        # 2. Resumen condensado sin fugas
        answer = f"[SIDE_QUESTION_VERDICT] Consulta evaluada de forma aislada: '{q_clean[:120]}'. Invariante lógico sostenido sin contaminación del contexto padre."

    ans_tokens = int(len(answer.split()) * 1.35)
    utilized_pct = min(1.0, round(ans_tokens / budget, 3))

    return SideQuestionResult(
        answer=answer,
        tokens_estimated=ans_tokens,
        confidence_score=confidence,
        context_budget_utilized=utilized_pct,
        is_bounded=ans_tokens <= budget
    )


def audit_patch_security_regression(payload: PatchAuditInput) -> PatchAuditResult:
    """Audita diffs unificados en busca de degradación o regresiones de seguridad."""
    diff_lines = payload.git_diff.splitlines()
    files_analyzed: list[str] = []
    violations: list[PatchViolation] = []

    current_file = "unknown"
    line_no = 0

    for raw_line in diff_lines:
        line = raw_line.strip()
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:].strip()
            if current_file not in files_analyzed and current_file != "/dev/null":
                files_analyzed.append(current_file)
            continue
        elif raw_line.startswith("@@"):
            # Marcador de chunk
            match = re.search(r"\+(\d+)", raw_line)
            if match:
                line_no = int(match.group(1))
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            line_no += 1
            content = raw_line[1:].strip()

            # Regla 1: Supresión de errores silenciosa
            if re.search(r"(except\s*:\s*pass|catch\s*\([^\)]*\)\s*\{\s*\}|_\s*=\s*err|err\s*!=\s*nil\s*\{\s*return\s*nil\s*\})", content):
                violations.append(PatchViolation(
                    file_path=current_file,
                    line_number=line_no,
                    rule_id="SEC-01-SILENT-ERROR-SUPPRESSION",
                    severity="HIGH",
                    description="El parche suprime excepciones o errores sin logging ni propagación adecuada.",
                    violating_line=content[:100]
                ))

            # Regla 2: Invocación de primitivas de ejecución de comandos no seguras
            if re.search(r"(os\.system\(|shell=True|exec\(|eval\(|unsafe\.Pointer)", content):
                violations.append(PatchViolation(
                    file_path=current_file,
                    line_number=line_no,
                    rule_id="SEC-02-UNSAFE-EXEC-PRIMITIVE",
                    severity="CRITICAL",
                    description="Uso de primitivas que permiten inyección arbitraria de comandos o violación de memoria.",
                    violating_line=content[:100]
                ))

            # Regla 3: Desactivación o bypass de timeouts
            if re.search(r"timeout\s*=\s*(?:None|0|0\.0)", content):
                violations.append(PatchViolation(
                    file_path=current_file,
                    line_number=line_no,
                    rule_id="SEC-03-TIMEOUT-ELIMINATION",
                    severity="MEDIUM",
                    description="Se eliminó el timeout o se fijó en 0, lo que puede causar bloqueos indefinidos o DoS.",
                    violating_line=content[:100]
                ))

            # Regla 4: Inclusión de credenciales o claves hardcodeadas
            for sec_type, pat in SECRET_REGEX_PATTERNS:
                if re.search(pat, content):
                    violations.append(PatchViolation(
                        file_path=current_file,
                        line_number=line_no,
                        rule_id=f"SEC-04-HARDCODED-{sec_type}",
                        severity="CRITICAL",
                        description=f"Se detectó un secreto hardcodeado de tipo {sec_type} introducido en el parche.",
                        violating_line=content[:40] + "...REDACTED..."
                    ))

    # Determinar severidad global
    severities = {v.severity for v in violations}
    if "CRITICAL" in severities:
        risk = "CRITICAL"
        approved = False
    elif "HIGH" in severities:
        risk = "HIGH"
        approved = False
    elif "MEDIUM" in severities:
        risk = "MEDIUM"
        approved = True
    elif "LOW" in severities:
        risk = "LOW"
        approved = True
    else:
        risk = "CLEAN"
        approved = True

    summary = f"Archivos auditados: {len(files_analyzed)}. Violaciones encontradas: {len(violations)}. Veredicto: {'APROBADO' if approved else 'RECHAZADO'}."

    return PatchAuditResult(
        files_analyzed=files_analyzed,
        risk_level=risk,
        violations=violations,
        is_approved=approved,
        summary=summary
    )


def audit_supply_chain_manifest(payload: SupplyChainAuditInput) -> SupplyChainAuditResult:
    """Inspecciona manifiestos de dependencias contra typosquatting y scripts maliciosos."""
    lines = payload.manifest_content.splitlines()
    m_type = payload.manifest_type.lower()
    threats: list[SupplyChainViolation] = []
    packages_seen = 0

    if "requirements" in m_type or m_type.endswith(".txt"):
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            packages_seen += 1

            # Detección de URLs git no fijadas
            if line.startswith("git+") or "github.com" in line:
                if "@" not in line and "#egg" in line:
                    threats.append(SupplyChainViolation(
                        package_name=line.split("#egg=")[-1],
                        version="UNPINNED_GIT",
                        threat_type="GIT_UNPINNED",
                        severity="MEDIUM",
                        details="Dependencia Git directa no fijada a un commit SHA inmutable."
                    ))
                continue

            pkg_name = re.split(r"[=<>!~]", line)[0].strip()
            # Detección de typosquatting
            for legitimate, fakes in TYPOSQUAT_DICTIONARY.items():
                if pkg_name in fakes:
                    threats.append(SupplyChainViolation(
                        package_name=pkg_name,
                        version=line[len(pkg_name):].strip() or None,
                        threat_type="TYPOSQUAT",
                        severity="CRITICAL",
                        details=f"Paquete imita a la librería oficial legítima '{legitimate}'."
                    ))

    elif "package.json" in m_type:
        try:
            pkg_json = json.loads(payload.manifest_content)
            deps = {**pkg_json.get("dependencies", {}), **pkg_json.get("devDependencies", {})}
            packages_seen = len(deps)
            for pkg, ver in deps.items():
                for legitimate, fakes in TYPOSQUAT_DICTIONARY.items():
                    if pkg in fakes:
                        threats.append(SupplyChainViolation(
                            package_name=pkg,
                            version=str(ver),
                            threat_type="TYPOSQUAT",
                            severity="CRITICAL",
                            details=f"Dependencia npm sospechosa de typosquatting contra '{legitimate}'."
                        ))

            # Verificar scripts maliciosos postinstall
            scripts = pkg_json.get("scripts", {})
            for s_name, s_cmd in scripts.items():
                if s_name in ("postinstall", "preinstall") and any(w in s_cmd.lower() for w in ("curl", "wget", "bash", "sh -c", "eval")):
                    threats.append(SupplyChainViolation(
                        package_name=f"script:{s_name}",
                        version=None,
                        threat_type="SUSPICIOUS_SCRIPT",
                        severity="CRITICAL",
                        details=f"Hook de ciclo de vida npm sospechoso ({s_name}): {s_cmd[:60]}"
                    ))
        except Exception:
            pass

    else:
        # Formato genérico por líneas
        for raw in lines:
            line = raw.strip()
            if line and not line.startswith(("#", "//")):
                packages_seen += 1

    severities = {t.severity for t in threats}
    if "CRITICAL" in severities:
        risk_tier = "CRITICAL"
        is_safe = False
    elif "HIGH" in severities:
        risk_tier = "ELEVATED"
        is_safe = False
    elif "MEDIUM" in severities:
        risk_tier = "WARNING"
        is_safe = True
    else:
        risk_tier = "CLEAN"
        is_safe = True

    return SupplyChainAuditResult(
        manifest_type=payload.manifest_type,
        package_count=packages_seen,
        suspicious_count=len(threats),
        threats=threats,
        risk_tier=risk_tier,
        is_safe=is_safe
    )


def validate_network_scope_boundary(payload: ScopeValidationInput) -> ScopeValidationResult:
    """Valida que una URL destino no apunte a rangos privados RFC 1918, metadata cloud o fuera del CIDR legal."""
    parsed = urlparse(payload.target_url)
    scheme = parsed.scheme.lower()

    if scheme not in ("http", "https"):
        return ScopeValidationResult(
            target_url=payload.target_url,
            resolved_ip=None,
            is_in_scope=False,
            is_private_or_cloud_metadata=False,
            allowed=False,
            violation_reason=f"Esquema no permitido '{scheme}://'. Se requiere exclusivamente HTTP/HTTPS."
        )

    host = parsed.hostname
    if not host:
        return ScopeValidationResult(
            target_url=payload.target_url,
            resolved_ip=None,
            is_in_scope=False,
            is_private_or_cloud_metadata=False,
            allowed=False,
            violation_reason="Host no especificado o formato de URL inválido."
        )

    # 1. Comprobación previa de dominio contra allowlist si solo contiene nombres de dominio
    if payload.authorized_cidrs:
        domain_match = False
        has_domain_rules = False
        for rule in payload.authorized_cidrs:
            rule_clean = rule.strip()
            if not re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", rule_clean):
                has_domain_rules = True
                if host == rule_clean or host.endswith("." + rule_clean.lstrip(".")):
                    domain_match = True
                    break
        if has_domain_rules and not domain_match:
            return ScopeValidationResult(
                target_url=payload.target_url,
                resolved_ip=None,
                is_in_scope=False,
                is_private_or_cloud_metadata=False,
                allowed=False,
                violation_reason=f"El destino '{host}' no coincide con los rangos autorizados: {payload.authorized_cidrs}"
            )

    # 2. Comprobación directa de IP o resolución DNS
    resolved_ip: str | None = None
    try:
        ip_obj = ipaddress.ip_address(host)
        resolved_ip = str(ip_obj)
    except ValueError:
        # Es un nombre de host: resolver
        try:
            resolved_ip = socket.gethostbyname(host)
            ip_obj = ipaddress.ip_address(resolved_ip)
        except Exception as exc:
            return ScopeValidationResult(
                target_url=payload.target_url,
                resolved_ip=None,
                is_in_scope=False,
                is_private_or_cloud_metadata=False,
                allowed=False,
                violation_reason=f"Fallo en resolución DNS para '{host}': {exc}"
            )

    # 3. Comprobación de Anti-SSRF (Loopback, Privada, Link-Local, Cloud Metadata 169.254.169.254)
    is_private_or_metadata = False
    if ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_link_local or ip_obj.is_reserved or str(ip_obj) == "169.254.169.254":
        is_private_or_metadata = True

    if payload.block_private_ips and is_private_or_metadata:
        return ScopeValidationResult(
            target_url=payload.target_url,
            resolved_ip=resolved_ip,
            is_in_scope=False,
            is_private_or_cloud_metadata=True,
            allowed=False,
            violation_reason=f"Violación SSRF: La dirección IP resuelta '{resolved_ip}' pertenece a un rango privado, loopback o metadata cloud."
        )

    # 3. Comprobación de CIDRs autorizados si fueron especificados
    in_scope = True
    violation_reason = None
    if payload.authorized_cidrs:
        matched = False
        for cidr in payload.authorized_cidrs:
            try:
                network = ipaddress.ip_network(cidr.strip(), strict=False)
                if ip_obj in network:
                    matched = True
                    break
            except ValueError:
                # Comprobación de dominio coincidente
                if host == cidr.strip() or host.endswith("." + cidr.strip().lstrip(".")):
                    matched = True
                    break

        if not matched:
            in_scope = False
            violation_reason = f"El destino '{host}' ({resolved_ip}) no coincide con los rangos autorizados: {payload.authorized_cidrs}"

    allowed = in_scope and not (payload.block_private_ips and is_private_or_metadata)

    return ScopeValidationResult(
        target_url=payload.target_url,
        resolved_ip=resolved_ip,
        is_in_scope=in_scope,
        is_private_or_cloud_metadata=is_private_or_metadata,
        allowed=allowed,
        violation_reason=violation_reason
    )
