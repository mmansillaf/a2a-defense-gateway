# syntax=docker/dockerfile:1.4
FROM python:3.11.11-slim-bookworm

# Evitar generación de .pyc y habilitar unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/agents

WORKDIR /app

# Crear usuario y grupo sin privilegios
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Instalar dependencias esenciales de Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY agents /app/agents

# Permisos para el usuario no privilegiado y directorio de datos
RUN mkdir -p /app/data && chown -R appuser:appgroup /app

USER appuser

# Exponer comando stdio para introspección MCP (compatible con Glama y Claude Desktop)
ENTRYPOINT ["python", "/app/agents/mcp_server.py"]
