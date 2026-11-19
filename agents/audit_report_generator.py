import html
from datetime import UTC, datetime
from pathlib import Path

from schemas import EvaluatedClaim


class ExecutiveAuditReportGenerator:
    """
    Genera informes ejecutivos trazables en Markdown y HTML autónomo XSS-Safe
    a partir de los resultados ponderados del Agente Privilegiado.
    """

    def __init__(self, mission_topic: str, session_nonce: str):
        self.mission_topic = mission_topic
        self.session_nonce = session_nonce
        self.generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    def generate_markdown(self, claims: list[EvaluatedClaim], telemetry: dict) -> str:
        verified = [c for c in claims if c.verdict == "VERIFIED_HIGH"]
        provisional = [c for c in claims if c.verdict == "PROVISIONAL_MEDIUM"]
        rejected = [c for c in claims if c.verdict in ("REJECTED_SYBIL", "REJECTED_ADVERSARIAL")]

        lines = [
            f"# Informe de Inteligencia Verificada: {self.mission_topic}",
            f"**Fecha de Auditoría:** `{self.generated_at}` | **ID Sesión:** `{self.session_nonce[:12]}...`",
            "",
            "## 1. Telemetría de Seguridad y Contención",
            f"- **Posts Analizados:** {telemetry.get('posts_scanned', 0)}",
            f"- **Clones Sybil Bloqueados Tempranamente:** {telemetry.get('posts_deduplicated_sybil_early', 0)}",
            f"- **Afirmaciones Verificadas (Alta Confianza):** {len(verified)}",
            f"- **Afirmaciones Provisionales (Confianza Media):** {len(provisional)}",
            f"- **Cargas Hostiles / Falsas Rechazadas en Control:** {len(rejected)}",
            "",
            "## 2. Hallazgos Verificados (Anclados a Evidencia Primaria)",
        ]

        if not verified:
            lines.append("_Ninguna afirmación alcanzó el umbral de verificación empírica de alta confianza._")
        else:
            for c in sorted(verified, key=lambda x: x.final_trust_score, reverse=True):
                lines.append(
                    f"- **[{c.claim_id}] (Score S_c: {c.final_trust_score:.2f}):** {c.statement}  \n"
                    f"  *Auditoría:* {c.audit_rationale} *(E={c.score_E:.2f}, I={c.score_I:.2f}, C={c.score_C:.2f})*"
                )

        lines.extend(["", "## 3. Registro de Amenazas y Desinformación Neutralizada"])
        for c in rejected:
            lines.append(f"- **[{c.claim_id}] [{c.verdict}]:** {c.audit_rationale}")

        return "\n".join(lines)

    def generate_html_dashboard(self, claims: list[EvaluatedClaim], telemetry: dict, output_path: Path) -> Path:
        """Renderiza un dashboard HTML autocontenido con escape estricto contra XSS."""
        esc = html.escape

        verified_count = sum(1 for c in claims if c.verdict == "VERIFIED_HIGH")
        rejected_count = sum(1 for c in claims if c.verdict in ("REJECTED_SYBIL", "REJECTED_ADVERSARIAL"))

        rows_html = []
        for c in sorted(claims, key=lambda x: x.final_trust_score, reverse=True):
            badge_class = {
                "VERIFIED_HIGH": "badge-green",
                "PROVISIONAL_MEDIUM": "badge-amber",
                "REJECTED_SYBIL": "badge-red",
                "REJECTED_ADVERSARIAL": "badge-red",
            }.get(c.verdict, "badge-gray")

            rows_html.append(f"""
            <tr>
                <td><code>{esc(c.claim_id)}</code></td>
                <td><span class="badge {badge_class}">{esc(c.verdict)}</span></td>
                <td><strong>{c.final_trust_score:.2f}</strong></td>
                <td>{esc(c.statement)}</td>
                <td>{esc(c.audit_rationale)}</td>
                <td>E:{c.score_E:.2f} | I:{c.score_I:.2f} | C:{c.score_C:.2f} | A:-{c.penalty_A:.2f}</td>
            </tr>
            """)

        html_doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline';">
<title>Auditoría Zero-Trust - {esc(self.mission_topic)}</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; margin: 2rem; }}
  .header {{ border-bottom: 1px solid #334155; padding-bottom: 1rem; margin-bottom: 2rem; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem; }}
  .kpi-card {{ background: #1e293b; padding: 1.2rem; border-radius: 8px; border: 1px solid #334155; }}
  .kpi-val {{ font-size: 1.8rem; font-weight: 700; color: #38bdf8; }}
  table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; }}
  th, td {{ padding: 0.9rem; text-align: left; border-bottom: 1px solid #334155; font-size: 0.9rem; }}
  th {{ background: #020617; color: #94a3b8; text-transform: uppercase; font-size: 0.75rem; }}
  .badge {{ padding: 0.25rem 0.6rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }}
  .badge-green {{ background: #065f46; color: #6ee7b7; }}
  .badge-amber {{ background: #78350f; color: #fcd34d; }}
  .badge-red {{ background: #7f1d1d; color: #fca5a5; }}
</style>
</head>
<body>
  <div class="header">
    <h1>Dashboard de Auditoría Epistémica y Seguridad Multi-Agente</h1>
    <p><strong>Tema Investigado:</strong> {esc(self.mission_topic)} | <strong>Fecha:</strong> {esc(self.generated_at)}</p>
  </div>

  <div class="kpi-grid">
    <div class="kpi-card"><div>Posts Escaneados</div><div class="kpi-val">{int(telemetry.get('posts_scanned', 0))}</div></div>
    <div class="kpi-card"><div>Clones Sybil Podados</div><div class="kpi-val">{int(telemetry.get('posts_deduplicated_sybil_early', 0))}</div></div>
    <div class="kpi-card"><div>Hallazgos Verificados</div><div class="kpi-val" style="color:#34d399;">{verified_count}</div></div>
    <div class="kpi-card"><div>Ataques / Falsedades Bloqueadas</div><div class="kpi-val" style="color:#f87171;">{rejected_count}</div></div>
  </div>

  <table>
    <thead>
      <tr>
        <th>ID</th>
        <th>Veredicto</th>
        <th>Score S_c</th>
        <th>Afirmación Extraída</th>
        <th>Trazabilidad de Auditoría</th>
        <th>Desglose Ponderado</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>
</body>
</html>"""

        output_path.write_text(html_doc, encoding="utf-8")
        return output_path
