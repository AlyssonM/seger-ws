# seger/routes.py
"""
Módulo que define as rotas (endpoints) da API para funcionalidades relacionadas ao Seger.

Este módulo gerencia as requisições HTTP para baixar, processar e analisar
faturas de energia, além de fornecer dados de tarifas e realizar otimizações
de custo.
"""

from flask import Blueprint, request, jsonify, send_file
from src.scraper import baixar_faturas_por_instalacao
from src.parser  import extrair_dados_completos_da_fatura, analisar_eficiencia_energetica
from src.utils.dict_diff import dict_diff, has_diff
from src.utils.tarifas import get_tarifas_filtradas
from src.utils.tarifas import calcular_tarifa_azul, calcular_tarifa_verde
from src.utils.tarifas import extrair_tarifa_compacta_por_modalidade
from src.optmization import opt_tarifa_verde, opt_tarifa_azul
import requests
import os
import re
from datetime import datetime
import logging
from operator import itemgetter

bp = Blueprint("seger", __name__, url_prefix="/api/seger")
SEGER_DADOS_FATURA_URL = "http://localhost:5000/api/seger/dados-fatura"

# Mapa de meses
MES_MAP = {
    "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4,
    "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8,
    "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12
}

def ref_to_date(ref: str) -> datetime:
    """
    Converte uma string de referência de mês/ano (ex: "JAN-2023") para um objeto datetime.

    Args:
        ref: A string no formato "MMM-AAAA" (ex: "JAN-2023").

    Returns:
        Um objeto datetime representando o primeiro dia do mês e ano especificados,
        ou datetime.min se a string não estiver no formato esperado.
    """
    try:
        mes, ano = ref.upper().split("-")
        return datetime(int(ano), MES_MAP[mes], 1)
    except:
        return datetime.min

def converter_tarifas_para_kwh(tarifas_compactadas):
    """
    Converte valores de tarifas de MWh para kWh.

    Identifica as chaves que representam tarifas de energia em MWh dentro do
    dicionário de tarifas compactadas e converte seus valores para kWh,
    dividindo por 1000.

    Args:
        tarifas_compactadas: Um dicionário contendo as tarifas organizadas
                             por modalidade e tipo, com alguns valores em MWh.

    Returns:
        O mesmo dicionário de tarifas, mas com os valores de tarifas de energia
        convertidos para kWh.
    """
    # Define quais chaves são tarifas de energia (em MWh e devem ser convertidas)
    chaves_energia = {
        "TE", "TUSD",
        "TEponta", "TUSDponta",
        "TEforaPonta", "TUSDforaPonta",
        "TEintermediario", "TUSDintermediario"
    }

    for modalidade in tarifas_compactadas:
        for chave in tarifas_compactadas[modalidade]:
            if chave in chaves_energia and tarifas_compactadas[modalidade][chave] is not None:
                tarifas_compactadas[modalidade][chave] = round(
                    tarifas_compactadas[modalidade][chave] / 1000, 6
                )
    return tarifas_compactadas

@bp.route("/faturas", methods=["POST"])
def faturas():
    """
    Endpoint para baixar faturas de energia.

    Recebe uma lista de códigos de instalação e um intervalo de datas
    e aciona o scraper para baixar as faturas correspondentes.

    Body da Requisição (JSON):
        {
          "instalacoes": ["cod_instalacao1", "cod_instalacao2"],
          "data_inicio": "JAN-2023",
          "data_fim": "DEZ-2023",
          "mode": true
        }

    Respostas:

    """
    data = request.get_json(force=True)
    instalacoes = data.get("instalacoes")
    inicio      = data.get("data_inicio")
    fim         = data.get("data_fim")
    mode        = data.get("mode", True)
    # validação mínima
    if not isinstance(instalacoes, list) or not inicio or not fim:
        return jsonify({"error": "instalacoes (lista), data_inicio e data_fim são obrigatórios"}), 400

    # dispara o scraper e retorna os paths
    try:
        paths = baixar_faturas_por_instalacao(instalacoes, inicio, fim, mode)
        return jsonify({"pdfs": paths})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/faturas/<path:pdf_path>", methods=["GET"])
def download(pdf_path):
    """
    Endpoint para baixar um arquivo PDF de fatura.

    Args:
        pdf_path: O caminho para o arquivo PDF a ser baixado.

    Respostas:
        200 OK: O arquivo PDF como anexo.
        404 Not Found: Se o arquivo PDF não for encontrado.
        # Pode haver outros códigos de erro dependendo da implementação de send_file
    """
    # envia o PDF como anexo
    return send_file(pdf_path, mimetype="application/pdf", as_attachment=True)

