"""
Módulo responsável por realizar o scraping de faturas de energia do portal online da EDP.

Utiliza Playwright para automatizar a navegação e download de arquivos PDF
de faturas para um ou mais números de instalação, dentro de um período
especificado.
"""
# seger/scraper.py
from playwright.sync_api import sync_playwright
import os
import re
import sys
from datetime import datetime
from dotenv import load_dotenv
import logging

load_dotenv()

BASE_DIR = os.path.join(os.getcwd(), "faturas_edp")
"""Diretório base onde as faturas baixadas serão salvas."""

LOG_DIR = os.path.join(os.getcwd(), "src/logs")
"""Diretório onde os arquivos de log do scraper serão armazenados."""

LOGIN_EMAIL = os.getenv("EDP_LOGIN_EMAIL", "")
"""E-mail utilizado para login no portal da EDP. Obtido de variável de ambiente."""

LOGIN_SENHA = os.getenv("EDP_LOGIN_SENHA", "")
"""Senha utilizada para login no portal da EDP. Obtida de variável de ambiente."""

# Configuração do logger
log_file = os.path.join(LOG_DIR, "scraper_edp.log")
os.makedirs(LOG_DIR, exist_ok=True)  # Garante que o diretório existe

logging.basicConfig(
    filename=log_file,
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO  # ou DEBUG para mais verbosidade
)

def ref_to_date(ref: str) -> datetime:
    """
        Converte uma string de referência de mês/ano (ex: "JAN-2023") para um objeto datetime.

        Similar à função no módulo routes, converte a referência textual
        para um objeto datetime.

        Args:
            ref: A string no formato "MMM-AAAA" (ex: "JAN-2023").

        Returns:
            Um objeto datetime representando o primeiro dia do mês e ano especificados, ou datetime.min se a string não estiver no formato esperado.
    """
    mes_map = {
        "JAN":"Jan","FEV":"Feb","MAR":"Mar","ABR":"Apr",
        "MAI":"May","JUN":"Jun","JUL":"Jul","AGO":"Aug",
        "SET":"Sep","OUT":"Oct","NOV":"Nov","DEZ":"Dec"
    }
    try:
        mes, ano = ref.upper().split("-")
        mon = mes_map.get(mes)
        return datetime.strptime(f"{mon}-{ano}", "%b-%Y") if mon else datetime.min
    except:
        return datetime.min

def reload_faturas(page,numero) -> None:
    """
        Tenta recarregar a página de faturas para uma instalação específica no Playwright.

        Usado internamente para tentar contornar erros de carregamento da página
        de faturas no portal da EDP.

        Args:
            page: O objeto Page do Playwright representando a página atual.
            numero: O número da instalação a ser recarregada.
    """
    while True:
        page.goto("https://www.edponline.com.br/servicos/consulta-debitos", wait_until="load")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)") 
        page.fill('input[name="Instalacao"]', numero)
        page.click('button:has-text("Avançar")')
        page.wait_for_timeout(3000)
        page.locator(f'a.instalacao:has-text("{numero}")').click()
        # Verifica se o erro de carregamento apareceu
        erro_carregamento = page.locator('text="Desculpe-nos! Não foi possível carregar as suas faturas"')
        if erro_carregamento.is_visible(timeout=3000):
            logging.warning("  ⚠️ Erro ao carregar faturas. Tentando novamente...")
            page.go_back()
            page.wait_for_timeout(3000)
            continue  # Tenta novamente
        else:
            sucesso = True
            break  # Sai do loop se carregou corretamente

