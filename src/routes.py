# seger/routes.py
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

bp = Blueprint("seger", __name__, url_prefix="/api/seger")
SEGER_DADOS_FATURA_URL = "http://localhost:5000/api/seger/dados-fatura"

# Mapa de meses
MES_MAP = {
    "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4,
    "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8,
    "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12
}

def ref_to_date(ref: str) -> datetime:
    try:
        mes, ano = ref.upper().split("-")
        return datetime(int(ano), MES_MAP[mes], 1)
    except:
        return datetime.min

def converter_tarifas_para_kwh(tarifas_compactadas):
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
    # envia o PDF como anexo
    return send_file(pdf_path, mimetype="application/pdf", as_attachment=True)

@bp.route("/dados-fatura", methods=["POST"])
def dados_fatura():
    data     = request.get_json(force=True)
    pdf_path = data.get("pdf_path", "")
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

@bp.route("/dados-fatura/teste", methods=["POST"])
def dados_fatura_teste():
    """
    Corpo esperado:
    {
      "pdf_path": "<caminho/arquivo.pdf>"
    }
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

@bp.route("/analisar-fatura/teste", methods=["POST"])
def analisar_faturas_teste():
    """
    Endpoint para testar a análise de eficiência energética a partir de caminhos de PDFs.
    """
    data = request.get_json()
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
    logging.info(f"Pasta de instalações: {pasta_instalacao}")
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
    logging.info(f"PDFs encontrados: {pdf_paths}")

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
    periodo = "JUL-2021"
    distribuidora = "EDP ES"
    tarifas_url = f"http://localhost:5000/api/seger/tarifas?periodo={periodo}&distribuidora={distribuidora}"
    periodo_atualizado = "DEC-2024"
    tarifas_url_atualizado = f"http://localhost:5000/api/seger/tarifas?periodo={periodo_atualizado}&distribuidora={distribuidora}"
    try:
        tarifas_response = requests.get(tarifas_url)
        tarifas_response.raise_for_status()
        tarifas_compactadas = tarifas_response.json()
        tarifas_compactadas = converter_tarifas_para_kwh(tarifas_compactadas)
        tarifa_azul = tarifas_compactadas.get("azul", {})
        tarifa_verde = tarifas_compactadas.get("verde", {})
        tarifa_atualizado = requests.get(tarifas_url_atualizado)
        tarifas_compactadas_atualizado = tarifa_atualizado.json()
        tarifas_compactadas_atualizado = converter_tarifas_para_kwh(tarifas_compactadas_atualizado)
        # logging.info(f"Tarifas originais: {tarifas_compactadas}")
        # logging.info(f"Tarifas atualizadas: {tarifas_compactadas_atualizado}")
        if not tarifa_azul or not tarifa_verde:
            return jsonify({"error": "Não foi possível obter as tarifas compactadas para as modalidades Azul e Verde."}), 500


        # analise_resultado = calcular_tarifa_azul(faturas_data[0],tarifa_azul,173,463)
        # analise_resultado = calcular_tarifa_verde(faturas_data,tarifa_verde, 570)
        result_verde = opt_tarifa_verde(faturas_data, tarifa_verde)
        result_azul = opt_tarifa_azul(faturas_data, tarifa_azul)
        analise_resultado = analisar_eficiencia_energetica(faturas_data, tarifas_compactadas, tarifas_compactadas_atualizado, result_verde["demanda_otima"], result_azul["demanda_p_otima"], result_azul["demanda_fp_otima"])
        
        relatorio_url=f"https://8000-idx-pylatex-seger-1742562415094.cluster-kc2r6y3mtba5mswcmol45orivs.cloudworkstations.dev/gerar-relatorio"
        headers = {
            "Content-Type": "application/json",
            "X-API-KEY": "chave-secreta-supersegura"
        }	
        response = requests.post(relatorio_url, json=analise_resultado, headers=headers)
        if response.status_code == 200:
            with open("/app/src/data/relatorio_gerado.pdf", "wb") as f:
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
    periodo = request.args.get("periodo")
    distribuidora = request.args.get("distribuidora")
    modalidade = request.args.get("modalidade")  # opcional
    subgrupo = request.args.get("subgrupo") #opcional

    if not periodo or not distribuidora:
        return jsonify({"error": "Informe 'periodo' e 'distribuidora'"}), 400

    dados = get_tarifas_filtradas(periodo, distribuidora, modalidade, subgrupo)
    if not dados:
        return jsonify({"error": "Nenhum dado encontrado para os filtros informados"}), 404
    tarifa = extrair_tarifa_compacta_por_modalidade(dados)
    return jsonify(tarifa)

@bp.route("/otimizacao/teste", methods=["POST"])
def otimizar_faturas_teste():
    """
    Endpoint para testar a análise de eficiência energética a partir de caminhos de PDFs.
    """
    data = request.get_json()
    pdf_paths = data.get("pdf_paths", [])
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
    periodo = "JUL-2021"
    distribuidora = "EDP ES"
    tarifas_url = f"http://localhost:5000/api/seger/tarifas?periodo={periodo}&distribuidora={distribuidora}"
    
    try:
        tarifas_response = requests.get(tarifas_url)
        tarifas_response.raise_for_status()
        tarifas_compactadas = tarifas_response.json()
        tarifas_compactadas = converter_tarifas_para_kwh(tarifas_compactadas)
        tarifa_azul = tarifas_compactadas.get("azul", {})
        tarifa_verde = tarifas_compactadas.get("verde", {})
        
        if not tarifa_azul or not tarifa_verde:
            return jsonify({"error": "Não foi possível obter as tarifas compactadas para as modalidades Azul e Verde."}), 500

        result_verde = opt_tarifa_verde(faturas_data, tarifa_verde)
        result_azul = opt_tarifa_azul(faturas_data, tarifa_azul)
        
        result = {
            "result_verde": result_verde,
            "result_azul": result_azul
        }
       
        return jsonify(result), 200
    except Exception as e:
        # Trata erros na função de análise
        return jsonify({"error": f"Erro durante a análise de eficiência energética: {e}"}), 500