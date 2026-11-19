#!/usr/bin/env bash
# Moltbook Egress and Agent Defense Guard Hook for Google Antigravity
# Intercepts 'run_command' calls to enforce Zero-Trust and prevent token exfiltration or uncontained scraping.
set -euo pipefail

input=$(cat)

# 1. Bloquear exfiltración de credenciales / nonces de sesión hacia el exterior
if [[ "$input" =~ (ACTIVE_SESSION_NONCE|MOLTBOOK_API_KEY|SESSION_NONCE) ]] && [[ "$input" =~ (curl|wget|nc|ncat|socat|ssh) ]]; then
  cat << 'EOF'
{
  "decision": "deny",
  "reason": "[MOLTBOOK-GUARD] Intento de exfiltración de nonces de sesión o API keys detectado y bloqueado determinísticamente."
}
EOF
  exit 0
fi

# 2. Bloquear peticiones de red directas a Moltbook sin pasar por el proxy de lista blanca
if [[ "$input" =~ (curl|wget|httpie)[[:space:]]+.*moltbook\.com ]] && ! [[ "$input" =~ (--proxy|http_proxy|localhost:3128|127\.0\.0\.1:3128) ]]; then
  cat << 'EOF'
{
  "decision": "deny",
  "reason": "[MOLTBOOK-GUARD] Petición directa a Moltbook sin proxy Squid de lista blanca bloqueada. Debe utilizar el proxy local :3128."
}
EOF
  exit 0
fi

# 3. Bloquear ejecución de comandos con payloads de inyección en argumentos de shell
if [[ "$input" =~ (ignore[[:space:]]+previous|system[[:space:]]+override|new[[:space:]]+instructions|act[[:space:]]+as) ]] && [[ "$input" =~ (bash|sh|python|eval) ]]; then
  cat << 'EOF'
{
  "decision": "deny",
  "reason": "[MOLTBOOK-GUARD] Inyección de instrucciones o manipulación de prompt detectada en comando de shell. Bloqueado por seguridad."
}
EOF
  exit 0
fi

# Permitir comandos seguros
cat << 'EOF'
{
  "decision": "allow"
}
EOF
exit 0