def get_logged_context(p, mode=True, force_login=False):
    """
        Obtém um contexto de navegador Playwright logado no portal da EDP.

        Tenta reutilizar uma sessão salva em arquivo (`edp_session.json`). Caso
        não encontre ou force um novo login, realiza o processo de login
        e salva a nova sessão.

        Args:
            p: O objeto sync_playwright.
            mode: Booleano indicando se o navegador deve ser headless (True) ou visível (False). Padrão é True.
            force_login: Booleano indicando se um novo login deve ser forcado, mesmo que uma sessão salva exista. Padrão é False.

        Returns: Uma tupla contendo o objeto Browser e o objeto Context do Playwright.
    """
    session_path = "edp_session.json"
    browser = p.chromium.launch(headless=mode)

    if not force_login and os.path.exists(session_path):
        logging.info("♻️ Sessão encontrada. Utilizando sessão salva.")
        ctx = browser.new_context(
            accept_downloads=True,
            storage_state=session_path
        )
        return browser, ctx

    # Caso contrário, cria nova sessão e realiza login
    logging.info("🔁 Criando nova sessão com login.")
    ctx = browser.new_context(accept_downloads=True)
    page = ctx.new_page()
    realizar_login(page, LOGIN_EMAIL, LOGIN_SENHA)

    # Salva a sessão após login bem-sucedido
    ctx.storage_state(path=session_path)
    logging.info("💾 Sessão salva em edp_session.json.")
    return browser, ctx

def realizar_login(page, email: str, senha: str):
    """
        Realiza o processo de login no portal online da EDP utilizando Playwright.

        Navega para a página de login, preenche as credenciais e tenta
        logar. Lida com a aceitação de cookies.

        Args:
            page: O objeto Page do Playwright representando a página de login.
            email: O e-mail para login.
            senha: A senha para login.

        Returns: True se o login for bem-sucedido (redirecionado para a página de serviços), False caso contrário.
    """
    logging.info("🔐 Navegando para página de login...")
    page.goto("https://www.edponline.com.br/engenheiro", wait_until="load")
    logging.info("✅ Página de login carregada.")

    # Tenta aceitar cookies ou ignora se não for possível
    try:
        page.locator("button#onetrust-accept-btn-handler").click(timeout=3000)
        page.wait_for_timeout(1000)
        logging.info("🍪 Cookies aceitos.")
    except:
        try:
            # Força remoção via JS se overlay estiver atrapalhando clique
            page.evaluate("document.getElementById('onetrust-consent-sdk')?.remove()")
            logging.info("🧹 Overlay de cookies removido via JS.")
        except:
            logging.warning("⚠️ Não foi possível lidar com cookies. Continuando...")

    # Tenta selecionar opção "Pessoa Física"
    try:
        page.locator('label[for="option-1"]').click(timeout=5000)
        logging.info("🧑‍💼 Opção Pessoa Física selecionada.")
    except Exception as e:
        logging.error(f"❌ Erro ao selecionar Pessoa Física: {e}")
        return False
    email_input = page.locator('input#Email')
    senha_input = page.locator('input[type="password"]')
    # Preenche credenciais
    try:
        email_input.click(timeout=5000)
        email_input.fill(email)
        senha_input.click(timeout=5000)
        senha_input.fill(senha)
        page.keyboard.press("Tab")
        
        logging.info("✉️ E-mail e 🔒 senha preenchidos.")

        # Aguarda botão de acesso
        btn_acessar = page.locator("button#acessar:enabled")
        btn_acessar.wait_for(state="visible", timeout=7000)
        btn_acessar.click()
        logging.info("🚪 Login enviado, aguardando redirecionamento...")

        # Espera redirecionamento após login
        for _ in range(50):
            if "/servicos" in page.url:
                logging.info("✅ Login realizado com sucesso!")
                return True
            page.wait_for_timeout(300)

    except Exception as e:
        logging.error(f"❌ Erro durante login: {e}")

    return False

