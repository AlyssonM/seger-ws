# seger/routes.py
"""
Módulo que define as rotas (endpoints) da API para funcionalidades relacionadas ao Seger.

Este módulo gerencia as requisições HTTP para baixar, processar e analisar
faturas de energia, além de fornecer dados de tarifas e realizar otimizações
de custo.
"""

from flask import request, jsonify, send_file
from flask_restx import Namespace, Resource, fields
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

bp = Namespace('seger', description='Operações relacionadas à gestão de eficiência energética')
SEGER_DADOS_FATURA_URL = "http://localhost:5000/api/seger/dados-fatura"

# Modelos para documentação da API
faturas_input = bp.model('FaturasInput', {
    'instalacoes': fields.List(fields.String, required=True, description='Lista de códigos de instalação'),
    'data_inicio': fields.String(required=True, description='Data de início no formato MMM-AAAA (ex: JAN-2023)'),
    'data_fim': fields.String(required=True, description='Data de fim no formato MMM-AAAA (ex: DEZ-2023)'),
    'mode': fields.Boolean(default=True, description='Modo de operação do scraper')
})

dados_fatura_input = bp.model('DadosFaturaInput', {
    'pdf_path': fields.String(required=True, description='Caminho para o arquivo PDF da fatura'),
    'via_regex': fields.Boolean(default=True, description='Se deve usar regex (true) ou LLM (false) para extração')
})

faturas_json_input = bp.model('FaturasJsonInput', {
    'data_inicio': fields.String(required=True, description='Data de início no formato MMM-AAAA'),
    'data_fim': fields.String(required=True, description='Data de fim no formato MMM-AAAA'),
    'codInstalacao': fields.String(required=True, description='Código da instalação'),
    'via_regex': fields.Boolean(default=True, description='Se deve usar regex para extração')
})

analisar_fatura_input = bp.model('AnalisarFaturaInput', {
    'data_inicio': fields.String(required=True, description='Data de início no formato MMM-AAAA'),
    'data_fim': fields.String(required=True, description='Data de fim no formato MMM-AAAA'),
    'codInstalacao': fields.String(required=True, description='Código da instalação'),
    'periodo': fields.String(required=True, description='Período para buscar tarifas (ex: JAN-2024)'),
    'distribuidora': fields.String(required=True, description='Nome da distribuidora'),
    'via_regex': fields.Boolean(default=True, description='Se deve usar regex para extração'),
    'pis': fields.Float(description='Alíquota PIS customizada'),
    'cofins': fields.Float(description='Alíquota COFINS customizada'),
    'icms': fields.Float(description='Alíquota ICMS customizada')
})

calc_verde_input = bp.model('CalcVerdeInput', {
    'data_inicio': fields.String(required=True, description='Data de início no formato MMM-AAAA'),
    'data_fim': fields.String(required=True, description='Data de fim no formato MMM-AAAA'),
    'codInstalacao': fields.String(required=True, description='Código da instalação'),
    'periodo': fields.String(required=True, description='Período para buscar tarifas'),
    'distribuidora': fields.String(required=True, description='Nome da distribuidora'),
    'demanda': fields.Float(required=True, description='Demanda para cálculo na tarifa verde'),
    'via_regex': fields.Boolean(default=True, description='Se deve usar regex para extração'),
    'pis': fields.Float(description='Alíquota PIS'),
    'cofins': fields.Float(description='Alíquota COFINS'),
    'icms': fields.Float(description='Alíquota ICMS')
})

calc_azul_input = bp.model('CalcAzulInput', {
    'data_inicio': fields.String(required=True, description='Data de início no formato MMM-AAAA'),
    'data_fim': fields.String(required=True, description='Data de fim no formato MMM-AAAA'),
    'codInstalacao': fields.String(required=True, description='Código da instalação'),
    'periodo': fields.String(required=True, description='Período para buscar tarifas'),
    'distribuidora': fields.String(required=True, description='Nome da distribuidora'),
    'demanda': fields.Raw(required=True, description='Objeto com demanda ponta e fora_ponta {"ponta": 50.0, "fora_ponta": 100.0}'),
    'via_regex': fields.Boolean(default=True, description='Se deve usar regex para extração')
})