@bp.route("/dados-fatura", methods=["POST"])
def dados_fatura():
    data     = request.get_json(force=True)
    pdf_path = data.get("pdf_path", "")
    """
    Endpoint para extrair dados estruturados de um arquivo PDF de fatura.

    Recebe o caminho de um arquivo PDF e extrai informações relevantes
    utilizando o parser.

    Body da Requisição (JSON):
        {
          "pdf_path": "caminho/arquivo.pdf",
          "via_regex": true  # Opcional, padrão é true
        }

    Respostas:
        200 OK: JSON contendo os dados extraídos da fatura.

    """
    via_regex  = data.get("via_regex", True)
    if not pdf_path:
        return jsonify({"error": "pdf_path é obrigatório"}), 400

    # logging.info(f"Extraindo dados da fatura de {pdf_path}")
    try:
        dados = extrair_dados_completos_da_fatura(pdf_path, via_regex=via_regex)
        return jsonify(dados)
    except Exception as e:
        import traceback
        traceback_str = traceback.format_exc()
        return jsonify({"error": str(traceback_str)}), 500

@bp.route("/faturas-json", methods=["POST"])
def dados_fatura_json():
    data = request.get_json(force=True)
    """
    Endpoint para obter dados de faturas em formato JSON para um intervalo de datas.

    Recebe o código de instalação, data de início e data de fim, localiza
    as faturas no diretório correspondente, extrai os dados de cada fatura
    e retorna um JSON consolidado.

    Body da Requisição (JSON):
        {
          "data_inicio": "JAN-2023",
          "data_fim": "DEZ-2023",
          "codInstalacao": "codigo_da_instalacao",
          "via_regex": true # Opcional, padrão é true
        }

    Respostas:
        200 OK: JSON contendo os dados consolidados das faturas no intervalo.
    """
    via_regex = data.get("via_regex", True)
    data_inicio = data.get("data_inicio")
    data_fim = data.get("data_fim")
    codinstalacao = data.get("codInstalacao")

    if not all([data_inicio, data_fim, codinstalacao]):
        return jsonify({"error": "Parâmetros obrigatórios: data_inicio, data_fim, CodInstalacao"}), 400

    dt1 = ref_to_date(data_inicio)
    dt2 = ref_to_date(data_fim)
    dt_ini, dt_fim = min(dt1, dt2), max(dt1, dt2)

    pasta_instalacao = os.path.join("/app/faturas_edp/", codinstalacao)
    if not os.path.exists(pasta_instalacao):
        return jsonify({"error": f"Pasta não encontrada para instalação {codinstalacao}"}), 404

    pdf_infos = []
    for nome_arquivo in os.listdir(pasta_instalacao):
        match = re.search(r'_(\w{3})-(\d{4})\.pdf$', nome_arquivo)
        if match:
            ref = f"{match.group(1)}-{match.group(2)}"
            dt_ref = ref_to_date(ref)
            if dt_ini <= dt_ref <= dt_fim:
                pdf_infos.append((dt_ref, os.path.join(pasta_instalacao, nome_arquivo)))

    pdf_infos.sort(key=itemgetter(0), reverse=True)
    pdf_paths = [path for _, path in pdf_infos]

    if not pdf_paths:
        return jsonify({"error": "Nenhuma fatura encontrada no intervalo informado"}), 404

    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": "chave-secreta-supersegura"
    }

    # Inicializa vetores
    faturas_data = {
        "mes_referencia": [],
        "Energia_Ativa_Ponta": [],
        "Energia_Ativa_Fora_Ponta": [],
        "Demanda_Maxima_Ponta": [],
        "Demanda_Maxima_Fora_Ponta": [],
        "ERE": [],
        "DRE_Ponta": [],
        "DRE_Fora_Ponta": [],
        "Bandeira": [],
        "Juros_e_Multas": [],
        "DIC_IFC": [],
        "Iluminacao_Publica": [],
        "Retencao_Imposto": [],
        "PIS": [],
        "COFINS": [],
        "ICMS": [],
        "Fatura_total": []
    }

    for dt_ref, pdf_path in pdf_infos:
        try:
            response = requests.post(
                SEGER_DADOS_FATURA_URL,
                json={"pdf_path": pdf_path, "via_regex": via_regex},
                headers=headers
            )
            response.raise_for_status()
            data_json = response.json()
            # logging.info(f"Dados da fatura para {pdf_path}:\n{data_json}")
            nome_arquivo = os.path.basename(pdf_path)
            match = re.search(r'_(\w{3})-(\d{4})\.pdf$', nome_arquivo)
            mes_referencia = match.group(1) + "-" + match.group(2) if match else "DESCONHECIDO"

            faturas_data["mes_referencia"].append(mes_referencia)

            faturas_data["Energia_Ativa_Ponta"].append(
                data_json.get("consumo_ativo", {}).get("ponta_kwh", 0))

            faturas_data["Energia_Ativa_Fora_Ponta"].append(
                data_json.get("consumo_ativo", {}).get("fora_ponta_kwh", 0))

            faturas_data["Demanda_Maxima_Ponta"].append(
                data_json.get("demanda", {}).get("maxima", [{}])[0].get("valor_kw", 0))

            faturas_data["Demanda_Maxima_Fora_Ponta"].append(
                data_json.get("demanda", {}).get("maxima", [{}, {}])[1].get("valor_kw", 0))

            faturas_data["ERE"].append(
                data_json.get("energia_reativa", {}).get("excedente", {}).get("total_kwh", 0.0)
            )

            # Componentes extras
            extras = data_json.get("componentes_extras", [])
            juros_multas = sum(c.get("valor_total", 0.0) for c in extras if "juros" in c["descricao"].lower() or "multa" in c["descricao"].lower())
            retencao = sum(c.get("valor_impostos", 0.0) for c in extras if "imposto de renda" in c["descricao"].lower())

            faturas_data["Juros_e_Multas"].append(juros_multas)
            faturas_data["Retencao_Imposto"].append(retencao)

            # Energia reativa excedente (DRE)
            dre = data_json.get("energia_reativa", {}).get("excedente", {})
            faturas_data["DRE_Ponta"].append(dre.get("ponta_kwh", 0.0))
            faturas_data["DRE_Fora_Ponta"].append(dre.get("fora_ponta_kwh", 0.0))

            # Bandeira (caso conste em tarifas)
            faturas_data["Bandeira"].append(
                next((c.get("valor_total", 0.0) for c in extras if "bandeira" in c["descricao"].lower()), 0.0)
            )

            # DIC/IFC – simulamos com 0.0 se não constar
            faturas_data["DIC_IFC"].append(data_json.get("dic_ifc", 0.0))

            # Iluminação pública
            faturas_data["Iluminacao_Publica"].append(
                next((c.get("valor_total", 0.0) for c in extras if "iluminação pública" in c["descricao"].lower()), 0.0)
            )

            # Impostos: PIS, COFINS, ICMS
            impostos = data_json.get("impostos", [])
            pis = next((i.get("aliquota", 0.0)/100 for i in impostos if i.get("nome", "").upper() == "PIS"), 0.0)
            cofins = next((i.get("aliquota", 0.0)/100 for i in impostos if i.get("nome", "").upper() == "COFINS"), 0.0)
            icms = next((i.get("aliquota", 0.0)/100 for i in impostos if i.get("nome", "").upper() == "ICMS"), 0.0)

            faturas_data["PIS"].append(pis)
            faturas_data["COFINS"].append(cofins)
            faturas_data["ICMS"].append(icms)
            faturas_data["Fatura_total"].append(
                data_json.get("valores_totais", {}).get("valor_total_fatura", 0.0)
            )
        except Exception as e:
            import traceback
            traceback_str = traceback.format_exc()
            return jsonify({"error": f"Erro ao processar PDF {pdf_path}: {traceback_str}"}), 500

    # ✅ Este retorno deve estar fora do loop
    return jsonify(faturas_data)

