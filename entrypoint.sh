#!/bin/bash
set -e

echo "Starting Open WebUI ExApp..."
echo "APP_ID: ${APP_ID}"
echo "APP_HOST: ${APP_HOST}"
echo "APP_PORT: ${APP_PORT}"
echo "Ollama URL: ${OLLAMA_BASE_URL:-auto-detect}"
echo "OpenAI URL: ${OPENAI_API_BASE_URL:-not configured}"

# Start FRP client if HaRP is configured
if [ -n "$HARP_FRP_SERVER" ]; then
    echo "Starting FRP client for HaRP..."
    cat > /tmp/frpc.toml << EOF
serverAddr = "${HARP_FRP_SERVER}"
serverPort = ${HARP_FRP_PORT:-7000}

[[proxies]]
name = "${APP_ID}"
type = "tcp"
localIP = "127.0.0.1"
localPort = ${APP_PORT}
remotePort = ${HARP_REMOTE_PORT:-0}
EOF
    /usr/local/bin/frpc -c /tmp/frpc.toml &
fi

# Start the AppAPI wrapper
exec python3 /app/ex_app/lib/main.py
