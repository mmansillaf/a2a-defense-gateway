import re
from typing import ClassVar


class GrammarCompilerService:
    """
    Servicio de compilación Grammar-as-a-Service (GaaS).
    Genera gramáticas formales GBNF a partir de especificaciones de campos
    para garantizar salidas JSON libres de errores sintácticos y seguras contra escapes.
    """

    SUPPORTED_TYPES: ClassVar[set[str]] = {"string", "integer", "boolean", "float", "safe_id"}

    def compile_schema_to_gbnf(self, schema_spec: dict[str, str], root_name: str = "root") -> str:
        """
        Compila un diccionario de {campo: tipo} en una gramática GBNF estricta.
        Tipos soportados: string, integer, boolean, float, safe_id.
        """
        lines: list[str] = [
            f'{root_name} ::= "{{" ws',
        ]

        field_rules: list[str] = []
        items = list(schema_spec.items())

        for idx, (field_name, field_type) in enumerate(items):
            clean_field = re.sub(r"[^a-zA-Z0-9_]", "", field_name)
            rule_ref = self._map_type_to_rule(field_type)
            comma = ' "," ws' if idx < len(items) - 1 else ""
            field_rules.append(f'  "\\"{clean_field}\\":" ws {rule_ref}{comma}')

        lines.extend(field_rules)
        lines.extend([
            'ws "}"',
            "",
            '# Reglas léxicas terminales de contención',
            'safe-string ::= "\\"" [^"\\\\<>\'`\\[\\]\\x00-\\x1f]{1,300} "\\""',
            'safe-id ::= "\\"" [a-zA-Z0-9_-]{4,64} "\\""',
            'integer ::= ("0" | [1-9] [0-9]*)',
            'float ::= ("0" | [1-9] [0-9]*) "." [0-9]+',
            'boolean ::= ("true" | "false")',
            'ws ::= [ \\t\\n]*',
        ])

        return "\n".join(lines)

    def _map_type_to_rule(self, ftype: str) -> str:
        ftype_lower = ftype.lower().strip()
        if ftype_lower == "integer" or ftype_lower == "int":
            return "integer"
        if ftype_lower == "float":
            return "float"
        if ftype_lower == "boolean" or ftype_lower == "bool":
            return "boolean"
        if ftype_lower == "safe_id" or ftype_lower == "id":
            return "safe-id"
        return "safe-string"