@bp.route("/dados-fatura/teste", methods=["POST"])
def dados_fatura_teste():
    """
    Endpoint para testar e comparar a extração de dados de fatura via regex e LLM.

    Recebe o caminho de um arquivo PDF, extrai os dados usando ambos os métodos
    e retorna as diferenças encontradas, além dos resultados de cada método.

    Body da Requisição (JSON):
        {
          "pdf_path": "caminho/arquivo.pdf"
        }

    Respostas:
        200 OK: JSON com o status da comparação, diferenças e os dados
                extraídos por regex e LLM.
        400 Bad Request: JSON com mensagem de erro se o pdf_path estiver faltando.
        500 Internal Server Error: JSON com mensagem de erro se ocorrer
                                   um erro durante o processamento.
    """
    data     = request.get_json(force=True)
    pdf_path = data.get("pdf_path", "")
    if not pdf_path:
        return jsonify({"error": "pdf_path é obrigatório"}), 400

    try:
        # 1) Extrai via regex e via LLM
        dados_regex = extrair_dados_completos_da_fatura(pdf_path, via_regex=True)
        dados_llm   = extrair_dados_completos_da_fatura(pdf_path, via_regex=False)
        
        # 2) Calcula diferenças
        diff = dict_diff(dados_regex, dados_llm)

        return jsonify({
            "status": "OK" if not has_diff(diff) else "DIVERGENCIAS",
            "diff":  diff,
            "regex": dados_regex,
            "llm":   dados_llm,
        })
    except Exception as e:
        import traceback
        traceback_str = traceback.format_exc()
        return jsonify({"error": str(traceback_str)}), 500

