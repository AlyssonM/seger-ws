# ⚡ Seger-WS: Sistema de Gestão de Eficiência Energética

Plataforma completa para automação de análise tarifária e gestão energética com **interface de chat interativo com IA**. Inclui web scraper para faturas EDP, análise inteligente de modalidades tarifárias, API REST com documentação Swagger e servidor MCP (Model Context Protocol) com suporte WebSocket para integração em tempo real.

---

## 🎯 Funcionalidades Principais

### 🤖 **Interface de Chat Interativo com IA**
- **Chat inteligente** com Google Gemini para análises conversacionais
- **Integração MCP** para acesso a ferramentas especializadas em tempo real
- **Análise sob demanda** via comandos naturais em português
- **Contexto persistente** durante toda a sessão de análise
- **Resultados visuais** com gráficos e tabelas interativas

### 📊 **Análise Tarifária Inteligente**
- **Detecção automática** de modalidade tarifária atual (Verde/Azul/Convencional)
- **Otimização tarifária** com recomendações de economia
- **Comparação entre modalidades** com cálculos precisos
- **Análise de padrões de consumo** ponta/fora-ponta
- **Relatórios executivos** com ROI e payback

### 🔄 **Web Scraping Automatizado**
- Login automatizado na área de clientes EDP
- Download de faturas entre períodos específicos
- Tolerância a falhas com sistema de retry robusto
- Organização automática por instalação
- Suporte a múltiplas instalações simultâneas

### 🚀 **API REST Completa** 
- **Documentação Swagger/OpenAPI** interativa
- **8+ endpoints especializados** para diferentes análises
- **Dados ordenados cronologicamente** em todos os retornos mensais
- **Dual-mode parsing** (Regex rápido + LLM preciso)
- **Validação de entrada** e tratamento de erros

### 📈 **Processamento de Dados**
- **Extração via regex** para performance máxima
- **Processamento LLM** para casos complexos
- **Cálculos tarifários** conformes à regulamentação
- **Impostos e tributos** (PIS/COFINS/ICMS) incluídos
- **Energia reativa** e ultrapassagem consideradas

---

## 🛠 Tecnologias

- **Backend**: Flask-RESTX + Python 3.9+
- **Frontend**: Next.js 15 + React 19 + TypeScript
- **Chat IA**: Google Gemini + Interface conversacional
- **Web Scraping**: Playwright (Chromium)
- **IA/LLM**: Google Gemini para extração complexa
- **Documentação**: Swagger/OpenAPI 3.0
- **Análise**: Scipy para otimização matemática
- **Dados**: Pandas + NumPy para processamento
- **MCP Server**: Node.js + TypeScript + WebSocket
- **UI Components**: shadcn/ui + TailwindCSS

---

## 🚀 Instalação e Setup

### 1. **Clone e Ambiente**
```bash
git clone https://github.com/AlyssonM/seger-ws.git
cd seger-ws

# Ambiente virtual Python (nome específico: .seger)
python -m venv .seger
source .seger/bin/activate  # Linux/Mac
# ou .\.seger\Scripts\activate  # Windows
```

### 2. **Dependências Python**
```bash
pip install -r requirements.txt
playwright install  # Instala navegadores Chromium
```

### 3. **Frontend React (Recomendado)**
```bash
# Instalar dependências do frontend
npm install
```

### 4. **MCP Server (Para Chat IA)**
```bash
cd mcp-server
npm install
npm run build
cd ..
```

### 5. **Configuração**
Crie arquivo `.env.local` para o frontend:
```env
GEMINI_API_KEY=sua_chave_gemini_aqui
MCP_SERVER_URL=ws://localhost:8080
NEXT_PUBLIC_API_URL=http://localhost:5001
```

E arquivo `.env` para credenciais EDP:
```env
EDP_LOGIN_EMAIL=seu-email@edp.com
EDP_LOGIN_SENHA=sua_senha_segura
```

## 🚀 Inicialização

### **Frontend React (Interface Principal)**
```bash
# Inicia interface web com chat IA
npm run dev

# Interface disponível em http://localhost:3000
# - Dashboard com análises visuais
# - Chat interativo com IA
# - Visualização de dados em tempo real
```

