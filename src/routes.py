# seger/routes.py
"""
Módulo que define as rotas (endpoints) da API para funcionalidades relacionadas ao Seger.

Este módulo gerencia as requisições HTTP para baixar, processar e analisar
faturas de energia, além de fornecer dados de tarifas e realizar otimizações
de custo.
"""

from flask import current_app, request, jsonify, send_file
from flask_restx import Namespace, Resource, fields
from src.scraper import baixar_faturas_por_instalacao
from src.parser import extrair_dados_completos_da_fatura
from src.utils.analise import analisar_tarifas_completo
from src.utils.dict_diff import dict_diff, has_diff
from src.utils.tarifas import get_tarifas_filtradas
from src.utils.tarifas import calcular_tarifa_verde, calcular_tarifa_azul
from src.utils.tarifas import extrair_tarifa_compacta_por_modalidade
from src.utils.invoice_locator import get_invoice_locator
from src.utils.fatura_cache import get_cache_instance

def ordenar_faturas_mensais_cronologicamente(faturas_mensais):
    """Ordena faturas mensais cronologicamente por mês/ano"""
    def _parse_mes_ref(item):
        """Converte 'MM/YYYY' para tuple (ano, mês) para ordenação"""
        try:
            mes_ref = item.get("mes", "")
            if "/" in mes_ref:
                mes, ano = mes_ref.split("/")
                return (int(ano), int(mes))
            else:
                return (9999, 99)  # Coloca datas inválidas no final
        except:
            return (9999, 99)
    
    if isinstance(faturas_mensais, list):
        faturas_mensais.sort(key=_parse_mes_ref)
    
    return faturas_mensais
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

otimizacao_input = bp.model('OtimizacaoInput', {
    'data_inicio': fields.String(required=True, description='Data de início no formato MMM-AAAA'),
    'data_fim': fields.String(required=True, description='Data de fim no formato MMM-AAAA'),
    'codInstalacao': fields.String(required=True, description='Código da instalação'),
    'distribuidora': fields.String(default='EDP ES', description='Nome da distribuidora'),
    'pis': fields.Float(description='Alíquota PIS customizada (%)'),
    'cofins': fields.Float(description='Alíquota COFINS customizada (%)'),
    'icms': fields.Float(description='Alíquota ICMS customizada (%)')
})

otimizacao_verde_input = bp.model('OtimizacaoVerdeInput', {
    'data_inicio': fields.String(required=True, description='Data de início no formato MMM-AAAA'),
    'data_fim': fields.String(required=True, description='Data de fim no formato MMM-AAAA'),
    'codInstalacao': fields.String(required=True, description='Código da instalação'),
    'distribuidora': fields.String(default='EDP ES', description='Nome da distribuidora'),
    'pis': fields.Float(description='Alíquota PIS customizada (%)'),
    'cofins': fields.Float(description='Alíquota COFINS customizada (%)'),
    'icms': fields.Float(description='Alíquota ICMS customizada (%)')
})

otimizacao_azul_input = bp.model('OtimizacaoAzulInput', {
    'data_inicio': fields.String(required=True, description='Data de início no formato MMM-AAAA'),
    'data_fim': fields.String(required=True, description='Data de fim no formato MMM-AAAA'),
    'codInstalacao': fields.String(required=True, description='Código da instalação'),
    'distribuidora': fields.String(default='EDP ES', description='Nome da distribuidora'),
    'pis': fields.Float(description='Alíquota PIS customizada (%)'),
    'cofins': fields.Float(description='Alíquota COFINS customizada (%)'),
    'icms': fields.Float(description='Alíquota ICMS customizada (%)')
})

calc_verde_input = bp.model('CalcVerdeInput', {
    'data_inicio': fields.String(required=True, description='Data de início no formato MMM-AAAA'),
    'data_fim': fields.String(required=True, description='Data de fim no formato MMM-AAAA'),
    'codInstalacao': fields.String(required=True, description='Código da instalação'),
    'periodo_tarifas': fields.String(required=True, description='Período das tarifas no formato MMM-AAAA'),
    'distribuidora': fields.String(default='EDP ES', description='Nome da distribuidora'),
    'demanda_contratada': fields.Float(description='Demanda contratada em kW (opcional)'),
    'pis': fields.Float(description='Alíquota PIS customizada (%)'),
    'cofins': fields.Float(description='Alíquota COFINS customizada (%)'),
    'icms': fields.Float(description='Alíquota ICMS customizada (%)'),
    'via_regex': fields.Boolean(default=True, description='Se deve usar regex para extração')
})