@bp.route("/analisar-fatura", methods=["POST"])
def analisar_faturas():
    """
    Endpoint para analisar a eficiência energética e otimização de tarifas para faturas.

    Recebe dados de faturas (através de caminhos de PDFs), período,
    distribuidora e código de instalação. Realiza a análise de eficiência
    energética e as otimizações de tarifa verde e azul, e tenta gerar um relatório.

    Body da Requisição (JSON):
        {
          "data_inicio": "JAN-2023",
          "data_fim": "DEZ-2023",
          "codInstalacao": "codigo_da_instalacao",
          "periodo": "JAN-2024", # Período para buscar tarifas
          "distribuidora": "Nome da Distribuidora",
          "via_regex": true # Opcional, padrão é true
        }

    Respostas:
        200 OK: JSON com os resultados da análise de eficiência e otimização.
        400 Bad Request: JSON com mensagem de erro se parâmetros obrigatórios
                         estiverem faltando.

    """
    data = request.get_json()
    via_regex = data.get("via_regex", True)
    data_inicio = data.get("data_inicio")
    data_fim = data.get("data_fim")
    periodo = data.get("periodo")
    distribuidora = data.get("distribuidora")
    codinstalacao = data.get("codInstalacao")

    if not all([data_inicio, data_fim, codinstalacao, periodo, distribuidora]):
        return jsonify({"error": "Parâmetros obrigatórios: data_inicio, data_fim, CodInstalacao"}), 400

    dt1 = ref_to_date(data_inicio)
    dt2 = ref_to_date(data_fim)
    dt_ini, dt_fim = min(dt1, dt2), max(dt1, dt2)

    pasta_instalacao = os.path.join("/app/faturas_edp/", codinstalacao)

    if not os.path.exists(pasta_instalacao):
        return jsonify({"error": f"Pasta não encontrada para instalação {codinstalacao}"}), 404

    pdf_paths = []
    pdf_infos = []
    for nome_arquivo in os.listdir(pasta_instalacao):
        match = re.search(r'_(\w{3})-(\d{4})\.pdf$', nome_arquivo)
        if match:
            ref = f"{match.group(1)}-{match.group(2)}"
            dt_ref = ref_to_date(ref)
            if dt_ini <= dt_ref <= dt_fim:
                pdf_infos.append((dt_ref, os.path.join(pasta_instalacao, nome_arquivo)))

    # logging.info(f"PDFs encontrados: {pdf_infos}")
    pdf_infos.sort(key=itemgetter(0), reverse=True)
    pdf_paths = [path for _, path in pdf_infos]
    
    if not pdf_paths:
        return jsonify({"error": "Nenhuma fatura encontrada no intervalo informado"}), 404

    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": "chave-secreta-supersegura"
    }

    faturas_data = []
    for pdf_path in pdf_paths:
        try:
            # Chama o endpoint interno para obter os dados da fatura
            response = requests.post(SEGER_DADOS_FATURA_URL, json={"pdf_path": pdf_path, "via_regex": via_regex}, headers=headers)
            response.raise_for_status()
            fatura_json = response.json()
            # logging.info(f"Dados da fatura para {pdf_path}:\n{fatura_json}")
            faturas_data.append(fatura_json)
        except Exception as e:
            import traceback
            traceback_str = traceback.format_exc()
            logging.info(f"❌ HTTP Error - Status: {response.status_code} - Response: {response.text}")
            # Trata erros na chamada ao endpoint de dados da fatura
            return jsonify({"error": f"Erro ao processar PDF {pdf_path}: {traceback_str}"}), 500
        except json.JSONDecodeError:
            # Trata erros na decodificação do JSON da resposta
            return jsonify({"error": f"Erro ao decodificar JSON para {pdf_path}"}), 500


    # Chama a função de análise com os dados das faturas
    tarifas_url = f"http://localhost:5000/api/seger/tarifas?periodo={periodo}&distribuidora={distribuidora}&detalhe=N%C3%A3o%20se%20aplica"
    periodo_atualizado = "DEZ-2024"
    tarifas_url_atualizado = f"http://localhost:5000/api/seger/tarifas?periodo={periodo_atualizado}&distribuidora={distribuidora}&detalhe=N%C3%A3o%20se%20aplica"
    try:
        tarifas_response = requests.get(tarifas_url)
        tarifas_response.raise_for_status()
        tarifas_compactadas = tarifas_response.json()
        tarifas_compactadas = converter_tarifas_para_kwh(tarifas_compactadas)
        tarifa_ere = tarifas_compactadas["convencional pr\u00e9-pagamento"]["TEforaPonta"]
        tarifa_atualizado = requests.get(tarifas_url_atualizado)
        tarifas_compactadas_atualizado = tarifa_atualizado.json()
        tarifas_compactadas_atualizado = converter_tarifas_para_kwh(tarifas_compactadas_atualizado)
        tarifa_ere_atualizado = tarifas_compactadas_atualizado["convencional pr\u00e9-pagamento"]["TEforaPonta"]
        tarifa_azul = tarifas_compactadas_atualizado.get("azul", {})
        tarifa_verde = tarifas_compactadas_atualizado.get("verde", {})
        # logging.info(f"Tarifas originais: {tarifas_compactadas}")
        # logging.info(f"Tarifas atualizadas: {tarifas_compactadas_atualizado}")
        if not tarifa_azul or not tarifa_verde:
            return jsonify({"error": "Não foi possível obter as tarifas compactadas para as modalidades Azul e Verde."}), 500

        result_verde = opt_tarifa_verde(faturas_data, tarifa_verde, tarifa_ere_atualizado)
        result_azul = opt_tarifa_azul(faturas_data, tarifa_azul, tarifa_ere_atualizado)
        analise_resultado = analisar_eficiencia_energetica(faturas_data, tarifas_compactadas, tarifa_ere, tarifas_compactadas_atualizado, tarifa_ere_atualizado , result_verde["demanda_otima"], result_azul["demanda_p_otima"], result_azul["demanda_fp_otima"])
        
        relatorio_url=f"https://8000-idx-pylatex-seger-1742562415094.cluster-kc2r6y3mtba5mswcmol45orivs.cloudworkstations.dev/gerar-relatorio"
        headers = {
            "Content-Type": "application/json",
            "X-API-KEY": "chave-secreta-supersegura"
        }	
        response = requests.post(relatorio_url, json=analise_resultado, headers=headers)
        if response.status_code == 200:
            with open(f"/app/src/data/relatorio_uc_{codinstalacao}.pdf", "wb") as f:
                f.write(response.content)
            logging.info("✅ PDF salvo com sucesso: relatorio_gerado.pdf")
        else:
            logging.error(f"❌ Erro ao gerar relatório: {response.status_code} - {response.text}")

        result = {
            "result_verde": result_verde,
            "result_azul": result_azul
        }
        final_response = {
            "analise_eficiencia": analise_resultado,
            "resultado_otimizacao": result
        }
        return jsonify(final_response), 200
    except Exception as e:
        import traceback
        traceback_str = traceback.format_exc()
        # Trata erros na função de análise
        return jsonify({"error": f"Erro durante a análise de eficiência energética: {traceback_str}"}), 500

