# Configuração do Google Drive Fallback

Este documento explica como configurar o sistema de fallback para buscar PDFs de faturas no Google Drive quando não encontrados localmente.

## Pré-requisitos

1. **Dependências Python**: Execute `pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib`
2. **Conta Google**: Precisa de uma conta Google com acesso aos arquivos de faturas
3. **Projeto Google Cloud**: Configurar um projeto no Google Cloud Console

## Configuração do Google Cloud

### 1. Criar Projeto e Habilitar API

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/)
2. Crie um novo projeto ou selecione um existente
3. No menu de navegação, vá para "APIs & Services" > "Library"
4. Procure por "Google Drive API" e habilite-a

### 2. Criar Credenciais

1. Vá para "APIs & Services" > "Credentials"
2. Clique em "Create Credentials" > "OAuth client ID"
3. Se solicitado, configure a tela de consentimento OAuth:
   - Tipo: Aplicativo interno (para uso empresarial) ou Externo
   - Preencha as informações básicas do aplicativo
4. Para "Application type", selecione "Desktop application"
5. Dê um nome para o cliente (ex: "Seger Invoice Fallback")
6. Baixe o arquivo JSON das credenciais

### 3. Configurar Credenciais no Projeto

1. Renomeie o arquivo baixado para `credentials.json`
2. Coloque-o na raiz do projeto seger-ws (`/home/user/studio/seger-ws/credentials.json`)
3. **IMPORTANTE**: Adicione `credentials.json` e `token.json` ao `.gitignore`

## Organização no Google Drive

### Estrutura de Pastas Recomendada

```
Google Drive/
└── Faturas EDP/
    └── 0000144112/
        ├── fatura_JAN-2025.pdf
        ├── fatura_FEV-2025.pdf
        └── ... outros arquivos
    └── 0000555666/
        ├── fatura_JAN-2025.pdf
        └── ... outros arquivos
```

**IMPORTANTE**: Cada instalação deve ter sua própria subpasta dentro de "Faturas EDP", usando o código da instalação como nome da pasta.

### Convenção de Nomes dos Arquivos

O sistema reconhece os seguintes padrões de nomes:
- `fatura_MES-ANO.pdf` (ex: `fatura_JAN-2025.pdf`)
- `MES-ANO.pdf` (ex: `JAN-2025.pdf`)
- `Fatura_EDP_MES-ANO.pdf` (ex: `Fatura_EDP_JAN-2025.pdf`)

**Nota**: O código da instalação não é mais necessário no nome do arquivo, pois é identificado pela pasta.

## Configuração de Ambiente

### Variáveis de Ambiente

Crie um arquivo `.env` baseado no `.env.example`:

```bash
# Google Drive Fallback
ENABLE_GOOGLE_DRIVE_FALLBACK=true
CACHE_GOOGLE_DRIVE_DOWNLOADS=true
GOOGLE_DRIVE_CREDENTIALS_PATH=credentials.json
GOOGLE_DRIVE_TOKEN_PATH=token.json
```

### Descrição das Variáveis

- `ENABLE_GOOGLE_DRIVE_FALLBACK`: Habilita/desabilita o fallback do Google Drive
- `CACHE_GOOGLE_DRIVE_DOWNLOADS`: Se deve salvar os arquivos baixados localmente para futuras consultas
- `GOOGLE_DRIVE_CREDENTIALS_PATH`: Caminho para o arquivo de credenciais
- `GOOGLE_DRIVE_TOKEN_PATH`: Caminho onde será salvo o token de acesso

## Primeira Execução

### Autenticação

1. Na primeira execução, o sistema abrirá um navegador para autenticação
2. Faça login com sua conta Google
3. Autorize o aplicativo a acessar seus arquivos do Drive
4. O token de acesso será salvo automaticamente em `token.json`

### Teste de Funcionalidade

Execute uma consulta de faturas para uma instalação:

```bash
curl -X POST "http://localhost:5001/api/seger/faturas-json" \
-H "Content-Type: application/json" \
-d '{
    "codInstalacao": "0000144112",
    "data_inicio": "JAN-2025",
    "data_fim": "MAR-2025"
}'
```

A resposta incluirá informações sobre as fontes dos arquivos:

```json
{
    "message": "Dados consolidados extraídos com sucesso",
    "fontes_utilizadas": {
        "local": 2,
        "google_drive": 1
    },
    "dados": [...]
}
```

## Funcionamento do Sistema

### Ordem de Busca

1. **Busca Local**: Primeiro verifica a pasta `faturas_edp/{codigo}/`
2. **Busca Google Drive**: Se não encontrar localmente, busca no Drive
3. **Cache**: Arquivos do Drive são baixados e opcionalmente salvos localmente

### Logs e Monitoramento

O sistema gera logs detalhados sobre:
- Arquivos encontrados por fonte
- Downloads do Google Drive
- Erros de autenticação ou acesso
- Performance das buscas

### Tratamento de Erros

- Se o Google Drive não estiver disponível, o sistema continua funcionando apenas com busca local
- Erros de rede ou autenticação são logados, mas não interrompem o processamento
- Arquivos corrompidos ou ilegíveis são reportados individualmente

## Segurança

### Boas Práticas

1. **Nunca commitar credenciais**: Sempre adicionar ao `.gitignore`
2. **Usar conta de serviço**: Para ambientes de produção, considere usar Service Account
3. **Limitar escopos**: O sistema usa apenas `drive.readonly` (somente leitura)
4. **Monitorar acessos**: Verifique regularmente os logs de acesso no Google Cloud Console

### Troubleshooting

#### Erro: "Google Drive dependencies not available"
- Execute: `pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib`

#### Erro: "Arquivo de credenciais não encontrado"
- Verifique se o `credentials.json` está no caminho correto
- Confirme as permissões de arquivo

#### Erro: "Pasta 'Faturas EDP' não encontrada"
- Crie a pasta no Google Drive ou ajuste o nome no código
- Verifique se a conta tem acesso à pasta

#### Performance lenta
- Considere habilitar cache de downloads: `CACHE_GOOGLE_DRIVE_DOWNLOADS=true`
- Verifique a conexão com internet
- Monitore quotas da API no Google Cloud Console

## Customização

### Alterar Nome da Pasta

Edite o arquivo `src/utils/google_drive_client.py`, método `search_invoice_files()`:

```python
def search_invoice_files(self, codinstalacao: str, folder_name: str = "Sua Pasta Personalizada"):
```

### Adicionar Outros Padrões de Nome

Edite o método `extract_reference_from_filename()` para reconhecer novos padrões de arquivo.