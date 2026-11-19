.PHONY: help setup test lint build up-secure down demo-e2e demo-monetization clean

VENV := .venv
BIN := $(VENV)/bin

help:
	@echo "Comandos disponibles:"
	@echo "  make setup              - Crea entorno virtual con uv e instala dependencias"
	@echo "  make test               - Ejecuta la suite adversarial Red Team completa (8 tests)"
	@echo "  make lint               - Ejecuta ruff check sobre todo el código"
	@echo "  make demo-e2e           - Simulación de contención y auditoría de inyecciones"
	@echo "  make demo-monetization  - Simulación de micropagos, oráculo y Alpha Feed A2A"
	@echo "  make build              - Construye la imagen Docker endurecida (no-root)"
	@echo "  make clean              - Destruye entorno virtual y artefactos temporales"

setup:
	uv venv $(VENV)
	uv pip install fastapi uvicorn httpx pydantic pytest ruff bandit

test:
	PYTHONPATH=agents $(BIN)/pytest tests/ -v

lint:
	ruff check agents/ tests/ scripts/

demo-e2e:
	@mkdir -p output
	PYTHONPATH=agents $(BIN)/python scripts/run_e2e_demo.py

demo-monetization:
	@mkdir -p output
	PYTHONPATH=agents $(BIN)/python scripts/run_monetization_demo.py

build:
	docker build -f agents/Dockerfile.hardened -t moltbook-agent-hardened:latest ./agents

clean:
	rm -rf $(VENV) __pycache__ .pytest_cache output/*.html output/*.md