@bp.route("/tarifas", methods=["GET"])
def tarifas():
    """
    Endpoint para obter dados de tarifas de energia.

    Permite filtrar as tarifas por período, distribuidora, modalidade,
    subgrupo, classe e detalhe.

    Parâmetros da Query String:
        periodo (obrigatório): O período de referência das tarifas (ex: "JAN-2024").
        distribuidora (obrigatório): O nome da distribuidora.
        modalidade (opcional): A modalidade tarifária (ex: "VERDE", "AZUL").
        subgrupo (opcional): O subgrupo tarifário (ex: "A4").
        classe (opcional): A classe de consumo.
        detalhe (opcional): Nível de detalhe da tarifa.

    Respostas:
        200 OK: JSON contendo as tarifas filtradas e compactadas por modalidade.
        400 Bad Request: JSON com mensagem de erro se parâmetros obrigatórios
                         estiverem faltando.
    """
    periodo = request.args.get("periodo")
    distribuidora = request.args.get("distribuidora")
    modalidade = request.args.get("modalidade") # opcional
    subgrupo = request.args.get("subgrupo")      # opcional
    classe = request.args.get("classe")          # opcional
    detalhe = request.args.get("detalhe")        # opcional

    if not periodo or not distribuidora:
        return jsonify({"error": "Informe 'periodo' e 'distribuidora'"}), 400

    dados = get_tarifas_filtradas(periodo, distribuidora, modalidade, subgrupo, classe,detalhe)

    # Verifica se a função retornou erro
    if isinstance(dados, dict) and "error" in dados:
        return jsonify(dados), 500  # erro interno na filtragem

    if not dados:
        return jsonify({"error": "Nenhum dado encontrado para os filtros informados"}), 404

    try:
        tarifa = extrair_tarifa_compacta_por_modalidade(dados)
        return jsonify(tarifa)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Erro ao extrair tarifa compactada: {str(e)}"}), 500


