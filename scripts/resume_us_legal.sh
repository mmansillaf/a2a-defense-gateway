#!/usr/bin/env bash
# resume_us_legal.sh - Script de Reanudación Automática y Sincronización a Google Drive
# para el Corpus Continuo de Contratos y Jurisprudencia de EE. UU. (A2A LegalTech)
set -euo pipefail

BASE_DIR="/home/usuario/Descargas/pycode/SkillA2A_Moltbook/moltbook_defense_system"
cd "$BASE_DIR"

echo "=== INICIANDO SERVICIOS DE COSECHA CONTINUA US LEGAL Y SINCRONIZACIÓN GDRIVE ==="

# 1. Reanudar Cosechador Continuo de Contratos SEC y Jurisprudencia
if ! pgrep -f "us_legal_continuous_harvester.py" > /dev/null; then
    echo "Iniciando us_legal_continuous_harvester.py en background..."
    nohup "$BASE_DIR/.venv/bin/python" -u "$BASE_DIR/scripts/us_legal_continuous_harvester.py" >> "$BASE_DIR/data/us_legal/us_legal_harvester.log" 2>&1 < /dev/null &
    echo " -> PID Cosechador US Legal: $!"
else
    echo " -> us_legal_continuous_harvester ya se encuentra en ejecución."
fi

# 2. Reanudar Sincronización Continua a Google Drive con Rclone
if ! pgrep -f "rclone copy.*gdrive:09_us_legal/corpus/" > /dev/null; then
    echo "Iniciando rclone hacia gdrive:09_us_legal/corpus/..."
    nohup /home/usuario/.local/bin/rclone copy "$BASE_DIR/data/us_legal/" gdrive:09_us_legal/corpus/ \
        --transfers 4 \
        --fast-list \
        --exclude "*.lock" \
        --exclude "*.tmp" \
        --exclude "*.log" >> "$BASE_DIR/data/us_legal/rclone_gdrive.log" 2>&1 < /dev/null &
    echo " -> PID Rclone GDrive: $!"
else
    echo " -> Rclone US Legal ya se encuentra sincronizando."
fi

echo "=== ESTADO DE DAEMONS ACTIVOS ==="
pgrep -a -f 'us_legal|rclone' || true
