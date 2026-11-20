#!/usr/bin/env bash
# run_gateway_daemon.sh - Supervisor y persistencia de FastAPI A2A Gateway
set -euo pipefail

BASE_DIR="/home/usuario/Descargas/pycode/SkillA2A_Moltbook/moltbook_defense_system"
cd "$BASE_DIR"
export PYTHONPATH="agents"

if ! pgrep -f "agents.api_gateway:app" > /dev/null; then
    echo "Iniciando FastAPI A2A Gateway en puerto 8000..."
    nohup "$BASE_DIR/.venv/bin/uvicorn" agents.api_gateway:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers 2 >> "$BASE_DIR/data/gateway.log" 2>&1 < /dev/null &
    echo " -> PID A2A Gateway: $!"
else
    echo " -> A2A Gateway ya está en ejecución."
fi

pgrep -a -f "agents.api_gateway:app" || true