@bp.route("/otimizacao", methods=["POST"])
def otimizar_faturas():
    """
    Endpoint para realizar a otimização de tarifas verde e azul com base em faturas.

    Recebe dados de faturas (através de caminhos de PDFs), data de início,
    data de fim e código de instalação. Realiza as otimizações de tarifa verde
    e azul e retorna os resultados.

    Body da Requisição (JSON):
        {
          "data_inicio": "JAN-2023",
          "data_fim": "DEZ-2023",
          "codInstalacao": "codigo_da_instalacao",
          "distribuidora": "Nome da Distribuidora" # Opcional, padrão "EDP ES"
        }

    Respostas:
        200 OK: JSON com os resultados das otimizações de tarifa verde e azul.
        400 Bad Request: JSON com mensagem de erro se parâmetros obrigatórios
                         estiverem faltando.

    """
    data = request.get_json()
    data_inicio = data.get("data_inicio")
    data_fim = data.get("data_fim")
    codinstalacao = data.get("codInstalacao")
    distribuidora = data.get("distribuidora","EDP ES")

    if not all([data_inicio, data_fim, codinstalacao]):
        return jsonify({"error": "Parâmetros obrigatórios: data_inicio, data_fim, codInstalacao"}), 400

    dt1 = ref_to_date(data_inicio)
    dt2 = ref_to_date(data_fim)
    dt_ini, dt_fim = min(dt1, dt2), max(dt1, dt2)

    pasta_instalacao = os.path.join("/app/faturas_edp/", codinstalacao)
    if not os.path.exists(pasta_instalacao):
        return jsonify({"error": f"Pasta não encontrada para instalação {codinstalacao}"}), 404

    pdf_paths = []
    for nome_arquivo in os.listdir(pasta_instalacao):
        match = re.search(r'_(\w{3})-(\d{4})\.pdf$', nome_arquivo)
        if match:
            ref = f"{match.group(1)}-{match.group(2)}"
            dt_ref = ref_to_date(ref)
            if dt_ini <= dt_ref <= dt_fim:
                pdf_paths.append(os.path.join(pasta_instalacao, nome_arquivo))

    if not pdf_paths:
        return jsonify({"error": "Nenhuma fatura encontrada no intervalo informado"}), 404

    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": "chave-secreta-supersegura"
    }
    if not pdf_paths:
        return jsonify({"error": "Nenhum caminho de PDF fornecido"}), 400

    faturas_data = []
    for pdf_path in pdf_paths:
        try:
            # Chama o endpoint interno para obter os dados da fatura
            response = requests.post(SEGER_DADOS_FATURA_URL, json={"pdf_path": pdf_path}, headers=headers)
            response.raise_for_status() # Levanta um erro para respostas de status ruins
            fatura_json = response.json()
            # logging.info(f"Dados da fatura para {pdf_path}:\n{fatura_json}")
            faturas_data.append(fatura_json)
        except requests.exceptions.RequestException as e:
            # Trata erros na chamada ao endpoint de dados da fatura
            return jsonify({"error": f"Erro ao processar PDF {pdf_path}: {e}"}), 500
        except json.JSONDecodeError:
            # Trata erros na decodificação do JSON da resposta
            return jsonify({"error": f"Erro ao decodificar JSON para {pdf_path}"}), 500


    # Chama a função de análise com os dados das faturas
    periodo = "JAN-2025"
    tarifas_url = f"http://localhost:5000/api/seger/tarifas?periodo={periodo}&distribuidora={distribuidora}"
    
    try:
        tarifas_response = requests.get(tarifas_url)
        tarifas_response.raise_for_status()
        tarifas_compactadas = tarifas_response.json()
        tarifas_compactadas = converter_tarifas_para_kwh(tarifas_compactadas)
        tarifa_ere = tarifas_compactadas["convencional pr\u00e9-pagamento"]["TEforaPonta"]
        tarifa_azul = tarifas_compactadas.get("azul", {})
        tarifa_verde = tarifas_compactadas.get("verde", {})
        
        if not tarifa_azul or not tarifa_verde:
            return jsonify({"error": "Não foi possível obter as tarifas compactadas para as modalidades Azul e Verde."}), 500

        result_verde = opt_tarifa_verde(faturas_data, tarifa_verde, tarifa_ere)
        result_azul = opt_tarifa_azul(faturas_data, tarifa_azul, tarifa_ere)
        
        result = {
            "result_verde": result_verde,
            "result_azul": result_azul
        }
       
        return jsonify(result), 200
    except Exception as e:
        # Trata erros na função de análise
        return jsonify({"error": f"Erro durante a análise de eficiência energética: {e}"}), 500