def baixar_faturas_por_instalacao(instalacoes: list[str], data_inicio: str, data_fim: str, mode: bool = True) -> list[str]:
    """
        Baixa faturas de energia para uma lista de números de instalação dentro de um período.

        Utiliza Playwright para navegar no portal da EDP, selecionar cada instalação,
        localizar as faturas dentro do intervalo de datas especificado e baixar
        os arquivos PDF correspondentes.

        Args:
            instalacoes: Uma lista de strings, onde cada string é o número da instalação.
            data_inicio: Uma string no formato "MMM-AAAA" representando a data de início
                        do intervalo de faturas a serem baixadas (inclusivo).
            data_fim: Uma string no formato "MMM-AAAA" representando a data de fim
                    do intervalo de faturas a serem baixadas (inclusivo).
            mode: Booleano indicando se o navegador Playwright deve ser headless (True) ou visível (False). Padrão é True.

        Returns:
            Uma lista de strings, onde cada string é o caminho completo para o arquivo
            PDF da fatura baixada.

        Raises: Exception: Para erros que possam ocorrer durante o processo de scraping.
    """
    dt_ini = ref_to_date(data_inicio)
    dt_fim = ref_to_date(data_fim)
    saved_paths: list[str] = []

    with sync_playwright() as p:
        browser, ctx = get_logged_context(p, mode, False)
        page = ctx.new_page()

        # Verifica se a sessão está válida
        page.goto("https://www.edponline.com.br/servicos/consulta-debitos", wait_until="load")
        if "/servicos" not in page.url:
            logging.info("🔒 Sessão expirada. Realizando login novamente.")
            realizar_login(page, LOGIN_EMAIL, LOGIN_SENHA)
            ctx.storage_state(path="edp_session.json")

        sair_instalacao = page.locator('a.edp-btn-dark:has-text("Sair da Instalação")')
        if sair_instalacao.is_visible(timeout=5000):
            sair_instalacao.click()
            logging.info("↩️ Sessão ativa: saída da instalação realizada.")
        else:
            logging.info("✅ Sessão ativa: nenhuma instalação estava aberta.")
        
        for numero in instalacoes:
            logging.info(f"Processando instalação: {numero}")
            pasta_instalacao = os.path.join(BASE_DIR, numero)
            os.makedirs(pasta_instalacao, exist_ok=True)

            max_tentativas = 3
            tentativa = 0
            sucesso = False
            
            while tentativa < max_tentativas:
                tentativa += 1
                logging.info(f"  🔁 Tentativa {tentativa} para carregar faturas...")

                # Vai para página de consulta
                page.goto("https://www.edponline.com.br/servicos/consulta-debitos", wait_until="load")
                logging.info("  🔄  Página de consulta carregada.")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.fill('input[name="Instalacao"]', numero)
                btn_click = page.locator('button:has-text("Avançar")')
                btn_click.wait_for(state="visible", timeout=20000)
                page.click('button:has-text("Avançar")')
                logging.info("  🔄  Página Instalação do cliente carregada.")
                link_click = page.locator(f'a.instalacao:has-text("{numero}")')
                link_click.wait_for(state="visible", timeout=20000)
                link_click.click()
                # Verifica se o erro de carregamento apareceu
                erro_carregamento = page.locator('text="Desculpe-nos! Não foi possível carregar as suas faturas"')
                if erro_carregamento.is_visible(timeout=3000):
                    logging.warning("  ⚠️ Erro ao carregar faturas. Tentando novamente...")
                    page.go_back()
                    page.wait_for_timeout(3000)
                    continue  # Tenta novamente
                else:
                    sucesso = True
                    break  # Sai do loop se carregou corretamente

            if not sucesso:
                logging.error("  ❌ Falha ao carregar faturas após 3 tentativas. Pulando instalação.")
                continue
            page.wait_for_timeout(3000)
            logging.info("  🔄  Página de faturas carregada.")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)") 
            page.wait_for_timeout(500)
            # Ver mais faturas
            for _ in range(21):
                try:
                    ver_mais = page.locator('button:has-text("Ver mais faturas")')
                    if ver_mais.is_visible(timeout=3000):
                        ver_mais.scroll_into_view_if_needed()
                        ver_mais.click()
                        page.wait_for_timeout(1000)
                    else:
                        logging.info("🔽 Nenhum botão 'Ver mais faturas' visível.")
                        break
                except Exception as e:
                    logging.warning(f"⚠️ Erro ao clicar em 'Ver mais faturas': {e}")
                    break

            cards = page.locator('div.tab-pane.active div.card.card-extrato.card-opcoes-segunda-via')
            total = cards.count()
            logging.info(f"  Encontradas {total} faturas.")

            for i in range(total):
                try:
                    card = cards.nth(i)
                    ref_text = card.locator(':scope >> text=/Referente/').first.inner_text()
                    ref_match = re.search(r'([A-Z]{3}/\d{4})', ref_text)
                    if not ref_match:
                        continue
                    ref = ref_match.group(1).replace("/", "-")
                    ref_dt = ref_to_date(ref)

                    if not (min(dt_ini, dt_fim) <= ref_dt <= max(dt_ini, dt_fim)):
                        logging.info(f"    ⏭️  Pulando fatura {ref} fora do intervalo.")
                        continue

                    logging.info(f"    ⬇️  Baixando fatura {ref}...")
                    max_retentativas = 3
                    for tentativa in range(max_retentativas):
                        try:
                            card.locator('p:has-text("Visualizar fatura")').click()
                            page.wait_for_selector('text="2ª Via de Fatura"', timeout=15000)

                            # Verifica se o botão "Baixar" apareceu
                            btn_baixar = page.locator('a:has-text("Baixar")')
                            btn_baixar.wait_for(state="visible", timeout=35000)
                            if btn_baixar.is_visible():
                                break  # modal carregou corretamente, pode prosseguir
                            else:
                                raise Exception("Modal não carregou corretamente")

                        except:
                            logging.warning(f"      ⚠️ Modal com erro, tentativa {tentativa + 1}/{max_retentativas}")
                            try:
                                voltar_btn = page.locator('button.btn-outline-main-2:has-text("Voltar")')
                                voltar_btn.wait_for(state="visible", timeout=15000)
                                if voltar_btn.is_visible():
                                    voltar_btn.click()
                                    page.wait_for_timeout(500)
                            except:
                                reload_faturas(page, numero)
                                logging.warning("      ⚠️ Botão 'Voltar' não estava disponível.")

                    if not page.locator('a:has-text("Baixar")').is_visible():
                        logging.error("      ❌ Falha ao abrir modal corretamente após tentativas.")
                        continue  # pula para a próxima fatura

                    with page.expect_download() as dl:
                        download_bt = page.locator('a:has-text("Baixar")')
                        download_bt.wait_for(state="visible", timeout=15000)
                        download_bt.click()
                    download = dl.value
                    nome = f"fatura_{ref}.pdf"
                    caminho = os.path.join(pasta_instalacao, nome)
                    download.save_as(caminho)
                    saved_paths.append(caminho)
                    logging.info(f"      ✔️  Salva em: {caminho}")

                    try:
                        fechar_modal = page.locator('i.icon-edp-circle-error.fs-1')
                        fechar_modal.wait_for(state="visible", timeout=20000)
                        fechar_modal.click()
                    except:
                        logging.warning("      ⚠️ Não foi possível fechar o modal de fatura.")

                except Exception as e:
                    logging.warning(f"      ⚠️ Erro ao baixar fatura {i+1}: {e}")
                    continue

            try:
                sair = page.locator('a.edp-btn-dark:has-text("Sair da Instalação")').first
                sair.wait_for(state="visible", timeout=10000)
                sair.click()
                logging.info("  🔄 Retornando para seleção de instalação...")
                for _ in range(100):
                    if "/servicos" in page.url:
                        break
                    page.wait_for_timeout(100)
            except Exception as e:
                logging.warning(f"  ⚠️ Não foi possível clicar em 'Sair da Instalação': {e}")


        ctx.close()
        browser.close()
        
    return saved_paths
