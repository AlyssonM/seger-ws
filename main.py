from playwright.sync_api import sync_playwright
import os
import time
from dotenv import load_dotenv
import re

load_dotenv()

# Lista de números de instalação a processar
#INSTALACOES = ["0009500016", "0009501331", "160424296", "9502682", "0000144112"]  # Grupo 1
INSTALACOES = ["0009501331"]  # Grupo 1
BASE_DIR = os.path.join(os.getcwd(), "faturas_edp")
LOGIN_EMAIL = os.getenv("EDP_LOGIN_EMAIL", "")
LOGIN_SENHA = os.getenv("EDP_LOGIN_SENHA", "")

def baixar_faturas_por_instalacao():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            accept_downloads=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for numero in INSTALACOES:
            print(f"Processando instalação: {numero}")
            pasta_instalacao = os.path.join(BASE_DIR, numero)
            os.makedirs(pasta_instalacao, exist_ok=True)

            # Etapa 1: Acessa a página de login
            page.goto("https://www.edponline.com.br/engenheiro")
            page.wait_for_timeout(3000)

            # Etapa 1.1: Força seleção do estado Espírito Santo
            try:
                page.locator("button#onetrust-accept-btn-handler").click(timeout=3000)
                print("  🍪 Consentimento de cookies aceito.")
            except:
                print("  ⚠️ Modal de cookies não estava visível.")
            try:   
                page.locator('label[for="option-1"]').click()
                page.wait_for_timeout(1000)
                print("  ✔️ Estado selecionado: Espírito Santo")
            except Exception as e:
                print(f"  ⚠️ Não foi possível selecionar o estado: {e}")

            # Etapa 1.2: Preenche login e senha e dispara login via JS
            try:
                box = page.locator('input#Email').bounding_box()
                page.click("#Email")
                page.keyboard.type(LOGIN_EMAIL)
                box = page.locator('input#Senha').bounding_box()
                # Clica no campo Senha e digita
                page.mouse.click(box['x'], box['y'])
                page.keyboard.type(LOGIN_SENHA)
                page.keyboard.press("Tab")
                page.wait_for_selector("button#acessar:enabled", timeout=5000)
                page.click("button#acessar")
                # Aguarda até a URL conter /servicos
                for _ in range(100):  # Tenta por até 10 segundos
                    if "/servicos" in page.url:
                        break
                    page.wait_for_timeout(100)  # 100 ms
                print("  ✔️ Login realizado com sucesso e página /servicos carregada")
            except Exception as e:
                print(f"  ❌ Erro ao tentar logar: {e}")
                continue

            
            # Etapa 2: Acessa a página de consulta
            page.goto("https://www.edponline.com.br/servicos/consulta-debitos", wait_until="load")
            try:
                # Usa evaluate ao invés de locator para preencher o campo e clicar no botão
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_selector('input[name="Instalacao"]', timeout=10000)
                page.fill('input[name="Instalacao"]', numero)
                page.click('button:has-text("Avançar")')     
            except:
                print(f"  ❌ Campo de número de instalação não encontrado para {numero}. Pulando.")
                continue

            # Etapa 4: Espera a tela de faturas carregar
            try:
                page.locator(f'a.instalacao:has-text("{numero}")').click()
                page.wait_for_timeout(5000)
            except:
                print(f"  ❌ Página de detalhe de fatura não carregou para {numero}. Pulando.")
                continue

            # Etapa 5: Expande todas as faturas visíveis
            count_clicks = 0
            while True:
                try:
                    ver_mais = page.locator('button:has-text("Ver mais faturas")')
                    if count_clicks <= 10: # if ver_mais.is_visible()  => para baixar todas as faturas
                        ver_mais.click()
                        page.wait_for_timeout(1000)
                        count_clicks += 1
                    else:
                        break
                except:
                    break

            # Etapa 6: Coleta e baixa todas as faturas
            cards = page.locator('div.card.card-extrato.card-opcoes-segunda-via')
            total = cards.count()
            # botoes = page.locator('p:has-text("Visualizar fatura")')
            # total = botoes.count()

            print(f"  Encontradas {total} faturas.")

            for i in range(total):
                print(f"    Baixando fatura {i + 1} de {total}...")

                try:
                    card = cards.nth(i)
                    # Localiza o botão novamente a cada iteração para evitar staleness
                    # Procura o texto "Referente XXX/YYYY"
                    referencia_raw = card.locator(':scope >> text=/Referente/').first.inner_text()
                    referencia_match = re.search(r'([A-Z]{3}/\d{4})', referencia_raw)
                    referencia = referencia_match.group(1).replace("/", "-") if referencia_match else f"desconhecido_{i+1}"
                    card.locator('p:has-text("Visualizar fatura")').click()
                    page.wait_for_selector('text="2ª Via de Fatura"', timeout=10000)
                    with page.expect_download() as download_info:
                        page.click('text="Baixar"')

                    download = download_info.value
                    timestamp = int(time.time())
                    nome = f"fatura_{i+1}_{referencia}.pdf"
                    caminho = os.path.join(pasta_instalacao, nome)
                    download.save_as(caminho)
                    print(f"      ✔️  Salva em: {caminho}")

                    # Fecha o modal
                    page.locator('i.icon-edp-circle-error.fs-1').click()
                except Exception as e:
                    print(f"      ⚠️ Erro ao baixar fatura {i+1}: {e}")
                    continue


        browser.close()

if __name__ == "__main__":
    baixar_faturas_por_instalacao()