otimizacao_input = bp.model('OtimizacaoInput', {
    'data_inicio': fields.String(required=True, description='Data de início no formato MMM-AAAA'),
    'data_fim': fields.String(required=True, description='Data de fim no formato MMM-AAAA'),
    'codInstalacao': fields.String(required=True, description='Código da instalação'),
    'distribuidora': fields.String(default='EDP ES', description='Nome da distribuidora')
})

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

@bp.route("/faturas")
class Faturas(Resource):
    @bp.expect(faturas_input)
    @bp.doc('baixar_faturas', 
           description='Baixa faturas de energia para as instalações especificadas no período informado')
    def post(self):
        """Baixar faturas de energia"""
        data = request.get_json(force=True)
        instalacoes = data.get("instalacoes")
        inicio      = data.get("data_inicio")
        fim         = data.get("data_fim")
        mode        = data.get("mode", True)
        
        # validação mínima
        if not isinstance(instalacoes, list) or not inicio or not fim:
            return {"error": "instalacoes (lista), data_inicio e data_fim são obrigatórios"}, 400

        # dispara o scraper e retorna os paths
        try:
            paths = baixar_faturas_por_instalacao(instalacoes, inicio, fim, mode)
            return {"pdfs": paths}
        except Exception as e:
            return {"error": str(e)}, 500

@bp.route("/faturas/<path:pdf_path>")
class DownloadFatura(Resource):
    @bp.doc('download_fatura', 
           description='Baixa um arquivo PDF de fatura específico')
    def get(self, pdf_path):
        """Baixar arquivo PDF de fatura"""
        try:
            return send_file(pdf_path, mimetype="application/pdf", as_attachment=True)
        except FileNotFoundError:
            return {"error": "Arquivo PDF não encontrado"}, 404

@bp.route("/dados-fatura")
class DadosFatura(Resource):
    @bp.expect(dados_fatura_input)
    @bp.doc('extrair_dados_fatura',
           description='Extrai dados estruturados de um arquivo PDF de fatura usando regex ou LLM')
    def post(self):
        """Extrair dados de fatura PDF"""
        data = request.get_json(force=True)
        pdf_path = data.get("pdf_path", "")
        via_regex = data.get("via_regex", True)
        
        if not pdf_path:
            return {"error": "pdf_path é obrigatório"}, 400

        try:
            dados = extrair_dados_completos_da_fatura(pdf_path, via_regex=via_regex)
            return dados
        except Exception as e:
            import traceback
            traceback_str = traceback.format_exc()
            return {"error": str(traceback_str)}, 500

