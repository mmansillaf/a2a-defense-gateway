"""
Módulo Forense de Macros Excel (VBA) y Desofuscación Estática.
Audita código VBA contra WinAPI/DLLs sospechosos, llamadas a Shell, credenciales
embebidas y normaliza identificadores ofuscados de confusión visual (O/0/l/1).
"""

from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, Field

RE_CONFUSION_IDENTIFIER = re.compile(r"\b([O0l1]{6,})\b")
RE_CONCAT = re.compile(r'"([^"\\]*)"\s*&\s*"([^"\\]*)"')
RE_DLL = re.compile(
    r"(?:Declare\s+(?:PtrSafe\s+)?(?:Function|Sub)\s+(\w+)\s+Lib\s+[\"']([^\"']+)[\"'])",
    re.IGNORECASE,
)
RE_URL = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
RE_SHELL = re.compile(
    r"\b(Shell|CreateObject|WScript\.Shell|VirtualAlloc|lstrcpy|lstrlen|FreeMemory)\b",
    re.IGNORECASE,
)
RE_CREDS = re.compile(
    r"(?:password|contrasenia|clave|client_?id|client_?secret|token|bearer)\s*[:=]\s*[\"']?([^\"'\s,]+)",
    re.IGNORECASE,
)


class MacroForensicsInput(BaseModel):
    vba_code: str = Field(..., description="Código fuente VBA para auditar e inspeccionar forensemente")
    auto_deobfuscate: bool = Field(True, description="Normalizar identificadores confusos (ej. O0l1) a símbolos legibles")


class MacroForensicsOutput(BaseModel):
    is_suspicious: bool
    risk_level: str
    confusion_identifiers_found: int
    detected_dll_declarations: list[str]
    detected_shell_invocations: list[str]
    detected_credential_patterns: list[str]
    detected_network_urls: list[str]
    normalized_preview: str
    doc_id: str


def simplify_string_concatenations(code: str) -> str:
    """Simplifica cadenas concatenadas adyacentes ("a" & "b" -> "ab")."""
    prev = None
    curr = code
    while prev != curr:
        prev = curr
        curr = RE_CONCAT.sub(r'"\1\2"', curr)
    return curr


def deobfuscate_confusion_identifiers(code: str) -> tuple[str, int]:
    """Reemplaza identificadores confusos tipo O/0/l/1 por símbolos ordenados (sym_0001)."""
    matches = RE_CONFUSION_IDENTIFIER.findall(code)
    unique_ids = list(dict.fromkeys(matches))
    mapping = {ident: f"sym_{idx:04d}" for idx, ident in enumerate(unique_ids, 1)}

    res = code
    for old_sym, new_sym in mapping.items():
        pattern = rf"\b{re.escape(old_sym)}\b"
        res = re.sub(pattern, new_sym, res)

    res = simplify_string_concatenations(res)
    return res, len(unique_ids)


def audit_vba_macro_code(payload: MacroForensicsInput) -> MacroForensicsOutput:
    """Ejecuta la auditoría estática determinista de código VBA."""
    code = payload.vba_code

    confusion_count = 0
    clean_code = code
    if payload.auto_deobfuscate:
        clean_code, confusion_count = deobfuscate_confusion_identifiers(code)

    dlls = [f"{m[0]} Lib '{m[1]}'" for m in RE_DLL.findall(clean_code)]
    shells = list(dict.fromkeys(RE_SHELL.findall(clean_code)))
    creds = list(dict.fromkeys(RE_CREDS.findall(clean_code)))
    urls = list(dict.fromkeys(RE_URL.findall(clean_code)))

    # Evaluación de riesgo
    is_suspicious = False
    risk_level = "SAFE"

    if shells or any("kernel32" in d.lower() or "ntdll" in d.lower() for d in dlls):
        risk_level = "CRITICAL"
        is_suspicious = True
    elif creds or dlls or confusion_count > 5:
        risk_level = "HIGH"
        is_suspicious = True
    elif urls or confusion_count > 0:
        risk_level = "MEDIUM"
        is_suspicious = True
    elif len(code.strip()) > 0:
        risk_level = "LOW"

    # Generar doc_id reproducible
    h = hashlib.sha256(code.encode("utf-8")).hexdigest()[:8]
    doc_id = f"MACRO-AUDIT-{risk_level}-{h}"

    lines = clean_code.splitlines()
    preview = "\n".join(lines[:10])
    if len(lines) > 10:
        preview += f"\n... [{len(lines) - 10} líneas truncadas]"

    return MacroForensicsOutput(
        is_suspicious=is_suspicious,
        risk_level=risk_level,
        confusion_identifiers_found=confusion_count,
        detected_dll_declarations=dlls,
        detected_shell_invocations=shells,
        detected_credential_patterns=creds,
        detected_network_urls=urls,
        normalized_preview=preview,
        doc_id=doc_id,
    )
