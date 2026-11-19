import ast
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict


class SkillCertificationReport(BaseModel):
    """Dictamen pericial de seguridad sobre una herramienta o skill A2A."""
    model_config = ConfigDict(extra="forbid")

    skill_name: str
    verdict: Literal["CERTIFIED_SECURE", "SUSPICIOUS_REVIEW", "MALICIOUS_REJECTED"]
    vulnerabilities_found: list[str]
    is_safe_to_execute: bool
    risk_score: float  # 0.0 (seguro) a 1.0 (malware)


class SkillSecurityCertifier:
    """
    Antivirus y auditor SAST para habilidades (Skills) en Moltbook.
    Detecta troyanos tipo DY-Skill, puertas traseras y exfiltración de credenciales.
    """

    FORBIDDEN_CALLS: ClassVar[set[str]] = {"eval", "exec", "__import__", "compile"}
    FORBIDDEN_MODULES: ClassVar[set[str]] = {"subprocess", "pty", "commands", "ctypes", "winreg"}
    FORBIDDEN_OS_ATTRS: ClassVar[set[str]] = {"system", "popen", "spawn", "execv", "execl"}
    SENSITIVE_PATTERNS: ClassVar[set[str]] = {
        "/etc/passwd",
        ".ssh",
        "id_rsa",
        "session_nonce",
        "private_key",
        # Firmas de campaña ClawHavoc / Stealer AMOS / Robo de Wallets en Moltbook
        ".config/solana",
        "solana/id.json",
        "keychain",
        "keypair.fromsecretkey",
        "cookies.sqlite",
        "wallet.dat",
        "phantom",
        "metamask",
        "amos",
        "pump.fun/create",
    }

    def certify_python_code(self, code_str: str, skill_name: str = "unnamed_skill") -> SkillCertificationReport:
        """Audita el código fuente de un skill y emite una atestación de seguridad."""
        vulnerabilities: list[str] = []

        try:
            tree = ast.parse(code_str, filename=f"{skill_name}.py")
        except SyntaxError as exc:
            return SkillCertificationReport(
                skill_name=skill_name,
                verdict="MALICIOUS_REJECTED",
                vulnerabilities_found=[f"Error de sintaxis: código malformado ({exc})"],
                is_safe_to_execute=False,
                risk_score=1.0,
            )

        for node in ast.walk(tree):
            # 1. Detección de llamadas a eval/exec o llamadas a shell
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in self.FORBIDDEN_CALLS:
                    vulnerabilities.append(f"Invocación de función peligrosa: {node.func.id}()")
                elif isinstance(node.func, ast.Attribute) and node.func.attr in self.FORBIDDEN_OS_ATTRS:
                    vulnerabilities.append(f"Llamada a shell interactiva o ejecución: .{node.func.attr}()")

            # 2. Detección de importación de módulos prohibidos
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in self.FORBIDDEN_MODULES:
                        vulnerabilities.append(f"Importación de módulo no autorizado: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module in self.FORBIDDEN_MODULES:
                    vulnerabilities.append(f"Importación desde módulo no autorizado: {node.module}")

            # 3. Detección de rutas o secretos en constantes
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                val_lower = node.value.lower()
                for pat in self.SENSITIVE_PATTERNS:
                    if pat in val_lower:
                        vulnerabilities.append(f"Acceso o referencia a ruta/secreto sensible: '{node.value}'")

        if not vulnerabilities:
            return SkillCertificationReport(
                skill_name=skill_name,
                verdict="CERTIFIED_SECURE",
                vulnerabilities_found=[],
                is_safe_to_execute=True,
                risk_score=0.0,
            )

        # Si solo contiene patrones sospechosos pero sin llamadas directas a shell
        has_critical = any("shell" in v or "eval" in v or "exec" in v or "subprocess" in v for v in vulnerabilities)
        verdict = "MALICIOUS_REJECTED" if has_critical else "SUSPICIOUS_REVIEW"
        risk = 1.0 if has_critical else 0.50

        return SkillCertificationReport(
            skill_name=skill_name,
            verdict=verdict,
            vulnerabilities_found=vulnerabilities,
            is_safe_to_execute=False,
            risk_score=risk,
        )