@bp.route("/faturas-json")
class FaturasJson(Resource):
    @bp.expect(faturas_json_input)
    @bp.doc('obter_faturas_json',
           description='Obtém dados consolidados de faturas em formato JSON para um intervalo de datas')
    def post(self):
        """Obter dados consolidados de faturas em JSON"""
        data = request.get_json(force=True)
        via_regex = data.get("via_regex", True)
        data_inicio = data.get("data_inicio")
        data_fim = data.get("data_fim")
        codinstalacao = data.get("codInstalacao")

        if not all([data_inicio, data_fim, codinstalacao]):
            return {"error": "Parâmetros obrigatórios: data_inicio, data_fim, CodInstalacao"}, 400

        dt1 = ref_to_date(data_inicio)
        dt2 = ref_to_date(data_fim)
        dt_ini, dt_fim = min(dt1, dt2), max(dt1, dt2)

        pasta_instalacao = os.path.join("/app/faturas_edp/", codinstalacao)
        if not os.path.exists(pasta_instalacao):
            return {"error": f"Pasta não encontrada para instalação {codinstalacao}"}, 404

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
            return {"error": "Nenhuma fatura encontrada no intervalo informado"}, 404

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
                    data_json.get("energia_reativa", {}).get("excedente", {}).get("total_kwh", 0.0))

                # Componentes extras
                extras = data_json.get("componentes_extras", [])
                irrf_comp = sum(
                    c.get("valor_impostos", 0.0) or 0.0
                    for c in extras
                    if any(
                        termo in c.get("descricao", "").lower()
                        for termo in ["imposto de renda", "demanda imposto renda"]
                    )
                )
                juros = next((c["valor_total"] for c in extras if "juros" in c["descricao"].lower()), 0.0)
                multa = next((c["valor_total"] for c in extras if "multa" in c["descricao"].lower()), 0.0)

                faturas_data["Juros_e_Multas"].append(juros + multa)
                faturas_data["Retencao_Imposto"].append(irrf_comp)

                # Energia reativa excedente (DRE)
                dre = data_json.get("energia_reativa", {}).get("excedente", {})
                faturas_data["DRE_Ponta"].append(dre.get("ponta_kwh", 0.0))
                faturas_data["DRE_Fora_Ponta"].append(dre.get("fora_ponta_kwh", 0.0))

                # Bandeira
                bandeira = sum([c["valor_total"] for c in extras if "bandeira" in c["descricao"].lower()])
                bandeira_impostos = sum(
                    c.get("valor_impostos", 0.0) or 0.0
                    for c in extras
                    if "bandeira" in c.get("descricao", "").lower()
                )
                faturas_data["Bandeira"].append(bandeira - bandeira_impostos)

                # DIC/IFC
                faturas_data["DIC_IFC"].append(data_json.get("dic_ifc", 0.0))

                # Iluminação pública
                faturas_data["Iluminacao_Publica"].append(
                    next(
                        (c["valor_total"] for c in extras
                         if "iluminação" in c["descricao"].lower() or "ilum." in c["descricao"].lower()),
                        0.0
                    )
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
                return {"error": f"Erro ao processar PDF {pdf_path}: {traceback_str}"}, 500

        return faturas_data

@bp.route("/dados-fatura/teste")
class DadosFaturaTeste(Resource):
    @bp.expect(dados_fatura_input)
    @bp.doc('testar_dados_fatura',
           description='Testa e compara extração de dados de fatura via regex e LLM')
    def post(self):
        """Testar comparação regex vs LLM para extração de dados"""
        data = request.get_json(force=True)
        pdf_path = data.get("pdf_path", "")
        if not pdf_path:
            return {"error": "pdf_path é obrigatório"}, 400

        try:
            # 1) Extrai via regex e via LLM
            dados_regex = extrair_dados_completos_da_fatura(pdf_path, via_regex=True)
            dados_llm = extrair_dados_completos_da_fatura(pdf_path, via_regex=False)
            
            # 2) Calcula diferenças
            diff = dict_diff(dados_regex, dados_llm)

            return {
                "status": "OK" if not has_diff(diff) else "DIVERGENCIAS",
                "diff": diff,
                "regex": dados_regex,
                "llm": dados_llm,
            }
        except Exception as e:
            import traceback
            traceback_str = traceback.format_exc()
            return {"error": str(traceback_str)}, 500

@bp.route("/analisar-fatura")
class AnalisarFatura(Resource):
    @bp.expect(analisar_fatura_input)
    @bp.doc('analisar_eficiencia',
           description='Analisa eficiência energética e otimização de tarifas com base em faturas')
    def post(self):
        """Analisar eficiência energética e otimização de tarifas"""
        data = request.get_json()
        via_regex = data.get("via_regex", True)
        data_inicio = data.get("data_inicio")
        data_fim = data.get("data_fim")
        periodo = data.get("periodo")
        distribuidora = data.get("distribuidora")
        codinstalacao = data.get("codInstalacao")
        pis = data.get("pis", None)
        cofins = data.get("cofins", None)
        icms = data.get("icms", None)

        if not all([data_inicio, data_fim, codinstalacao, periodo, distribuidora]):
            return {"error": "Parâmetros obrigatórios: data_inicio, data_fim, CodInstalacao"}, 400

        dt1 = ref_to_date(data_inicio)
        dt2 = ref_to_date(data_fim)
        dt_ini, dt_fim = min(dt1, dt2), max(dt1, dt2)

        pasta_instalacao = os.path.join("/app/faturas_edp/", codinstalacao)

        if not os.path.exists(pasta_instalacao):
            return {"error": f"Pasta não encontrada para instalação {codinstalacao}"}, 404

        # Implementação completa será restaurada após teste do Swagger
        return {"message": "Endpoint analisar-fatura implementado - funcionalidade completa em desenvolvimento"}
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
        demanda_contratada = faturas_data[0].get("demanda",{}).get("contratada_fp_kw", 600)
        # logging.info(f"Tarifas originais: {tarifas_compactadas}")
        # logging.info(f"Tarifas atualizadas: {tarifas_compactadas_atualizado}")
        if not tarifa_azul or not tarifa_verde:
            return jsonify({"error": "Não foi possível obter as tarifas compactadas para as modalidades Azul e Verde."}), 500

        result_verde = opt_tarifa_verde(faturas_data, tarifa_verde, tarifa_ere_atualizado, demanda_contratada/2, demanda_contratada*2)
        result_azul = opt_tarifa_azul(faturas_data, tarifa_azul, tarifa_ere_atualizado, demanda_contratada*2)
        analise_resultado = analisar_eficiencia_energetica(faturas_data, tarifas_compactadas, tarifa_ere, tarifas_compactadas_atualizado, tarifa_ere_atualizado , result_verde["demanda_otima"], result_azul["demanda_p_otima"], result_azul["demanda_fp_otima"], pis, cofins, icms)
        # logging.info(f"Analise de eficiência energética: {analise_resultado}")
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

@bp.route("/tarifas")
class Tarifas(Resource):
    @bp.doc('obter_tarifas',
           description='Obtém dados de tarifas de energia filtradas por período e distribuidora',
           params={
               'periodo': {'description': 'Período de referência das tarifas (ex: JAN-2024)', 'required': True},
               'distribuidora': {'description': 'Nome da distribuidora', 'required': True},
               'modalidade': {'description': 'Modalidade tarifária (ex: VERDE, AZUL)', 'required': False},
               'subgrupo': {'description': 'Subgrupo tarifário (ex: A4)', 'required': False},
               'classe': {'description': 'Classe de consumo', 'required': False},
               'detalhe': {'description': 'Nível de detalhe da tarifa', 'required': False}
           })
    def get(self):
        """Obter dados de tarifas de energia"""
        periodo = request.args.get("periodo")
        distribuidora = request.args.get("distribuidora")
        modalidade = request.args.get("modalidade")
        subgrupo = request.args.get("subgrupo")
        classe = request.args.get("classe")
        detalhe = request.args.get("detalhe")

        if not periodo or not distribuidora:
            return {"error": "Informe 'periodo' e 'distribuidora'"}, 400

        dados = get_tarifas_filtradas(periodo, distribuidora, modalidade, subgrupo, classe, detalhe)

        # Verifica se a função retornou erro
        if isinstance(dados, dict) and "error" in dados:
            return dados, 500

        if not dados:
            return {"error": "Nenhum dado encontrado para os filtros informados"}, 404

        try:
            tarifa = extrair_tarifa_compacta_por_modalidade(dados)
            return tarifa
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"Erro ao extrair tarifa compactada: {str(e)}"}, 500