### **API Backend**
```bash
# Ativa ambiente e inicia servidor Flask
source .seger/bin/activate
python app.py

# API rodando em http://localhost:5001
# Swagger UI: http://localhost:5001/swagger/
```

### **MCP Server (Para Chat IA)**
```bash
cd mcp-server
./start-server.sh websocket  # Porta 8080 (WebSocket)
# ou
./start-server.sh            # Modo stdio (Claude Desktop)
```

---

## 🤖 Chat Interativo com IA

### **Interface Conversacional**
O sistema agora inclui uma interface de chat inteligente que permite:

- **Análises em linguagem natural**: "Analise a instalação 0000144112 de maio a dezembro de 2024"
- **Perguntas complexas**: "Qual seria a economia se migrássemos para tarifa azul?"
- **Contextualização automática**: O chat mantém o contexto da conversa
- **Resultados visuais**: Gráficos e tabelas gerados automaticamente

### **Exemplos de Comandos**
```
💬 "Faça uma análise completa da instalação 144112 de janeiro a junho de 2024"
💬 "Compare as modalidades tarifárias para o período analisado"
💬 "Quais são as recomendações de economia?"
💬 "Gere um relatório executivo com os resultados"
```

### **Integração MCP**
O chat utiliza o protocolo MCP para:
- **Acesso direto às ferramentas** de análise em tempo real
- **Comunicação WebSocket** para respostas instantâneas
- **Processamento inteligente** com Google Gemini
- **Persistência de sessão** durante a análise

---

## 📡 API Endpoints

### **Core Endpoints**
| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/swagger/` | GET | 📖 Documentação interativa Swagger |
| `/api/seger/faturas` | POST | 📥 Download de faturas por instalação |
| `/api/seger/faturas-json` | POST | 📊 Dados consolidados de faturas |
| `/api/seger/analisar-fatura` | POST | 🎯 **Análise tarifária completa** |
| `/api/seger/calc-verde` | POST | 🟢 Cálculo modalidade Verde |
| `/api/seger/calc-azul` | POST | 🔵 Cálculo modalidade Azul |
| `/api/seger/otimizacao` | POST | ⚡ Otimização tarifária |
| `/api/seger/tarifas` | GET | 💰 Consulta de tarifas por período |

### **Exemplo de Uso Completo**

#### 1. **Análise Tarifária Automática**
```bash
curl -X POST http://localhost:5001/api/seger/analisar-fatura \
  -H "Content-Type: application/json" \
  -d '{
    "data_inicio": "JAN-2024",
    "data_fim": "DEZ-2024", 
    "codInstalacao": "0000144112",
    "distribuidora": "EDP ES",
    "via_regex": true
  }'
```

**Resposta Estruturada:**
```json
{
  "analise": {
    "modalidade_atual": "verde",
    "parametros_atuais": {"demanda_contratada": 180.0},
    "melhor_opcao": {
      "modalidade": "azul",
      "economia_anual": 11355.39,
      "economia_percentual": 1.7
    },
    "dados_mensais": [
      {"mes_referencia": "01/2024", "valor_fatura": 62048.37},
      {"mes_referencia": "02/2024", "valor_fatura": 61509.06}
    ],
    "recomendacoes": [
      "Migrar para modalidade Azul para economia de R$ 11.355,39 anuais"
    ]
  }
}
```

#### 2. **Download de Faturas**
```bash
curl -X POST http://localhost:5001/api/seger/faturas \
  -H "Content-Type: application/json" \
  -d '{
    "instalacoes": "1234567890,0987654321",
    "mes_inicio": "JAN-2024",
    "mes_fim": "ABR-2024"
  }'
