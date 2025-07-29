# ⚡ Seger-WS: Sistema de Gestão de Eficiência Energética

Plataforma completa para automação de análise tarifária e gestão energética, com web scraper para faturas EDP, análise inteligente de modalidades tarifárias e API REST com documentação Swagger. Inclui servidor MCP (Model Context Protocol) para extensibilidade e integração com sistemas externos.

---

## 🎯 Funcionalidades Principais

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
- **Web Scraping**: Playwright (Chromium)
- **IA/LLM**: Google Gemini para extração complexa
- **Documentação**: Swagger/OpenAPI 3.0
- **Análise**: Scipy para otimização matemática
- **Dados**: Pandas + NumPy para processamento
- **MCP Server**: Node.js + TypeScript

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

### 3. **MCP Server (Opcional)**
```bash
cd mcp-server
npm install
npm run build
cd ..
```

### 4. **Configuração**
Crie arquivo `.env` com credenciais EDP:
```env
EDP_LOGIN_EMAIL=seu-email@edp.com
EDP_LOGIN_SENHA=sua_senha_segura
```

## 🚀 Inicialização

### **API Principal**
```bash
# Ativa ambiente e inicia servidor Flask
source .seger/bin/activate
python app.py

# Servidor rodando em http://localhost:5001
# Swagger UI: http://localhost:5001/swagger/
```

### **MCP Server (Opcional)**
```bash
cd mcp-server
npm run start  # Porta 3000
```

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
├── src/
│   ├── routes.py         # 📡 Endpoints da API REST
│   ├── scraper.py        # 🕸️ Web scraping EDP (Playwright)
│   ├── parser.py         # 🧠 Extração LLM (Gemini)
│   ├── parser_regex.py   # ⚡ Extração regex (rápida)
│   └── utils/
│       ├── analise.py    # 🎯 Nova análise tarifária
│       ├── tarifas.py    # 💰 Cálculos tarifários
│       └── optmization.py # 📊 Algoritmos de otimização
├── mcp-server/           # 🔧 Servidor MCP (Node.js)
└── faturas_edp/          # 📁 PDFs organizados por instalação
```

### **Fluxo de Análise**
1. **Download** → Web scraping das faturas PDF
2. **Extração** → Parsing via regex ou LLM
3. **Análise** → Detecção automática de modalidade
4. **Otimização** → Cálculo de economia potencial
5. **Relatório** → Recomendações estruturadas

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

O servidor MCP (Model Context Protocol) estende as funcionalidades:

### **Inicialização**
```bash
cd mcp-server
npm run build && npm run start
```

### **Configuração Claude Desktop**
Adicione ao `settings.json`:
```json
{
  "mcpServers": {
    "seger-ws-mcp-server": {
      "command": "npm",
      "args": ["run", "start"],
      "cwd": "/home/user/pylatex-seger/seger-ws/mcp-server"
    }
  }
}
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

---

## 🎯 Casos de Uso

### **💼 Consultores Energéticos**
- Análise automatizada de múltiplas instalações
- Relatórios executivos para clientes
- Comparação de modalidades tarifárias

### **🏢 Facilities Management**
- Monitoramento contínuo de eficiência
- Identificação de oportunidades de economia
- Integração com sistemas ERP/SCADA

### **🔬 Pesquisa Acadêmica**
- Base de dados de consumo energético
- Algoritmos de otimização tarifária
- Análise de padrões de consumo

---

## 🚀 Roadmap

- [ ] **Dashboard Web**: Interface visual para análises
- [ ] **API v2**: GraphQL para consultas flexíveis  
- [ ] **ML Predictions**: Previsão de consumo futuro
- [ ] **Multi-distribuidora**: Suporte além da EDP
- [ ] **Export formats**: Excel, PDF, Power BI

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