calc_azul_input = bp.model('CalcAzulInput', {
    'data_inicio': fields.String(required=True, description='Data de início no formato MMM-AAAA'),
    'data_fim': fields.String(required=True, description='Data de fim no formato MMM-AAAA'),
    'codInstalacao': fields.String(required=True, description='Código da instalação'),
    'periodo_tarifas': fields.String(required=True, description='Período das tarifas no formato MMM-AAAA'),
    'distribuidora': fields.String(default='EDP ES', description='Nome da distribuidora'),
    'demanda_ponta': fields.Float(description='Demanda contratada ponta em kW (opcional)'),
    'demanda_fora_ponta': fields.Float(description='Demanda contratada fora ponta em kW (opcional)'),
    'via_regex': fields.Boolean(default=True, description='Se deve usar regex para extração')
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
    """
    try:
        mes, ano = ref.upper().split("-")
        return datetime(int(ano), MES_MAP[mes], 1)
    except:
        return datetime.min

def converter_tarifas_para_kwh(tarifas_compactadas):
    """
    Converte valores de tarifas de MWh para kWh.
    """
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


def buscar_arquivos_fatura_com_fallback(codinstalacao: str, data_inicio: str = None, data_fim: str = None):
    """
    Busca arquivos de faturas usando sistema de fallback (local + Google Drive)
    
    Returns:
        Lista de dicionários com informações dos arquivos e suas fontes
    """
    try:
        locator = get_invoice_locator()
        arquivos_info = locator.find_invoice_files(codinstalacao, data_inicio, data_fim)
        
        # Log da fonte dos arquivos para debug
        fontes = {}
        for arquivo in arquivos_info:
            fonte = arquivo['fonte']
            fontes[fonte] = fontes.get(fonte, 0) + 1
        
        current_app.logger.info(f"Arquivos encontrados por fonte: {fontes}")
        
        return arquivos_info
    except Exception as e:
        current_app.logger.error(f"Erro na busca com fallback: {str(e)}")
        # Fallback para busca local tradicional
        import glob
        pasta_instalacao = os.path.join("faturas_edp", codinstalacao)
        padrao_arquivos = os.path.join(pasta_instalacao, "*.pdf")
        arquivos_pdf = glob.glob(padrao_arquivos)
        
        dt_ini, dt_fim = None, None
        if data_inicio and data_fim:
            dt_ini = ref_to_date(data_inicio)
            dt_fim = ref_to_date(data_fim)
            if dt_ini > dt_fim:
                dt_ini, dt_fim = dt_fim, dt_ini
        
        arquivos_info = []
        for arquivo in arquivos_pdf:
            nome_arquivo = os.path.basename(arquivo)
            ref = None
            if "_" in nome_arquivo:
                ref = nome_arquivo.split("_")[-1].replace(".pdf", "")
                if dt_ini and dt_fim:
                    ref_dt = ref_to_date(ref)
                    if not (dt_ini <= ref_dt <= dt_fim):
                        continue
            
            arquivos_info.append({
                'arquivo': nome_arquivo,
                'caminho_completo': arquivo,
                'referencia': ref,
                'fonte': 'local',
                'drive_file_id': None
            })
        
        return arquivos_info


def obter_caminho_arquivo_fatura(arquivo_info):
    """
    Obtém caminho do arquivo de fatura, baixando do Google Drive se necessário
    
    Returns:
        Caminho do arquivo local ou None se erro
    """
    try:
        if arquivo_info['fonte'] == 'local':
            return arquivo_info['caminho_completo']
        
        # Arquivo do Google Drive - precisa baixar
        locator = get_invoice_locator()
        return locator.get_file_path(arquivo_info)
        
    except Exception as e:
        current_app.logger.error(f"Erro ao obter caminho do arquivo: {str(e)}")
        return None


def processar_faturas_com_fallback(codinstalacao: str, data_inicio: str, data_fim: str, via_regex: bool = True):
    """
    Função auxiliar para processar faturas usando fallback, retornando dados extraídos
    
    Returns:
        tuple: (dados_faturas, info_processamento)
    """
    arquivos_info = buscar_arquivos_fatura_com_fallback(codinstalacao, data_inicio, data_fim)
    
    if not arquivos_info:
        return [], {"error": f"Nenhuma fatura encontrada para instalação {codinstalacao}"}
    
    dados_faturas = []
    arquivos_processados = 0
    arquivos_com_erro = 0
    fontes_utilizadas = {}
    
    for arquivo_info in arquivos_info:
        nome_arquivo = arquivo_info['arquivo']
        fonte = arquivo_info['fonte']
        
        # Obtém caminho do arquivo
        caminho_arquivo = obter_caminho_arquivo_fatura(arquivo_info)
        
        if not caminho_arquivo:
            current_app.logger.warning(f"Não foi possível obter arquivo {nome_arquivo} da fonte {fonte}")
            arquivos_com_erro += 1
            continue
        
        # Extrai dados da fatura
        try:
            dados_fatura = extrair_dados_completos_da_fatura(
                caminho_arquivo, 
                via_regex, 
                codinstalacao=codinstalacao,
                use_cache=True
            )
            if "error" not in dados_fatura:
                dados_faturas.append(dados_fatura)
                arquivos_processados += 1
                fontes_utilizadas[fonte] = fontes_utilizadas.get(fonte, 0) + 1
            else:
                current_app.logger.warning(f"Erro ao extrair dados de {nome_arquivo}: {dados_fatura.get('error', 'Erro desconhecido')}")
                arquivos_com_erro += 1
        except Exception as e:
            current_app.logger.error(f"Erro ao processar arquivo {nome_arquivo}: {str(e)}")
            arquivos_com_erro += 1
    
    info_processamento = {
        "total_arquivos_encontrados": len(arquivos_info),
        "arquivos_processados": arquivos_processados,
        "arquivos_com_erro": arquivos_com_erro,
        "fontes_utilizadas": fontes_utilizadas
    }
    
    if not dados_faturas:
        info_processamento["error"] = "Nenhuma fatura válida encontrada no período"
    
    return dados_faturas, info_processamento

@bp.route("/faturas")
class Faturas(Resource):
    @bp.expect(faturas_input)
    @bp.doc('baixar_faturas', 
           description='Baixa faturas de energia para as instalações especificadas no período informado')
    def post(self):
        """Baixar faturas de energia"""
        data = request.get_json(force=True)
        instalacoes = data.get("instalacoes")
        inicio = data.get("data_inicio")
        fim = data.get("data_fim")
        mode = data.get("mode", True)
        
        current_app.logger.info(f'Solicitação para baixar faturas: {instalacoes}')
        if not isinstance(instalacoes, list) or not inicio or not fim:
            return {"error": "instalacoes (lista), data_inicio e data_fim são obrigatórios"}, 400

        try:
            # Chama a função real de scraping
            caminhos_salvos = baixar_faturas_por_instalacao(instalacoes, inicio, fim, mode)
            return {
                "message": "Faturas baixadas com sucesso",
                "instalacoes_processadas": instalacoes,
                "periodo": f"{inicio} a {fim}",
                "arquivos_salvos": caminhos_salvos,
                "total_arquivos": len(caminhos_salvos)
            }
        except Exception as e:
            return {"error": f"Erro ao baixar faturas: {str(e)}"}, 500

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
            # Chama a função real de extração de dados
            dados_extraidos = extrair_dados_completos_da_fatura(pdf_path, via_regex)
            return {
                "message": "Dados extraídos com sucesso",
                "pdf_path": pdf_path,
                "metodo_extracao": "regex" if via_regex else "llm",
                "dados": dados_extraidos
            }
        except FileNotFoundError:
            return {"error": "Arquivo PDF não encontrado"}, 404
        except Exception as e:
            return {"error": f"Erro ao extrair dados: {str(e)}"}, 500

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

        current_app.logger.info(f'Solicitação para dados json de faturas da instalação: {codinstalacao}')
        if not all([data_inicio, data_fim, codinstalacao]):
            return {"error": "Parâmetros obrigatórios: data_inicio, data_fim, CodInstalacao"}, 400

        dt1 = ref_to_date(data_inicio)
        dt2 = ref_to_date(data_fim)
        dt_ini, dt_fim = min(dt1, dt2), max(dt1, dt2)

        try:
            # Busca arquivos usando sistema de fallback (local + Google Drive)
            arquivos_info = buscar_arquivos_fatura_com_fallback(codinstalacao, data_inicio, data_fim)
            
            if not arquivos_info:
                return {"error": f"Nenhuma fatura encontrada para instalação {codinstalacao}"}, 404
            
            # Processa arquivos encontrados
            dados_consolidados = []
            arquivos_processados = 0
            arquivos_com_erro = 0
            
            for arquivo_info in arquivos_info:
                nome_arquivo = arquivo_info['arquivo']
                referencia = arquivo_info['referencia']
                fonte = arquivo_info['fonte']
                
                # Obtém caminho do arquivo (baixa do Drive se necessário)
                caminho_arquivo = obter_caminho_arquivo_fatura(arquivo_info)
                
                if not caminho_arquivo:
                    current_app.logger.warning(f"Não foi possível obter arquivo {nome_arquivo} da fonte {fonte}")
                    arquivos_com_erro += 1
                    continue
                
                # Extrai dados da fatura
                try:
                    dados_fatura = extrair_dados_completos_da_fatura(
                        caminho_arquivo, 
                        via_regex, 
                        codinstalacao=codinstalacao,
                        use_cache=True
                    )
                    if "error" not in dados_fatura:
                        dados_consolidados.append({
                            "arquivo": nome_arquivo,
                            "referencia": referencia,
                            "dados": dados_fatura,
                            "fonte": fonte  # Inclui informação da fonte
                        })
                        arquivos_processados += 1
                    else:
                        current_app.logger.warning(f"Erro ao extrair dados de {nome_arquivo}: {dados_fatura.get('error', 'Erro desconhecido')}")
                        arquivos_com_erro += 1
                except Exception as e:
                    current_app.logger.error(f"Erro ao processar arquivo {nome_arquivo}: {str(e)}")
                    arquivos_com_erro += 1
            
            # Log de resultados
            current_app.logger.info(f"Processamento concluído: {arquivos_processados} sucessos, {arquivos_com_erro} erros")
            
            # Conta fontes dos arquivos processados
            fontes_utilizadas = {}
            for item in dados_consolidados:
                fonte = item.get('fonte', 'unknown')
                fontes_utilizadas[fonte] = fontes_utilizadas.get(fonte, 0) + 1
            
            return {
                "message": "Dados consolidados extraídos com sucesso",
                "parametros": {
                    "data_inicio": data_inicio,
                    "data_fim": data_fim,
                    "codInstalacao": codinstalacao,
                    "via_regex": via_regex
                },
                "total_faturas": len(dados_consolidados),
                "arquivos_processados": arquivos_processados,
                "arquivos_com_erro": arquivos_com_erro,
                "fontes_utilizadas": fontes_utilizadas,
                "dados": dados_consolidados
            }
            
        except Exception as e:
            return {"error": f"Erro ao processar faturas: {str(e)}"}, 500

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

        try:
            # Busca tarifas usando a função real
            tarifas_filtradas = get_tarifas_filtradas(
                periodo, distribuidora, modalidade, subgrupo, classe, detalhe
            )
            
            if tarifas_filtradas is None:
                return {"error": "Nenhuma tarifa encontrada para os parâmetros fornecidos"}, 404
            
            if isinstance(tarifas_filtradas, dict) and "error" in tarifas_filtradas:
                return tarifas_filtradas, 400
            
            # Converte objetos Timestamp para string para serialização JSON
            import json
            import pandas as pd
            import numpy as np
            from datetime import datetime
            
            def convert_timestamps(obj):
                if isinstance(obj, list):
                    return [convert_timestamps(item) for item in obj]
                elif isinstance(obj, dict):
                    return {key: convert_timestamps(value) for key, value in obj.items()}
                elif isinstance(obj, (pd.Timestamp, datetime)):
                    return obj.strftime('%Y-%m-%d %H:%M:%S')
                elif isinstance(obj, np.datetime64):
                    return str(obj)
                elif pd.isna(obj) or obj is None:
                    return None
                elif isinstance(obj, (np.integer, np.floating)):
                    return float(obj)
                else:
                    return obj
            
            tarifas_clean = convert_timestamps(tarifas_filtradas)
            
            # Converte para formato compacto por modalidade
            tarifas_compactas = extrair_tarifa_compacta_por_modalidade(tarifas_filtradas)
            
            # Converte valores de MWh para kWh
            tarifas_convertidas = converter_tarifas_para_kwh(tarifas_compactas)
            
            return {
                "message": "Tarifas encontradas com sucesso",
                "parametros": {
                    "periodo": periodo,
                    "distribuidora": distribuidora,
                    "modalidade": modalidade,
                    "subgrupo": subgrupo,
                    "classe": classe,
                    "detalhe": detalhe
                },
                "total_registros": len(tarifas_filtradas),
                "tarifas_raw": tarifas_clean,
                "tarifas_compactas": tarifas_convertidas
            }
            
        except Exception as e:
            return {"error": f"Erro ao buscar tarifas: {str(e)}"}, 500


@bp.route("/otimizacao/verde")
class OtimizacaoVerde(Resource):
    @bp.expect(otimizacao_verde_input)
    @bp.doc('otimizar_faturas_verde',
           description='Realiza otimização de tarifas verde com base em faturas de energia')
    def post(self):
        """Otimizar tarifas verde"""
        data = request.get_json(force=True)
        data_inicio = data.get("data_inicio")
        data_fim = data.get("data_fim")
        codinstalacao = data.get("codInstalacao")
        distribuidora = data.get("distribuidora", "EDP ES")
        pis = data.get("pis", None)
        cofins = data.get("cofins", None)
        icms = data.get("icms", None)
        
        if not all([data_inicio, data_fim, codinstalacao]):
            return {"error": "Parâmetros obrigatórios: data_inicio, data_fim, codInstalacao"}, 400
            
        try:
            # Usa sistema de fallback para buscar faturas
            dados_faturas, info_processamento = processar_faturas_com_fallback(
                codinstalacao, data_inicio, data_fim, True
            )
            
            if "error" in info_processamento:
                return {"error": info_processamento["error"]}, 404
            
            # Busca tarifas para o período
            tarifas_raw = get_tarifas_filtradas(mes_ano=data_inicio, distribuidora=distribuidora, detalhe="Não se Aplica")
            if not tarifas_raw or isinstance(tarifas_raw, dict) and "error" in tarifas_raw:
                return {"error": "Erro ao buscar tarifas para otimização"}, 404
            
            tarifas = extrair_tarifa_compacta_por_modalidade(tarifas_raw)
            tarifas_convertidas = converter_tarifas_para_kwh(tarifas)
            
            if "convencional pré-pagamento" in tarifas_convertidas:
                tarifa_ere = tarifas_convertidas["convencional pré-pagamento"].get("TEforaPonta", 0.05)
            elif "convencional" in tarifas_convertidas:
                tarifa_ere = tarifas_convertidas["convencional"].get("TEforaPonta", 0.05)
            if "verde" not in tarifas_convertidas:
                return {"error": "Tarifas verde não encontradas"}, 404
            # Executa otimização

            down_bound = 30
            up_bound = 1000
            
            resultado_verde = opt_tarifa_verde(
                dados_faturas, 
                tarifas_convertidas.get("verde", {}), 
                tarifa_ere, 
                down_bound, 
                up_bound,
                pis,
                cofins,
                icms
            )
            
            return {
                "message": "Otimização da tarifa verde realizada com sucesso",
                "parametros": {
                    "data_inicio": data_inicio,
                    "data_fim": data_fim,
                    "codInstalacao": codinstalacao,
                    "distribuidora": distribuidora
                },
                "faturas_analisadas": len(dados_faturas),
                "otimizacao_verde": resultado_verde
            }
            
        except Exception as e:
            return {"error": f"Erro na otimização: {str(e)}"}, 500

@bp.route("/otimizacao/azul")
class OtimizacaoAzul(Resource):
    @bp.expect(otimizacao_azul_input)
    @bp.doc('otimizar_faturas_azul',
           description='Realiza otimização de tarifas azul com base em faturas de energia')
    def post(self):
        """Otimizar tarifas azul"""
        data = request.get_json(force=True)
        data_inicio = data.get("data_inicio")
        data_fim = data.get("data_fim")
        codinstalacao = data.get("codInstalacao")
        distribuidora = data.get("distribuidora", "EDP ES")
        pis = data.get("pis", None)
        cofins = data.get("cofins", None)
        icms = data.get("icms", None)
        
        if not all([data_inicio, data_fim, codinstalacao]):
            return {"error": "Parâmetros obrigatórios: data_inicio, data_fim, codInstalacao"}, 400
            
        try:
            # Usa sistema de fallback para buscar faturas
            dados_faturas, info_processamento = processar_faturas_com_fallback(
                codinstalacao, data_inicio, data_fim, True
            )
            
            if "error" in info_processamento:
                return {"error": info_processamento["error"]}, 404
            
            # Busca tarifas para o período
            tarifas_raw = get_tarifas_filtradas(mes_ano=data_inicio, distribuidora=distribuidora, detalhe="Não se Aplica")
            if not tarifas_raw or isinstance(tarifas_raw, dict) and "error" in tarifas_raw:
                return {"error": "Erro ao buscar tarifas para otimização"}, 404
            
            tarifas = extrair_tarifa_compacta_por_modalidade(tarifas_raw)
            tarifas_convertidas = converter_tarifas_para_kwh(tarifas)
            
            if "convencional pré-pagamento" in tarifas_convertidas:
                tarifa_ere = tarifas_convertidas["convencional pré-pagamento"].get("TEforaPonta", 0.05)
            elif "convencional" in tarifas_convertidas:
                tarifa_ere = tarifas_convertidas["convencional"].get("TEforaPonta", 0.05)
            if "azul" not in tarifas_convertidas:
                return {"error": "Tarifas azul não encontradas"}, 404
            # Executa otimização

            down_bound = 30
            up_bound = 1000
            
            resultado_azul = opt_tarifa_azul(
                dados_faturas, 
                tarifas_convertidas.get("azul", {}), 
                tarifa_ere, 
                up_bound
            )
            
            return {
                "message": "Otimização da tarifa azul realizada com sucesso",
                "parametros": {
                    "data_inicio": data_inicio,
                    "data_fim": data_fim,
                    "codInstalacao": codinstalacao,
                    "distribuidora": distribuidora
                },
                "faturas_analisadas": len(dados_faturas),
                "otimizacao_azul": resultado_azul
            }
            
        except Exception as e:
            return {"error": f"Erro na otimização: {str(e)}"}, 500


@bp.route("/analisar-fatura")
class AnalisarFatura(Resource):
    @bp.expect(analisar_fatura_input)
    @bp.doc('analisar_eficiencia',
           description='Realiza análise tarifária completa: detecta modalidade atual, otimiza todas as opções e recomenda a melhor estratégia')
    def post(self):
        """Análise tarifária completa com detecção automática e otimização"""
        data = request.get_json(force=True)
        data_inicio = data.get("data_inicio")
        data_fim = data.get("data_fim")
        codinstalacao = data.get("codInstalacao")
        periodo = data.get("periodo")
        distribuidora = data.get("distribuidora")
        via_regex = data.get("via_regex", True)
        pis = data.get("pis")
        cofins = data.get("cofins")
        icms = data.get("icms")
        
        if not all([data_inicio, data_fim, codinstalacao, periodo, distribuidora]):
            return {"error": "Parâmetros obrigatórios: data_inicio, data_fim, codInstalacao, periodo, distribuidora"}, 400
            
        try:
            # Usa sistema de fallback para buscar faturas
            dados_faturas, info_processamento = processar_faturas_com_fallback(
                codinstalacao, data_inicio, data_fim, via_regex
            )
            
            if "error" in info_processamento:
                return {"error": info_processamento["error"]}, 404
            
            # Busca tarifas para análise
            tarifas_raw = get_tarifas_filtradas(mes_ano=periodo, distribuidora=distribuidora, detalhe="Não se Aplica")
            
            if not tarifas_raw or isinstance(tarifas_raw, dict) and "error" in tarifas_raw:
                return {"error": "Erro ao buscar tarifas para análise"}, 404
            
            tarifas = extrair_tarifa_compacta_por_modalidade(tarifas_raw)
            tarifas_convertidas = converter_tarifas_para_kwh(tarifas)
            
            # Busca tarifa ERE da modalidade convencional
            tarifa_ere = 0.05  # Valor padrão
            if "convencional pré-pagamento" in tarifas_convertidas:
                tarifa_ere = tarifas_convertidas["convencional pré-pagamento"].get("TEforaPonta", 0.05)
            elif "convencional" in tarifas_convertidas:
                tarifa_ere = tarifas_convertidas["convencional"].get("TEforaPonta", 0.05)
            
            # Executa análise tarifária completa com novo módulo
            resultado_analise = analisar_tarifas_completo(
                fatura_dados=dados_faturas,
                tarifas_disponiveis=tarifas_convertidas,
                tarifa_ere=tarifa_ere,
                pis=pis,
                cofins=cofins,
                icms=icms
            )
            
            return {
                "message": "Análise tarifária completa realizada com sucesso",
                "parametros": {
                    "data_inicio": data_inicio,
                    "data_fim": data_fim,
                    "codInstalacao": codinstalacao,
                    "periodo_tarifas": periodo,
                    "distribuidora": distribuidora,
                    "via_regex": via_regex,
                    "tarifa_ere": tarifa_ere
                },
                "faturas_analisadas": len(dados_faturas),
                "info_processamento": info_processamento,
                "analise": resultado_analise
            }
            
        except Exception as e:
            return {"error": f"Erro na análise: {str(e)}"}, 500

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
            # Extrai dados via regex
            dados_regex = extrair_dados_completos_da_fatura(pdf_path, True)
            
            # Extrai dados via LLM
            dados_llm = extrair_dados_completos_da_fatura(pdf_path, False)
            
            # Calcula diferenças
            if "error" not in dados_regex and "error" not in dados_llm:
                diferencas = dict_diff(dados_regex, dados_llm)
                tem_diferenca = has_diff(diferencas)
                
                return {
                    "message": "Comparação realizada com sucesso",
                    "pdf_path": pdf_path,
                    "status": "DIVERGENCIA" if tem_diferenca else "OK",
                    "tem_diferenca": tem_diferenca,
                    "diferencas": diferencas,
                    "dados_regex": dados_regex,
                    "dados_llm": dados_llm
                }
            else:
                return {
                    "message": "Erro em um ou ambos os métodos de extração",
                    "pdf_path": pdf_path,
                    "status": "ERROR",
                    "dados_regex": dados_regex,
                    "dados_llm": dados_llm
                }
                
        except FileNotFoundError:
            return {"error": "Arquivo PDF não encontrado"}, 404
        except Exception as e:
            return {"error": f"Erro ao comparar métodos: {str(e)}"}, 500

@bp.route("/calc-verde")
class CalcVerde(Resource):
    @bp.expect(calc_verde_input)
    @bp.doc('calcular_tarifa_verde',
           description='Calcula custos da modalidade tarifária Verde com base em faturas de energia')
    def post(self):
        """Calcular custos da tarifa Verde"""
        data = request.get_json(force=True)
        data_inicio = data.get("data_inicio")
        data_fim = data.get("data_fim")
        codinstalacao = data.get("codInstalacao")
        periodo_tarifas = data.get("periodo_tarifas")
        distribuidora = data.get("distribuidora", "EDP ES")
        demanda_contratada = data.get("demanda_contratada", None)
        pis = data.get("pis", None)
        cofins = data.get("cofins", None)
        icms = data.get("icms", None)
        via_regex = data.get("via_regex", True)
        
        if not all([data_inicio, data_fim, codinstalacao, periodo_tarifas]):
            return {"error": "Parâmetros obrigatórios: data_inicio, data_fim, codInstalacao, periodo_tarifas"}, 400
            
        try:
            # Usa sistema de fallback para buscar faturas
            dados_faturas, info_processamento = processar_faturas_com_fallback(
                codinstalacao, data_inicio, data_fim, via_regex
            )
            
            if "error" in info_processamento:
                return {"error": info_processamento["error"]}, 404
            
            # Busca tarifas para o período
            tarifas_raw = get_tarifas_filtradas(mes_ano=periodo_tarifas, distribuidora=distribuidora, detalhe="Não se Aplica")
            if not tarifas_raw or isinstance(tarifas_raw, dict) and "error" in tarifas_raw:
                return {"error": "Erro ao buscar tarifas verde"}, 404
            
            tarifas = extrair_tarifa_compacta_por_modalidade(tarifas_raw)
            tarifas_convertidas = converter_tarifas_para_kwh(tarifas)
            current_app.logger.debug(f'Tarifas: {tarifas_convertidas}')
            # Busca tarifa ERE da modalidade convencional pré-pagamento
            tarifa_ere = 0.05  # Valor padrão
            if "convencional pré-pagamento" in tarifas_convertidas:
                tarifa_ere = tarifas_convertidas["convencional pré-pagamento"].get("TEforaPonta", 0.05)
            elif "convencional" in tarifas_convertidas:
                tarifa_ere = tarifas_convertidas["convencional"].get("TEforaPonta", 0.05)
            if "verde" not in tarifas_convertidas:
                return {"error": "Tarifas verde não encontradas"}, 404
            
            # Executa cálculo da tarifa verde
            fatura_total, faturas_mensais = calcular_tarifa_verde(
                dados_faturas, 
                tarifas_convertidas["verde"], 
                tarifa_ere, 
                demanda_contratada,
                pis,
                cofins,
                icms
            )
            
            # Ordena faturas mensais cronologicamente
            faturas_mensais_ordenadas = ordenar_faturas_mensais_cronologicamente(faturas_mensais)
            
            return {
                "message": "Cálculo da tarifa Verde realizado com sucesso",
                "parametros": {
                    "data_inicio": data_inicio,
                    "data_fim": data_fim,
                    "codInstalacao": codinstalacao,
                    "periodo_tarifas": periodo_tarifas,
                    "distribuidora": distribuidora,
                    "demanda_contratada": demanda_contratada,
                    "tarifa_ere": tarifa_ere,
                    "via_regex": via_regex
                },
                "faturas_analisadas": len(dados_faturas),
                "valor_total_anual": fatura_total,
                "faturas_mensais": faturas_mensais_ordenadas,
                "tarifas_utilizadas": tarifas_convertidas["verde"]
            }
            
        except Exception as e:
            return {"error": f"Erro no cálculo da tarifa verde: {str(e)}"}, 500

@bp.route("/calc-azul")
class CalcAzul(Resource):
    @bp.expect(calc_azul_input)
    @bp.doc('calcular_tarifa_azul',
           description='Calcula custos da modalidade tarifária Azul com base em faturas de energia')
    def post(self):
        """Calcular custos da tarifa Azul"""
        data = request.get_json(force=True)
        data_inicio = data.get("data_inicio")
        data_fim = data.get("data_fim")
        codinstalacao = data.get("codInstalacao")
        periodo_tarifas = data.get("periodo_tarifas")
        distribuidora = data.get("distribuidora", "EDP ES")
        demanda_ponta = data.get("demanda_ponta", None)
        demanda_fora_ponta = data.get("demanda_fora_ponta", None)
        pis = data.get("pis", None)
        cofins = data.get("cofins", None)
        icms = data.get("icms", None)
        via_regex = data.get("via_regex", True)
        
        if not all([data_inicio, data_fim, codinstalacao, periodo_tarifas]):
            return {"error": "Parâmetros obrigatórios: data_inicio, data_fim, codInstalacao, periodo_tarifas"}, 400
            
        try:
            # Usa sistema de fallback para buscar faturas
            dados_faturas, info_processamento = processar_faturas_com_fallback(
                codinstalacao, data_inicio, data_fim, via_regex
            )
            
            if "error" in info_processamento:
                return {"error": info_processamento["error"]}, 404
            
            # Busca tarifas para o período
            tarifas_raw = get_tarifas_filtradas(mes_ano=periodo_tarifas, distribuidora=distribuidora, detalhe="Não se Aplica")
            if not tarifas_raw or isinstance(tarifas_raw, dict) and "error" in tarifas_raw:
                return {"error": "Erro ao buscar tarifas azul"}, 404
            
            tarifas = extrair_tarifa_compacta_por_modalidade(tarifas_raw)
            tarifas_convertidas = converter_tarifas_para_kwh(tarifas)
            # Busca tarifa ERE da modalidade convencional pré-pagamento
            tarifa_ere = 0.05  # Valor padrão
            if "convencional pré-pagamento" in tarifas_convertidas:
                tarifa_ere = tarifas_convertidas["convencional pré-pagamento"].get("TEforaPonta", 0.05)
            elif "convencional" in tarifas_convertidas:
                tarifa_ere = tarifas_convertidas["convencional"].get("TEforaPonta", 0.05)
            if "azul" not in tarifas_convertidas:
                return {"error": "Tarifas azul não encontradas"}, 404
            
            # Prepara parâmetros de demanda para tarifa azul
            dm = None
            if demanda_ponta is not None and demanda_fora_ponta is not None:
                dm = [demanda_fora_ponta, demanda_ponta]
            
            # Executa cálculo da tarifa azul
            fatura_total, faturas_mensais = calcular_tarifa_azul(
                dados_faturas, 
                tarifas_convertidas["azul"], 
                tarifa_ere, 
                dm,
                pis,
                cofins,
                icms
            )
            
            # Ordena faturas mensais cronologicamente
            faturas_mensais_ordenadas = ordenar_faturas_mensais_cronologicamente(faturas_mensais)
            
            return {
                "message": "Cálculo da tarifa Azul realizado com sucesso",
                "parametros": {
                    "data_inicio": data_inicio,
                    "data_fim": data_fim,
                    "codInstalacao": codinstalacao,
                    "periodo_tarifas": periodo_tarifas,
                    "distribuidora": distribuidora,
                    "demanda_ponta": demanda_ponta,
                    "demanda_fora_ponta": demanda_fora_ponta,
                    "tarifa_ere": tarifa_ere,
                    "via_regex": via_regex
                },
                "faturas_analisadas": len(dados_faturas),
                "valor_total_anual": fatura_total,
                "faturas_mensais": faturas_mensais_ordenadas,
                "tarifas_utilizadas": tarifas_convertidas["azul"]
            }
            
        except Exception as e:
            return {"error": f"Erro no cálculo da tarifa azul: {str(e)}"}, 500


# =============================================================================
# ENDPOINTS DE GERENCIAMENTO DE CACHE
# =============================================================================

@api.route('/cache/status/<string:codinstalacao>')
class CacheStatus(Resource):
    @api.doc('cache_status')
    def get(self, codinstalacao):
        """Retorna status do cache para uma instalação específica"""
        try:
            cache = get_cache_instance()
            stats = cache.get_cache_stats()
            
            if codinstalacao in stats.get("installations", {}):
                return {
                    "codinstalacao": codinstalacao,
                    "cache_info": stats["installations"][codinstalacao],
                    "cache_enabled": True
                }
            else:
                return {
                    "codinstalacao": codinstalacao,
                    "cache_info": {},
                    "cache_enabled": False,
                    "message": "Nenhum cache encontrado para esta instalação"
                }
                
        except Exception as e:
            return {"error": f"Erro ao obter status do cache: {str(e)}"}, 500


@api.route('/cache/stats')
class CacheStats(Resource):
    @api.doc('cache_stats')
    def get(self):
        """Retorna estatísticas globais do cache"""
        try:
            cache = get_cache_instance()
            return cache.get_cache_stats()
        except Exception as e:
            return {"error": f"Erro ao obter estatísticas do cache: {str(e)}"}, 500


@api.route('/cache/<string:codinstalacao>')
class CacheClear(Resource):
    @api.doc('cache_clear_installation')
    def delete(self, codinstalacao):
        """Remove todo o cache de uma instalação específica"""
        try:
            cache = get_cache_instance()
            success = cache.clear_cache(codinstalacao=codinstalacao)
            
            if success:
                return {
                    "message": f"Cache da instalação {codinstalacao} removido com sucesso",
                    "codinstalacao": codinstalacao
                }
            else:
                return {"error": "Falha ao remover cache"}, 500
                
        except Exception as e:
            return {"error": f"Erro ao remover cache: {str(e)}"}, 500


@api.route('/cache/<string:codinstalacao>/<string:periodo>')
class CacheClearPeriod(Resource):
    @api.doc('cache_clear_period')
    def delete(self, codinstalacao, periodo):
        """Remove cache de um período específico (formato: YYYY-MM)"""
        try:
            cache = get_cache_instance()
            success = cache.clear_cache(codinstalacao=codinstalacao, periodo=periodo)
            
            if success:
                return {
                    "message": f"Cache removido para {codinstalacao}/{periodo}",
                    "codinstalacao": codinstalacao,
                    "periodo": periodo
                }
            else:
                return {"error": "Falha ao remover cache do período"}, 500
                
        except Exception as e:
            return {"error": f"Erro ao remover cache do período: {str(e)}"}, 500


@api.route('/cache')
class CacheClearAll(Resource):
    @api.doc('cache_clear_all')
    def delete(self):
        """Remove todo o cache do sistema"""
        try:
            cache = get_cache_instance()
            success = cache.clear_cache()
            
            if success:
                return {"message": "Todo o cache foi removido com sucesso"}
            else:
                return {"error": "Falha ao remover todo o cache"}, 500
                
        except Exception as e:
            return {"error": f"Erro ao remover todo o cache: {str(e)}"}, 500