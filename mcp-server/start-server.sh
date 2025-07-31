#!/bin/bash

# Script para iniciar o MCP Server
# Uso: ./start-server.sh [modo] [porta]
# Exemplos:
#   ./start-server.sh                  # Inicia em modo stdio
#   ./start-server.sh websocket        # Inicia WebSocket na porta 8080
#   ./start-server.sh websocket 9090   # Inicia WebSocket na porta 9090

echo "🔧 Construindo MCP Server..."
npm run build

if [ $? -ne 0 ]; then
    echo "❌ Erro na compilação do MCP Server"
    exit 1
fi

echo "🚀 Iniciando Seger MCP Server..."

# Determinar o modo e porta
MODE=${1:-stdio}
PORT=${2:-8080}

if [ "$MODE" = "websocket" ] || [ "$MODE" = "ws" ]; then
    echo "📡 Modo WebSocket na porta $PORT"
    echo "🔗 Frontend pode conectar em: ws://localhost:$PORT"
    node build/main.js websocket $PORT
else
    echo "📝 Modo stdio (padrão para Claude Desktop, etc.)"
    node build/main.js
fi