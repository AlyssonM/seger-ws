# Google Drive Fallback Feature

## Resumo

Esta feature implementa um sistema de fallback que permite buscar PDFs de faturas no Google Drive quando não encontrados localmente no servidor. O sistema mantém compatibilidade total com o código existente e adiciona transparentemente a capacidade de acessar arquivos remotos.

## Funcionalidades Implementadas

### 🔍 Sistema de Busca Inteligente
- **Busca Local Primeiro**: Sistema prioriza arquivos locais (`faturas_edp/`) 
- **Fallback Automático**: Quando não encontra localmente, busca no Google Drive
- **Cache Opcional**: Arquivos do Drive podem ser baixados e salvos localmente
- **Sem Duplicatas**: Evita baixar arquivos que já existem localmente

### 📊 APIs Atualizadas
- **`/faturas-json`**: Inclui informações sobre fonte dos arquivos
- **`/analisar-fatura`**: Análise completa com fallback automático
- Demais rotas mantêm compatibilidade com busca local tradicional

### 📈 Informações de Monitoramento
Todas as respostas agora incluem:
```json
{
    "fontes_utilizadas": {
        "local": 2,
        "google_drive": 1
    },
    "arquivos_processados": 3,
    "arquivos_com_erro": 0
}
```

## Instalação Rápida

### 1. Instalar Dependências
```bash
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### 2. Configurar Variáveis de Ambiente
```bash
cp .env.example .env
# Editar .env com suas configurações
```

### 3. Configurar Google Drive (Opcional)
- Ver arquivo `GOOGLE_DRIVE_SETUP.md` para configuração completa
- Se não configurado, sistema funciona apenas com busca local

## Uso da API

### Endpoint Atualizado: `/faturas-json`

**Request:**
```bash
curl -X POST "http://localhost:5001/api/seger/faturas-json" \
-H "Content-Type: application/json" \
-d '{
    "codInstalacao": "0000144112",
    "data_inicio": "JAN-2025", 
    "data_fim": "MAR-2025"
}'
```

**Response com Fallback:**
```json
{
    "message": "Dados consolidados extraídos com sucesso",
    "total_faturas": 3,
    "arquivos_processados": 3,
    "arquivos_com_erro": 0,
    "fontes_utilizadas": {
        "local": 2,
        "google_drive": 1
    },
    "dados": [
        {
            "arquivo": "fatura_0000144112_JAN-2025.pdf",
            "referencia": "JAN-2025",
            "fonte": "local",
            "dados": { /* dados extraídos */ }
        },
        {
            "arquivo": "fatura_0000144112_FEV-2025.pdf", 
            "referencia": "FEV-2025",
            "fonte": "google_drive",
            "dados": { /* dados extraídos */ }
        }
    ]
}
```

### Endpoint Atualizado: `/analisar-fatura`

Agora inclui `info_processamento` na resposta:

```json
{
    "message": "Análise tarifária completa realizada com sucesso",
    "faturas_analisadas": 3,
    "info_processamento": {
        "total_arquivos_encontrados": 3,
        "arquivos_processados": 3,
        "arquivos_com_erro": 0,
        "fontes_utilizadas": {
            "local": 2,
            "google_drive": 1
        }
    },
    "analise": { /* resultados da análise */ }
}
```

## Configuração

### Variáveis de Ambiente

```bash
# Habilitar/desabilitar Google Drive
ENABLE_GOOGLE_DRIVE_FALLBACK=true

# Cache de downloads localmente
CACHE_GOOGLE_DRIVE_DOWNLOADS=true

# Caminhos das credenciais
GOOGLE_DRIVE_CREDENTIALS_PATH=credentials.json
GOOGLE_DRIVE_TOKEN_PATH=token.json
```

### Estrutura de Pastas no Google Drive

```
Google Drive/
└── Faturas EDP/
    └── 0000144112/
        ├── fatura_JAN-2025.pdf
        ├── fatura_FEV-2025.pdf
        └── fatura_MAR-2025.pdf
    └── 0000555666/
        ├── fatura_JAN-2025.pdf
        └── ... outros arquivos
```

**Organização por Instalação**: Cada instalação tem sua subpasta usando o código como nome.

## Arquivos Criados/Modificados

### Novos Arquivos
- `src/utils/google_drive_client.py` - Cliente para Google Drive API
- `src/utils/invoice_locator.py` - Sistema de localização com fallback
- `GOOGLE_DRIVE_SETUP.md` - Guia completo de configuração
- `.env.example` - Exemplo de configuração
- `README_GOOGLE_DRIVE_FALLBACK.md` - Esta documentação

### Arquivos Modificados
- `src/routes.py` - APIs atualizadas com fallback
- `requirements.txt` - Novas dependências adicionadas

## Compatibilidade

✅ **Totalmente Retrocompatível**
- Sistema funciona normalmente sem configuração do Google Drive
- APIs mantêm mesmo formato de resposta (com campos adicionais)
- Sem breaking changes no código existente

✅ **Graceful Degradation**
- Se Google Drive não estiver disponível, usa apenas busca local
- Erros de rede são tratados sem interromper operação
- Logs detalhados para debugging

## Logs e Monitoramento

O sistema gera logs detalhados:

```
INFO - Encontrados 2 arquivos locais para instalação 0000144112
INFO - Encontrados 1 arquivos no Google Drive para instalação 0000144112  
INFO - Arquivos encontrados por fonte: {'local': 2, 'google_drive': 1}
INFO - Arquivo fatura_FEV-2025.pdf baixado para /tmp/tmpxxx/fatura_FEV-2025.pdf
INFO - Processamento concluído: 3 sucessos, 0 erros
```

## Troubleshooting Comum

### Sem Dependências Google Drive
```
WARNING - Google Drive dependencies not available. Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```
**Solução**: Instalar dependências ou desabilitar com `ENABLE_GOOGLE_DRIVE_FALLBACK=false`

### Credenciais Não Encontradas
```
ERROR - Arquivo de credenciais credentials.json não encontrado.
```
**Solução**: Seguir `GOOGLE_DRIVE_SETUP.md` para configurar credenciais

### Performance
- Cache habilitado reduz tempo de resposta em consultas subsequentes
- Busca local sempre será mais rápida que Google Drive
- Considere usar apenas para arquivos não críticos em frequência

## Próximos Passos

Para produção, considere:
1. **Service Account** ao invés de OAuth para automação
2. **Rate Limiting** para APIs do Google Drive  
3. **Metrics/Alerting** para monitorar uso da quota
4. **Backup Strategy** com sincronização periódica
5. **Configuração de Regiões** para latência otimizada

## Suporte

Para dúvidas sobre configuração, consulte:
- `GOOGLE_DRIVE_SETUP.md` - Configuração detalhada
- Logs da aplicação para debugging
- Google Cloud Console para quotas e limits