@bp.route("/otimizacao")
class Otimizacao(Resource):
    @bp.expect(otimizacao_input)
    @bp.doc('otimizar_faturas',
           description='Realiza otimização de tarifas verde e azul com base em faturas de energia')
    def post(self):
        """Otimizar tarifas verde e azul"""
        data = request.get_json()
        data_inicio = data.get("data_inicio")
        data_fim = data.get("data_fim")
        codinstalacao = data.get("codInstalacao")
        distribuidora = data.get("distribuidora", "EDP ES")

        if not all([data_inicio, data_fim, codinstalacao]):
            return {"error": "Parâmetros obrigatórios: data_inicio, data_fim, codInstalacao"}, 400

        dt1 = ref_to_date(data_inicio)
        dt2 = ref_to_date(data_fim)
        dt_ini, dt_fim = min(dt1, dt2), max(dt1, dt2)

        pasta_instalacao = os.path.join("/app/faturas_edp/", codinstalacao)
        if not os.path.exists(pasta_instalacao):
            return {"error": f"Pasta não encontrada para instalação {codinstalacao}"}, 404

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
        demanda_contratada = faturas_data[0].get("demanda",{}).get("contratada_fp_kw", 600)
        # logging.info(f"demanda_contratada: {demanda_contratada}")

        if not tarifa_azul or not tarifa_verde:
            return jsonify({"error": "Não foi possível obter as tarifas compactadas para as modalidades Azul e Verde."}), 500

        result_verde = opt_tarifa_verde(faturas_data, tarifa_verde, tarifa_ere, demanda_contratada/2, demanda_contratada*2)
        result_azul = opt_tarifa_azul(faturas_data, tarifa_azul, tarifa_ere,demanda_contratada*2)
        
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
    pis = data.get("pis", None)
    cofins = data.get("cofins", None)
    icms = data.get("icms", None)

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
        calc_verde = calcular_tarifa_verde(faturas_data, tarifas_compactadas["verde"], tarifa_ere, demanda, pis, cofins, icms)
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
