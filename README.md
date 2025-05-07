# ⚡ Seger-WS: Web Scraper de Faturas EDP

Projeto automatizado com Playwright para realizar login, navegação e download de faturas em PDF do portal [EDP Online](https://www.edponline.com.br). Ideal para automação de relatórios de consumo ou integração com sistemas de gestão energética.

---

## 📦 Funcionalidades

- Login automatizado na área de clientes EDP.
- Consulta de instalações por número de instalação.
- Extração de faturas entre dois meses específicos (ex: `JAN-2024` a `ABR-2025`).
- Download automático das faturas em PDF para diretório local organizado por instalação.
- Tolerância a falhas com sistema de `retry`:
  - Modal quebrado (sem botão de download).
  - Erros no carregamento de faturas.
  - Timeout ou lentidão do site.
- Organização de faturas em subpastas: `faturas_edp/<número_instalação>/`.

---

## 🚀 Requisitos

- Python 3.9+
- Node.js (para dependências do Playwright)
- [Playwright para Python](https://playwright.dev/python/)
- Conta EDP com acesso válido (e-mail e senha)

---

## 🔧 Instalação

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/seger-ws.git
cd seger-ws

# Crie o ambiente virtual
python -m venv .venv
source .venv/bin/activate  # ou .\.venv\Scripts\activate no Windows

# Instale dependências
pip install -r requirements.txt

# Instale os navegadores do Playwright
playwright install
```

---

## 🔐 Configuração

Crie um arquivo `.env` com suas credenciais:

```env
EDP_LOGIN_EMAIL=seu-email@dominio.com
EDP_LOGIN_SENHA=sua_senha
```

---

## ▶️ Uso

Execute o script principal com os argumentos:

```bash
python app.py <lista_instalacoes> <MES_INICIO> <MES_FIM>
```

### Exemplo:

```bash
python app.py 1234567890,0987654321 JAN-2024 ABR-2025
```

> Isso irá baixar as faturas de **janeiro de 2024 até abril de 2025** para as instalações informadas.

---

## 📁 Estrutura de saída

```bash
faturas_edp/
├── 1234567890/
│   ├── fatura_1_JAN-2024.pdf
│   ├── ...
├── 0987654321/
│   ├── fatura_1_FEV-2024.pdf
│   ├── ...
```

---

## 🧠 Observações

- O scraper usa o Chromium via Playwright e depende da estrutura atual do site da EDP. Mudanças no HTML podem exigir ajustes no seletor.
- Em caso de falha de carregamento de modal, ele tenta clicar em "Voltar" ou recarregar a página de faturas.
- Apenas faturas da aba **"Faturas"** são processadas (ignora "Negociação de Pagamento").

---

## 🛠 Contribuições

Pull requests são bem-vindos! Para grandes mudanças, abra uma issue primeiro para discutir o que deseja alterar.

---

## 📄 Licença

MIT © [Seu Nome ou Equipe]
