# seger/routes.py
"""
Módulo que define as rotas (endpoints) da API para funcionalidades relacionadas ao Seger.

Este módulo gerencia as requisições HTTP para baixar, processar e analisar
faturas de energia, além de fornecer dados de tarifas e realizar otimizações
de custo.
"""

from flask import request, jsonify, send_file
from flask_restx import Namespace, Resource, fields
# Importações temporariamente comentadas para teste do Swagger
# from src.scraper import baixar_faturas_por_instalacao
# from src.parser import extrair_dados_completos_da_fatura, analisar_eficiencia_energetica
# from src.utils.dict_diff import dict_diff, has_diff
# from src.utils.tarifas import get_tarifas_filtradas
# from src.utils.tarifas import calcular_tarifa_verde, calcular_tarifa_azul
# from src.utils.tarifas import extrair_tarifa_compacta_por_modalidade
# from src.optmization import opt_tarifa_verde, opt_tarifa_azul
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
        
        if not isinstance(instalacoes, list) or not inicio or not fim:
            return {"error": "instalacoes (lista), data_inicio e data_fim são obrigatórios"}, 400

        # Implementação de demonstração para teste do Swagger
        return {
            "message": "Endpoint faturas implementado com Swagger",
            "instalacoes_recebidas": instalacoes,
            "periodo": f"{inicio} a {fim}",
            "mode": mode
        }

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

        # Implementação de demonstração para teste do Swagger
        return {
            "message": "Endpoint dados-fatura implementado com Swagger",
            "pdf_path_recebido": pdf_path,
            "via_regex": via_regex,
            "dados_exemplo": {
                "consumo_ativo": {"ponta_kwh": 150.5, "fora_ponta_kwh": 890.2},
                "demanda": {"maxima": [{"valor_kw": 45.8}]},
                "valores_totais": {"valor_total_fatura": 1250.75}
            }
        }

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

        # Implementação de demonstração para teste do Swagger
        return {
            "message": "Endpoint faturas-json implementado com Swagger",
            "parametros_recebidos": {
                "data_inicio": data_inicio,
                "data_fim": data_fim,
                "codInstalacao": codinstalacao,
                "via_regex": via_regex
            },
            "dados_exemplo": {
                "mes_referencia": ["JAN-2024", "FEV-2024", "MAR-2024"],
                "Energia_Ativa_Ponta": [150.5, 145.8, 162.3],
                "Energia_Ativa_Fora_Ponta": [890.2, 876.4, 912.1],
                "Fatura_total": [1250.75, 1180.50, 1320.80]
            }
        }

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

        # Implementação de demonstração para teste do Swagger
        return {
            "message": "Endpoint tarifas implementado com Swagger",
            "parametros_recebidos": {
                "periodo": periodo,
                "distribuidora": distribuidora,
                "modalidade": modalidade,
                "subgrupo": subgrupo,
                "classe": classe,
                "detalhe": detalhe
            },
            "tarifas_exemplo": {
                "verde": {
                    "TE": 0.45123,
                    "TUSD": 0.12456,
                    "TEforaPonta": 0.38745
                },
                "azul": {
                    "TEponta": 0.89456,
                    "TEforaPonta": 0.45123,
                    "TUSDponta": 0.15789
                }
            }
        }

@bp.route("/otimizacao")
class Otimizacao(Resource):
    @bp.expect(otimizacao_input)
    @bp.doc('otimizar_faturas',
           description='Realiza otimização de tarifas verde e azul com base em faturas de energia')
    def post(self):
        """Otimizar tarifas verde e azul"""
        return {"message": "Endpoint de otimização implementado - funcionalidade completa em desenvolvimento"}

@bp.route("/analisar-fatura")
class AnalisarFatura(Resource):
    @bp.expect(analisar_fatura_input)
    @bp.doc('analisar_eficiencia',
           description='Analisa eficiência energética e otimização de tarifas com base em faturas')
    def post(self):
        """Analisar eficiência energética e otimização de tarifas"""
        return {"message": "Endpoint de análise implementado - funcionalidade completa em desenvolvimento"}

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

        # Implementação de demonstração para teste do Swagger
        return {
            "message": "Endpoint dados-fatura/teste implementado com Swagger",
            "pdf_path_recebido": pdf_path,
            "status": "OK",
            "diff": {},
            "regex": {"consumo_ativo": {"ponta_kwh": 150.5}, "metodo": "regex"},
            "llm": {"consumo_ativo": {"ponta_kwh": 150.5}, "metodo": "llm"}
        }