@bp.route("/calc-verde", methods=["POST"])
def calcular_fatura_verde():
    """
    Endpoint para calcular o custo da fatura com uma demanda específica na tarifa verde.

    Recebe dados de faturas (através de caminhos de PDFs), informações
    para buscar tarifas (período, distribuidora) e uma demanda para cálculo.

    Body da Requisição (JSON):
        {
          "data_inicio": "JAN-2023",
          "data_fim": "DEZ-2023",
          "codInstalacao": "codigo_da_instalacao",
          "periodo": "JAN-2024", # Período para buscar tarifas
          "distribuidora": "Nome da Distribuidora",
          "demanda": 100.0, # Demanda para cálculo na tarifa verde
          "via_regex": true # Opcional, padrão é true
        }

    Respostas:
        200 OK: JSON com o resultado do cálculo do custo na tarifa verde.
    """
    data = request.get_json()
    via_regex = data.get("via_regex", True)
    data_inicio = data.get("data_inicio")
    data_fim = data.get("data_fim")
    codinstalacao = data.get("codInstalacao")
    periodo = data.get("periodo")
    distribuidora = data.get("distribuidora")
    demanda = data.get("demanda")

    if not all([data_inicio, data_fim, codinstalacao, periodo]):
        return jsonify({"error": "Parâmetros obrigatórios: data_inicio, data_fim, CodInstalacao, periodo, distribuidora"}), 400

    dt1 = ref_to_date(data_inicio)
    dt2 = ref_to_date(data_fim)
    dt_ini, dt_fim = min(dt1, dt2), max(dt1, dt2)

    pasta_instalacao = os.path.join("/app/faturas_edp/", codinstalacao)

    if not os.path.exists(pasta_instalacao):
        return jsonify({"error": f"Pasta não encontrada para instalação {codinstalacao}"}), 404

    pdf_paths = []
    pdf_infos = []
    for nome_arquivo in os.listdir(pasta_instalacao):
        match = re.search(r'_(\w{3})-(\d{4})\.pdf$', nome_arquivo)
        if match:
            ref = f"{match.group(1)}-{match.group(2)}"
            dt_ref = ref_to_date(ref)
            if dt_ini <= dt_ref <= dt_fim:
                pdf_infos.append((dt_ref, os.path.join(pasta_instalacao, nome_arquivo)))

    # logging.info(f"PDFs encontrados: {pdf_infos}")
    pdf_infos.sort(key=itemgetter(0), reverse=True)
    pdf_paths = [path for _, path in pdf_infos]
    
    if not pdf_paths:
        return jsonify({"error": "Nenhuma fatura encontrada no intervalo informado"}), 404

    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": "chave-secreta-supersegura"
    }

    faturas_data = []
    for pdf_path in pdf_paths:
        try:
            # Chama o endpoint interno para obter os dados da fatura
            response = requests.post(SEGER_DADOS_FATURA_URL, json={"pdf_path": pdf_path, "via_regex": via_regex}, headers=headers)
            response.raise_for_status()
            fatura_json = response.json()
            # logging.info(f"Dados da fatura para {pdf_path}:\n{fatura_json}")
            faturas_data.append(fatura_json)
        except Exception as e:
            import traceback
            traceback_str = traceback.format_exc()
            logging.info(f"❌ HTTP Error - Status: {response.status_code} - Response: {response.text}")
            # Trata erros na chamada ao endpoint de dados da fatura
            return jsonify({"error": f"Erro ao processar PDF {pdf_path}: {traceback_str}"}), 500
        except json.JSONDecodeError:
            # Trata erros na decodificação do JSON da resposta
            return jsonify({"error": f"Erro ao decodificar JSON para {pdf_path}"}), 500


    # Chama a função de análise com os dados das faturas
    tarifas_url = f"http://localhost:5000/api/seger/tarifas?periodo={periodo}&distribuidora={distribuidora}&detalhe=N%C3%A3o%20se%20aplica"
    try:
        tarifas_response = requests.get(tarifas_url)
        tarifas_response.raise_for_status()
        tarifas_compactadas = tarifas_response.json()
        tarifas_compactadas = converter_tarifas_para_kwh(tarifas_compactadas)
        # logging.info(f"Tarifas:\n{tarifas_compactadas}")
        # logging.info(f"Dados da Fatura:\n{faturas_data}")
        tarifa_ere = tarifas_compactadas["convencional pr\u00e9-pagamento"]["TEforaPonta"]
        # logging.info(f"Tarifa ERE: {tarifa_ere}")
        calc_verde = calcular_tarifa_verde(faturas_data, tarifas_compactadas["verde"], tarifa_ere, demanda)
        result = {
            "result_verde": calc_verde,
        }
        return jsonify(result), 200
    except Exception as e:
        import traceback
        traceback_str = traceback.format_exc()
        # Trata erros na função de análise
        return jsonify({"error": f"Erro durante o calculo: {traceback_str}-{e}"}), 500 