```

---

## 🏗 Arquitetura do Sistema

### **Componentes Principais**
```
seger-ws/
├── app.py                 # 🚀 Servidor Flask principal (porta 5001)
├── src/                   # 🐍 Backend Python
│   ├── app/              # ⚙️ Frontend Next.js
│   │   ├── dashboard/    # 📊 Páginas de análise
│   │   ├── actions.ts    # 🔄 Server Actions
│   │   └── gemini-actions.ts # 🤖 Integração Gemini
│   ├── components/       # 🧩 Componentes React
│   │   └── ui/Chat.tsx   # 💬 Interface de chat
│   ├── contexts/         # 🔄 Context providers
│   ├── routes.py         # 📡 Endpoints da API REST
│   ├── scraper.py        # 🕸️ Web scraping EDP (Playwright)
│   ├── parser.py         # 🧠 Extração LLM (Gemini)
│   ├── parser_regex.py   # ⚡ Extração regex (rápida)
│   └── utils/
│       ├── analise.py    # 🎯 Nova análise tarifária
│       ├── tarifas.py    # 💰 Cálculos tarifários
│       └── optmization.py # 📊 Algoritmos de otimização
├── mcp-server/           # 🔧 Servidor MCP (Node.js + WebSocket)
│   ├── src/
│   │   ├── infrastructure/
│   │   │   └── services/ # 🌐 Serviços API
│   │   └── interface/
│   │       └── controllers/ # 🔧 Controladores MCP
│   └── start-server.sh   # 🚀 Script de inicialização
└── faturas_edp/          # 📁 PDFs organizados por instalação
```

### **Fluxo de Análise Moderna**
1. **Interface** → Chat interativo ou dashboard web
2. **Comunicação** → WebSocket/MCP para tempo real
3. **Download** → Web scraping das faturas PDF
4. **Extração** → Parsing via regex ou LLM
5. **Análise** → Detecção automática de modalidade
6. **Otimização** → Cálculo de economia potencial
7. **Visualização** → Gráficos e tabelas interativas
8. **Chat IA** → Respostas e recomendações conversacionais

---

## 🎛 Features Avançadas

### **🔍 Dual-Mode Parsing**
- **Regex Mode**: Extração ultrarrápida para formatos conhecidos
- **LLM Mode**: IA generativa para casos complexos/novos formatos
- **Auto-fallback**: Muda automaticamente entre modos

### **📊 Análise Tarifária Inteligente**
- **Detecção automática** de modalidade (Verde/Azul/Convencional)
- **Otimização matemática** usando Scipy
- **Consideração completa**: Impostos, energia reativa, ultrapassagem
- **Relatórios executivos** com ROI e payback

### **⚡ Performance Otimizada**
- **Grid reduzido**: 20x20 pontos (vs 50x50 anterior)
- **Logs inteligentes**: DEBUG durante cálculos, INFO para resultados
- **Cache de resultados** para consultas repetidas
- **Processamento paralelo** quando possível

---

## 🔧 MCP Server Integration

O servidor MCP (Model Context Protocol) fornece integração avançada com suporte **WebSocket** e **stdio**:

### **Ferramentas Disponíveis**
- `seger-tools/start_analysis`: Análise energética completa automatizada
- `baixar-faturas`: Download de faturas por instalação e período
- `dados-fatura`: Extração de dados consolidados de faturas

### **Modos de Operação**

#### **WebSocket Mode (Frontend React)**
```bash
cd mcp-server
./start-server.sh websocket     # Porta 8080 (padrão)
./start-server.sh websocket 9090 # Porta customizada
```
**Uso**: Integração com chat do frontend React

#### **Stdio Mode (Claude Desktop)**
```bash
cd mcp-server
./start-server.sh  # ou npm start
```
**Uso**: Integração direta com Claude Desktop

### **Configuração Claude Desktop**
Adicione ao `settings.json`:
```json
{
  "mcpServers": {
    "seger-ws-mcp-server": {
      "command": "node",
      "args": ["build/main.js"],
      "cwd": "/caminho/para/seger-ws/mcp-server"
    }
  }
}
```

### **Exemplo de Uso via MCP**
```bash
# Análise automática com credenciais padrão
curl -X POST ws://localhost:8080 \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "seger-tools/start_analysis",
      "arguments": {
        "installations": ["0000144112"],
        "start_date": "05/2024",
        "end_date": "04/2025"
      }
    }
  }'
```

---

## 📊 Dados de Saída

### **Estrutura de Arquivos**
```
faturas_edp/
├── 0000144112/           # Por número de instalação
│   ├── fatura_MAI-2024.pdf
│   ├── fatura_JUN-2024.pdf
│   └── ...
└── logs/
    └── swagger_api.log   # Logs detalhados da API
