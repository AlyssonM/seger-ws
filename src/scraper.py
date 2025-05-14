# seger/scraper.py
from playwright.sync_api import sync_playwright
import os
import re
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BASE_DIR    = os.path.join(os.getcwd(), "faturas_edp")
LOGIN_EMAIL = os.getenv("EDP_LOGIN_EMAIL", "")
LOGIN_SENHA = os.getenv("EDP_LOGIN_SENHA", "")

def ref_to_date(ref: str) -> datetime:
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

def reload_faturas(page) -> None:
    page.goto("https://www.edponline.com.br/servicos/consulta-debitos", wait_until="load")
    for _ in range(11):
        try:
            btn = page.locator('button:has-text("Ver mais faturas")')
            if btn.is_visible():
                btn.click()
                page.wait_for_timeout(1000)
            else:
                break
        except:
            break

def baixar_faturas_por_instalacao(instalacoes: list[str], data_inicio: str, data_fim: str, mode: bool = True) -> list[str]:
    dt_ini = ref_to_date(data_inicio)
    dt_fim = ref_to_date(data_fim)
    saved_paths: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=mode)
        ctx     = browser.new_context(accept_downloads=True)
        page    = ctx.new_page()

        # === Login ===
        page.goto("https://www.edponline.com.br/engenheiro", wait_until="load")
        try:
            page.locator("button#onetrust-accept-btn-handler").click(timeout=3000)
        except:
            pass
        page.locator('label[for="option-1"]').click()
        page.click("#Email")
        page.keyboard.type(LOGIN_EMAIL)
        page.click("#Senha")
        page.keyboard.type(LOGIN_SENHA)
        page.keyboard.press("Tab")
        page.wait_for_selector("button#acessar:enabled", timeout=5000)
        page.wait_for_timeout(100)
        page.click("button#acessar")
        for _ in range(300):
            if "/servicos" in page.url:
                break
            page.wait_for_timeout(100)

        for numero in instalacoes:
            print(f"Processando instalação: {numero}")
            pasta_instalacao = os.path.join(BASE_DIR, numero)
            os.makedirs(pasta_instalacao, exist_ok=True)

            max_tentativas = 3
            tentativa = 0
            sucesso = False

            while tentativa < max_tentativas:
                tentativa += 1
                print(f"  🔁 Tentativa {tentativa} para carregar faturas...")

                # Vai para página de consulta
                page.goto("https://www.edponline.com.br/servicos/consulta-debitos", wait_until="load")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.fill('input[name="Instalacao"]', numero)
                page.click('button:has-text("Avançar")')
                page.wait_for_timeout(3000)
                page.locator(f'a.instalacao:has-text("{numero}")').click()
                page.wait_for_timeout(5000)
                # Verifica se o erro de carregamento apareceu
                erro_carregamento = page.locator('text="Desculpe-nos! Não foi possível carregar as suas faturas"')
                if erro_carregamento.is_visible(timeout=3000):
                    print("  ⚠️ Erro ao carregar faturas. Tentando novamente...")
                    page.go_back()
                    page.wait_for_timeout(3000)
                    continue  # Tenta novamente
                else:
                    sucesso = True
                    break  # Sai do loop se carregou corretamente

            if not sucesso:
                print("  ❌ Falha ao carregar faturas após 3 tentativas. Pulando instalação.")
                continue
            
            ver_mais = page.locator('button:has-text("Ver mais faturas")')
            ver_mais.wait_for(state="visible", timeout=30000)
            # Ver mais faturas
            for _ in range(11):
                try:
                    ver_mais = page.locator('button:has-text("Ver mais faturas")')
                    if ver_mais.is_visible():
                        ver_mais.click()
                        page.wait_for_timeout(1000)
                    else:
                        break
                except:
                    break

            cards = page.locator('div.tab-pane.active div.card.card-extrato.card-opcoes-segunda-via')
            total = cards.count()
            print(f"  Encontradas {total} faturas.")

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
                        print(f"    ⏭️  Pulando fatura {ref} fora do intervalo.")
                        continue

                    print(f"    ⬇️  Baixando fatura {ref}...")
                    # card.locator('p:has-text("Visualizar fatura")').click()
                    # page.wait_for_selector('text="2ª Via de Fatura"', timeout=15000)
                    max_retentativas = 3
                    for tentativa in range(max_retentativas):
                        try:
                            card.locator('p:has-text("Visualizar fatura")').click()
                            page.wait_for_selector('text="2ª Via de Fatura"', timeout=15000)

                            # Verifica se o botão "Baixar" apareceu
                            btn_baixar = page.locator('a:has-text("Baixar")')
                            btn_baixar.wait_for(state="visible", timeout=15000)
                            if btn_baixar.is_visible():
                                break  # modal carregou corretamente, pode prosseguir
                            else:
                                raise Exception("Modal não carregou corretamente")

                        except:
                            print(f"      ⚠️ Modal com erro, tentativa {tentativa + 1}/{max_retentativas}")
                            try:
                                voltar_btn = page.locator('button.btn-outline-main-2:has-text("Voltar")')
                                voltar_btn.wait_for(state="visible", timeout=15000)
                                if voltar_btn.is_visible():
                                    voltar_btn.click()
                                    page.wait_for_timeout(3000)
                            except:
                                reload_faturas(page)
                                print("      ⚠️ Botão 'Voltar' não estava disponível.")

                    if not page.locator('a:has-text("Baixar")').is_visible():
                        print("      ❌ Falha ao abrir modal corretamente após tentativas.")
                        continue  # pula para a próxima fatura

                    with page.expect_download() as dl:
                        page.click('a:has-text("Baixar")')
                    download = dl.value
                    # nome     = f"fatura_{i+1}_{ref}.pdf"
                    # dest     = os.path.join(pasta, nome)
                    # download.save_as(dest)
                    # print(f"      ✔️ Salvo em: {dest}")
                    # saved_paths.append(dest)
                    # download = download_info.value
                    nome = f"fatura_{i+1}_{ref}.pdf"
                    caminho = os.path.join(pasta_instalacao, nome)
                    download.save_as(caminho)
                    saved_paths.append(caminho)
                    print(f"      ✔️  Salva em: {caminho}")

                    try:
                        fechar_modal = page.locator('i.icon-edp-circle-error.fs-1')
                        fechar_modal.wait_for(state="visible", timeout=20000)
                        fechar_modal.click()
                    except:
                        print("      ⚠️ Não foi possível fechar o modal de fatura.")

                except Exception as e:
                    print(f"      ⚠️ Erro ao baixar fatura {i+1}: {e}")
                    continue

            try:
                sair = page.locator('a.edp-btn-dark:has-text("Sair da Instalação")').first
                sair.wait_for(state="visible", timeout=10000)
                sair.click()
                print("  🔄 Retornando para seleção de instalação...")
                for _ in range(100):
                    if "/servicos" in page.url:
                        break
                    page.wait_for_timeout(100)
            except Exception as e:
                print(f"  ⚠️ Não foi possível clicar em 'Sair da Instalação': {e}")


        browser.close()
        #             try:
        #                 page.locator('i.icon-edp-circle-error.fs-1').click(timeout=5000)
        #             except:
        #                 pass

        #         except Exception as e:
        #             print(f"      ⚠️ Erro ao baixar fatura {i+1}: {e}")

        #     # Sai da instalação
        #     try:
        #         btn = page.locator('a.edp-btn-dark:has-text("Sair da Instalação")').first
        #         btn.click(); page.wait_for_timeout(1000)
        #         print("  🔄 Voltando para lista de instalações...")
        #     except:
        #         pass

        # browser.close()

    return saved_paths
