# Seger MCP Server

MCP (Model Context Protocol) server que fornece ferramentas de análise energética para o WattSight.

## Configuração

### 1. Instalar Dependências
```bash
npm install
```

### 2. Configurar API Base URL
O servidor está configurado para usar:
```
https://5001-idx-pylatex-seger-1742562415094.cluster-kc2r6y3mtba5mswcmol45orivs.cloudworkstations.dev
```

Se sua URL mudou, edite `src/infrastructure/services/SegerApiService.ts`:
```typescript
private readonly API_BASE="https://sua-nova-url-aqui/api/seger";
```

### 3. Compilar
```bash
npm run build
```

## Uso

### Opção 1: Script Conveniente (Recomendado)
```bash
# WebSocket na porta 8080 (para chat do frontend)
./start-server.sh websocket

# WebSocket em porta customizada
./start-server.sh websocket 9090

# Modo stdio (para Claude Desktop, etc.)
./start-server.sh
```

### Opção 2: NPM Scripts
```bash
# WebSocket na porta 8080
npm run start:ws

# Modo stdio
npm start
```

### Opção 3: Node Direto
```bash
# WebSocket
node build/main.js websocket [porta]

# Stdio
node build/main.js
```

## Modos de Operação

### WebSocket Mode
- **Porta padrão**: 8080
- **Uso**: Frontend React, aplicações web
- **URL de conexão**: `ws://localhost:8080`

### Stdio Mode
- **Uso**: Claude Desktop, ferramentas de linha de comando
- **Configuração no Claude Desktop**: Adicionar no config.json

## Ferramentas Disponíveis

### `seger-tools/start_analysis`
Inicia análise energética completa para instalações.

**Parâmetros:**
```json
{
  "installations": ["0000144112"],
  "start_date": "05/2024",
  "end_date": "04/2025",
  "user": "admin",
  "password": "senha123"
}
```

## Configuração no Frontend

No arquivo `.env.local`:
```bash
MCP_SERVER_URL=ws://localhost:8080
GEMINI_API_KEY=sua_chave_gemini_aqui
```

## Logs e Debug

O servidor produz logs no stderr para não interferir com a comunicação MCP:

```bash
# Logs típicos em WebSocket mode
Seger MCP Server starting WebSocket server on port 8080
New WebSocket connection established

# Logs típicos em stdio mode  
Seger MCP Server running on stdio
```

## Estrutura do Projeto

```
src/
├── infrastructure/
│   └── services/
│       └── SegerApiService.ts    # Cliente da API SEGER
├── interface/
│   └── controllers/
│       └── SegerToolsController.ts # Controlador das ferramentas MCP
└── main.ts                       # Servidor principal
```

## Troubleshooting

### "Connection refused" no frontend
- Verifique se o MCP server está rodando: `./start-server.sh websocket`
- Confirme a porta no `.env.local`: `MCP_SERVER_URL=ws://localhost:8080`

### "HTTP 502/503" nas ferramentas
- Verifique se a API SEGER está rodando na URL configurada
- Teste a API diretamente: `curl https://sua-url/api/seger/health`

### "Tool not found"
- Verifique os logs do MCP server
- Confirme que as ferramentas foram registradas corretamente

## Desenvolvimento

### Modo Watch (Recompila automaticamente)
```bash
# Terminal 1: Watch TypeScript
npx tsc --watch

# Terminal 2: Reiniciar servidor quando mudanças
./start-server.sh websocket
```

### Testes
```bash
# Testar conectividade WebSocket
wscat -c ws://localhost:8080

# Testar ferramenta via JSON-RPC
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | wscat -c ws://localhost:8080
```