@bp.route("/calc-azul", methods=["POST"])
def calcular_fatura_azul():
    """
    Endpoint para calcular o custo da fatura com uma demanda específica na tarifa azul.

    Recebe dados de faturas (através de caminhos de PDFs), informações
    para buscar tarifas (período, distribuidora) e uma demanda para cálculo.

    Body da Requisição (JSON):
        {
          "data_inicio": "JAN-2023",
          "data_fim": "DEZ-2023",
          "codInstalacao": "codigo_da_instalacao",
          "periodo": "JAN-2024", # Período para buscar tarifas
          "distribuidora": "Nome da Distribuidora",
          "demanda": {"ponta": 50.0, "fora_ponta": 100.0}, # Demanda para cálculo na tarifa azul (objeto com ponta e fora_ponta)
          "via_regex": true # Opcional, padrão é true
        }

    Respostas:
        200 OK: JSON com o resultado do cálculo do custo na tarifa azul.
    """
    data = request.get_json()
    via_regex = data.get("via_regex", True)
    data_inicio = data.get("data_inicio")
    data_fim = data.get("data_fim")
    codinstalacao = data.get("codInstalacao")
    periodo = data.get("periodo")
    distribuidora = data.get("distribuidora")
    demanda = data.get("demanda",None)

    if not all([data_inicio, data_fim, codinstalacao, periodo]):
        return jsonify({"error": "Parâmetros obrigatórios: data_inicio, data_fim, CodInstalacao, periodo, distribuidora"}), 400

    dt1 = ref_to_date(data_inicio)
    dt2 = ref_to_date(data_fim)
    dt_ini, dt_fim = min(dt1, dt2), max(dt1, dt2)

    pasta_instalacao = os.path.join("/app/faturas_edp/", codinstalacao)

    if not os.path.exists(pasta_instalacao):
        return jsonify({"error": f"Pasta não encontrada para instalação {codinstalacao}"}), 404

    pdf_paths = []
    pdf_infos = []
    for nome_arquivo in os.listdir(pasta_instalacao):
        match = re.search(r'_(\w{3})-(\d{4})\.pdf$', nome_arquivo)
        if match:
            ref = f"{match.group(1)}-{match.group(2)}"
            dt_ref = ref_to_date(ref)
            if dt_ini <= dt_ref <= dt_fim:
                pdf_infos.append((dt_ref, os.path.join(pasta_instalacao, nome_arquivo)))

    # logging.info(f"PDFs encontrados: {pdf_infos}")
    pdf_infos.sort(key=itemgetter(0), reverse=True)
    pdf_paths = [path for _, path in pdf_infos]
    
    if not pdf_paths:
        return jsonify({"error": "Nenhuma fatura encontrada no intervalo informado"}), 404

    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": "chave-secreta-supersegura"
    }

    faturas_data = []
    for pdf_path in pdf_paths:
        try:
            # Chama o endpoint interno para obter os dados da fatura
            response = requests.post(SEGER_DADOS_FATURA_URL, json={"pdf_path": pdf_path, "via_regex": via_regex}, headers=headers)
            response.raise_for_status()
            fatura_json = response.json()
            # logging.info(f"Dados da fatura para {pdf_path}:\n{fatura_json}")
            faturas_data.append(fatura_json)
        except Exception as e:
            import traceback
            traceback_str = traceback.format_exc()
            logging.info(f"❌ HTTP Error - Status: {response.status_code} - Response: {response.text}")
            # Trata erros na chamada ao endpoint de dados da fatura
            return jsonify({"error": f"Erro ao processar PDF {pdf_path}: {traceback_str}"}), 500
        except json.JSONDecodeError:
            # Trata erros na decodificação do JSON da resposta
            return jsonify({"error": f"Erro ao decodificar JSON para {pdf_path}"}), 500


    # Chama a função de análise com os dados das faturas
    tarifas_url = f"http://localhost:5000/api/seger/tarifas?periodo={periodo}&distribuidora={distribuidora}&detalhe=N%C3%A3o%20se%20aplica"
    try:
        tarifas_response = requests.get(tarifas_url)
        tarifas_response.raise_for_status()
        tarifas_compactadas = tarifas_response.json()
        tarifas_compactadas = converter_tarifas_para_kwh(tarifas_compactadas)
        # logging.info(f"Tarifas:\n{tarifas_compactadas}")
        # logging.info(f"Dados da Fatura:\n{faturas_data}")
        tarifa_ere = tarifas_compactadas["convencional pr\u00e9-pagamento"]["TEforaPonta"]
        # logging.info(f"Tarifa ERE: {tarifa_ere}")
        calc_azul = calcular_tarifa_azul(faturas_data, tarifas_compactadas["azul"], tarifa_ere, demanda)
        result = {
            "result_verde": calc_azul,
        }
        return jsonify(result), 200
    except Exception as e:
        # Trata erros na função de análise
        return jsonify({"error": f"Erro durante a análise de eficiência energética: {e}"}), 500

@bp.route("/relatorio/<cod_instalacao>", methods=["GET"])
def baixar_relatorio_por_cod(cod_instalacao):
    """
    Endpoint para baixar o relatório de análise de eficiência energética em PDF.

    Args:
        cod_instalacao: O código da instalação para a qual o relatório foi gerado.

    Respostas:
        200 OK: O arquivo PDF do relatório como anexo.

    """
    nome_arquivo = f"relatorio_uc_{cod_instalacao}.pdf"
    caminho_arquivo = os.path.join("/app/src/data", nome_arquivo)

    if os.path.exists(caminho_arquivo):
        return send_file(
            caminho_arquivo,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=nome_arquivo
        )
    else:
        return jsonify({"error": f"Relatório não encontrado para instalação {cod_instalacao}"}), 404