```

### **Formato de Resposta API**
Todos os dados mensais são **ordenados cronologicamente**:
```json
{
  "dados_mensais": [
    {"mes_referencia": "05/2024", "valor_fatura": 63972.48},
    {"mes_referencia": "06/2024", "valor_fatura": 49252.65},
    {"mes_referencia": "07/2024", "valor_fatura": 48617.17}
  ]
}
```

---

## 🚨 Troubleshooting

### **Problemas Comuns**

#### 🔐 **Erro de Login EDP**
```bash
# Verifique credenciais no .env
cat .env
# Teste manual no navegador
```

#### 🤖 **Chat não Responde**
```bash
# Verifique MCP server
cd mcp-server && ./start-server.sh websocket

# Verifique variáveis de ambiente
cat .env.local | grep GEMINI_API_KEY
cat .env.local | grep MCP_SERVER_URL
```

#### 🔌 **"Connection refused" no Frontend**
- Verifique se o MCP server está rodando: `./start-server.sh websocket`
- Confirme a porta no `.env.local`: `MCP_SERVER_URL=ws://localhost:8080`
- Teste a conexão: `wscat -c ws://localhost:8080`

#### 📊 **Valores Zerados na Análise**
- ✅ **Solucionado**: Valores mensais agora calculados via funções tarifárias
- ✅ **Ordenação**: Dados cronológicos em todos os endpoints

#### 🕸️ **Falha no Web Scraping**
```bash
# Reinstalar navegadores Playwright
playwright install chromium
```

#### 🧠 **Erro de Parsing LLM**
- Verifique conexão com Google Gemini
- Fallback automático para regex ativo
- Teste a chave API: `curl -H "Authorization: Bearer $GEMINI_API_KEY" ...`

#### 🔧 **"Tool not found" no MCP**
- Verifique os logs do MCP server: `./start-server.sh websocket`
- Confirme que as ferramentas foram registradas: `tools/list`
- Recompile o servidor: `npm run build`

---

## 🎯 Casos de Uso

### **💼 Consultores Energéticos**
- **Chat inteligente** para análises rápidas com clientes
- **Dashboard visual** com gráficos e métricas
- **Relatórios automatizados** via conversação natural
- **Comparações interativas** entre modalidades

### **🏢 Facilities Management**
- **Interface web moderna** para equipes técnicas
- **Análises sob demanda** via comandos naturais
- **Monitoramento visual** em tempo real
- **Integração API** com sistemas ERP/SCADA

### **🔬 Pesquisa Acadêmica**
- **Exploração interativa** de dados energéticos
- **Visualizações personalizadas** via chat
- **Export de dados** para ferramentas acadêmicas
- **API REST** para integração com pipelines de pesquisa

---

## 🚀 Roadmap

### **✅ Implementado Recentemente**
- [x] **Interface Web**: Dashboard React com Next.js 15
- [x] **Chat Interativo**: IA conversacional com Gemini
- [x] **MCP WebSocket**: Integração em tempo real
- [x] **Visualizações**: Gráficos e tabelas interativas
- [x] **Context Management**: Persistência de sessão

### **🕰️ Próximas Features**
- [ ] **API v2**: GraphQL para consultas flexíveis  
- [ ] **ML Predictions**: Previsão de consumo futuro
- [ ] **Multi-distribuidora**: Suporte além da EDP
- [ ] **Export formats**: Excel, PDF, Power BI
- [ ] **Mobile App**: Aplicação React Native
- [ ] **Real-time Alerts**: Notificações de anomalias

---

## 🛠 Contribuição

### **Development Setup**
```bash
git clone https://github.com/AlyssonM/seger-ws.git
cd seger-ws
git checkout -b feature/nova-funcionalidade

# Setup ambiente
python -m venv .seger
source .seger/bin/activate
pip install -r requirements.txt

# Testes
python -m pytest tests/
```

### **Commit Guidelines**
- `feat:` Nova funcionalidade
- `fix:` Correção de bugs  
- `docs:` Documentação
- `perf:` Melhorias de performance
- `test:` Adição de testes

---

## 📄 Licença

**MIT License** © 2025 Seger-WS Project

Desenvolvido com ❤️ para automação de gestão energética no Brasil.
