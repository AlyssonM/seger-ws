# csv_parser.py
"""
Módulo para processar dados de faturas a partir de arquivos CSV como fallback.
"""

import os
import logging
import pandas as pd
from typing import Dict, List, Optional, Any
from datetime import datetime
from .google_drive_client import create_google_drive_client

# Função global para conversão de formato MÊS-YYYY
def parse_mes_ano(data_str: str) -> datetime:
    """Converte 'JAN-2024' para datetime"""
    meses_map = {
        'JAN': 1, 'FEV': 2, 'MAR': 3, 'ABR': 4, 'MAI': 5, 'JUN': 6,
        'JUL': 7, 'AGO': 8, 'SET': 9, 'OUT': 10, 'NOV': 11, 'DEZ': 12
    }
    mes_nome, ano = data_str.split('-')
    mes_num = meses_map.get(mes_nome.upper(), 1)
    return datetime(int(ano), mes_num, 1)

def fatura_para_consumo(data_str: str) -> str:
    """
    Converte período de fatura para período de consumo.
    JAN-2025 → DEZ-2024 (busca dados de dezembro)
    FEV-2025 → FEV-2025 (busca dados de fevereiro mesmo)
    """
    meses_map = {
        'JAN': 1, 'FEV': 2, 'MAR': 3, 'ABR': 4, 'MAI': 5, 'JUN': 6,
        'JUL': 7, 'AGO': 8, 'SET': 9, 'OUT': 10, 'NOV': 11, 'DEZ': 12
    }
    
    try:
        mes_nome, ano_str = data_str.split('-')
        mes_num = meses_map.get(mes_nome.upper(), 1)
        ano = int(ano_str)
        
        # Apenas janeiro precisa do mês anterior
        if mes_num == 1:  # Janeiro
            # Janeiro 2025 → Dezembro 2024
            ano_consumo = ano - 1
            mes_consumo = 12
        else:
            # Outros meses usam o próprio período
            ano_consumo = ano
            mes_consumo = mes_num
            
        return f"{ano_consumo:04d}{mes_consumo:02d}"
    except:
        return f"{datetime.now().year:04d}01"

def parse_csv_invoices(
    codinstalacao: str, 
    data_inicio: str, 
    data_fim: str
) -> List[Dict[str, Any]]:
    """
    Processa dados de faturas a partir de arquivos CSV
    
    Args:
        codinstalacao: Código da instalação  
        data_inicio: Data início no formato MÊS-YYYY (ex: "JAN-2024")
        data_fim: Data fim no formato MÊS-YYYY (ex: "DEZ-2024") 
        
    Returns:
        Lista de dados de faturas no formato JSON compatível com API
    """
    
    # Determina o período solicitado para escolher arquivos CSV
    inicio = parse_mes_ano(data_inicio)
    fim = parse_mes_ano(data_fim)
    
    # Processa dados de múltiplos CSVs conforme necessário
    return process_mixed_csv_sources(codinstalacao, data_inicio, data_fim)

def process_mixed_csv_sources(
    codinstalacao: str, 
    data_inicio: str, 
    data_fim: str
) -> List[Dict[str, Any]]:
    """Processa dados de múltiplos arquivos CSV: 2021-2024 e 2025"""
    
    inicio = parse_mes_ano(data_inicio)
    fim = parse_mes_ano(data_fim)
    faturas = []
    
    # Processa dados de 2025 do CSV se necessário
    if fim.year >= 2025:
        csv_2025_path = os.path.join(os.path.dirname(__file__), "../data/Consumo_Governo_ES_EDP_25_Calculos.csv")
        if os.path.exists(csv_2025_path):
            faturas_csv_2025 = parse_single_csv_file(codinstalacao, data_inicio, data_fim, csv_2025_path)
            faturas.extend(faturas_csv_2025)
            logging.info(f"Processadas {len(faturas_csv_2025)} faturas do CSV 2025")
    
    # Processa dados de 2021-2024 do CSV se necessário
    if inicio.year <= 2024:
        csv_2124_path = os.path.join(os.path.dirname(__file__), "../data/Consumo_Governo_ES_EDP_21-24_Calculos.csv")
        if os.path.exists(csv_2124_path):
            # Ajusta período para CSV 2021-2024 (apenas parte 2021-2024)
            data_inicio_2124 = data_inicio if inicio.year <= 2024 else "JAN-2024"
            data_fim_2124 = data_fim if fim.year <= 2024 else "DEZ-2024"
            
            faturas_csv_2124 = parse_single_csv_file(codinstalacao, data_inicio_2124, data_fim_2124, csv_2124_path)
            faturas.extend(faturas_csv_2124)
            logging.info(f"Processadas {len(faturas_csv_2124)} faturas do CSV 2021-2024")
    
    if not faturas:
        logging.warning(f"Nenhuma fatura encontrada para instalação {codinstalacao} no período {data_inicio} a {data_fim}")
    
    return faturas

def parse_single_csv_file(
    codinstalacao: str, 
    data_inicio: str, 
    data_fim: str,
    csv_path: str
) -> List[Dict[str, Any]]:
    """Processa dados de faturas a partir de um arquivo CSV específico"""
    
    try:
        # Carrega CSV
        df = pd.read_csv(csv_path)
        logging.info(f"CSV carregado com {len(df)} linhas: {os.path.basename(csv_path)}")
        
        # Filtra por código de instalação
        df_filtered = df[df['Instalação'].astype(str).str.replace('.0', '', regex=False) == str(codinstalacao)]
        
        if df_filtered.empty:
            logging.warning(f"Nenhum dado encontrado no CSV {os.path.basename(csv_path)} para instalação {codinstalacao}")
            return []
        
        inicio = parse_mes_ano(data_inicio)
        fim = parse_mes_ano(data_fim)
        
        # Extrai ano e mês da coluna AnoMês (formato: 202501)
        # Remove .0 caso exista e converte para int primeiro
        df_filtered['AnoMes_Clean'] = df_filtered['AnoMês'].astype(str).str.replace('.0', '', regex=False)
        df_filtered['Ano_Consumo'] = df_filtered['AnoMes_Clean'].str[:4].astype(int)
        df_filtered['Mes_Consumo'] = df_filtered['AnoMes_Clean'].str[4:].astype(int)
        
        # Converte períodos de fatura para períodos de consumo necessários
        periodos_consumo_needed = []
        
        # Gera lista de meses no período solicitado
        current_date = inicio.replace(day=1)
        while current_date <= fim:
            meses_map_rev = {
                1: "JAN", 2: "FEV", 3: "MAR", 4: "ABR", 5: "MAI", 6: "JUN",
                7: "JUL", 8: "AGO", 9: "SET", 10: "OUT", 11: "NOV", 12: "DEZ"
            }
            mes_fatura = f"{meses_map_rev[current_date.month]}-{current_date.year}"
            
            # Converte período de fatura para período de consumo
            anomes_consumo = fatura_para_consumo(mes_fatura)
            periodos_consumo_needed.append(anomes_consumo)
            
            # Próximo mês
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Debugging: Log os períodos necessários
        logging.info(f"Dados antes filtro período: {len(df_filtered)} linhas")
        logging.info(f"Períodos de consumo necessários: {periodos_consumo_needed}")
        if len(df_filtered) > 0:
            logging.info(f"Exemplo: AnoMes={df_filtered.iloc[0]['AnoMes_Clean']}")
        
        # Filtra por períodos de consumo necessários
        df_filtered = df_filtered[df_filtered['AnoMes_Clean'].isin(periodos_consumo_needed)]
        
        logging.info(f"Dados após filtro período: {len(df_filtered)} linhas")
        
        if df_filtered.empty:
            logging.warning(f"Nenhum dado encontrado no CSV {os.path.basename(csv_path)} para instalação {codinstalacao} no período {data_inicio} a {data_fim}")
            return []
        
        # Transforma cada linha em estrutura JSON compatível
        faturas = []
        for _, row in df_filtered.iterrows():
            fatura_data = transform_csv_row_to_json(row)
            if fatura_data:
                faturas.append(fatura_data)
        
        return faturas
        
    except Exception as e:
        logging.error(f"Erro ao processar CSV {os.path.basename(csv_path)}: {str(e)}")
        return []


def transform_csv_row_to_json(row: pd.Series) -> Optional[Dict[str, Any]]:
    """
    Transforma uma linha do CSV em estrutura JSON compatível com API
    
    Args:
        row: Linha do CSV como pandas Series
        
    Returns:
        Dicionário com estrutura compatível com JSON de fatura ou None em caso de erro
    """
    
    try:
        # Converte valores NaN para None/0
        def safe_float(value):
            if pd.isna(value) or value == '':
                return 0.0
            try:
                # Remove pontos como separadores de milhares e converte vírgulas para pontos decimais
                if isinstance(value, str):
                    original_value = value
                    # Se tem vírgula, assume formato brasileiro: "1.234,56" -> "1234.56"
                    if ',' in value:
                        value = value.replace('.', '').replace(',', '.')
                    # Se tem múltiplos pontos, assume que são separadores de milhares: "1.234.567" -> "1234567"
                    elif value.count('.') > 1:
                        value = value.replace('.', '')
                    logging.debug(f"Converting '{original_value}' to '{value}'")
                return float(value)
            except ValueError as e:
                logging.error(f"Error converting '{value}' to float: {e}")
                return 0.0
        
        def safe_str(value):
            if pd.isna(value):
                return ""
            str_val = str(value)
            # Remove .0 de números inteiros quando convertidos para string
            if str_val.endswith('.0') and str_val.replace('.0', '').isdigit():
                return str_val.replace('.0', '')
            return str_val
        
        # Extrai ano e mês de AnoMês (202501)
        ano_mes_str = safe_str(row['AnoMês']).replace('.0', '')  # Remove .0 se existir
        ano_consumo = int(ano_mes_str[:4])
        mes_consumo = int(ano_mes_str[4:])
        
        # Lógica simplificada: apenas dezembro vira janeiro do próximo ano
        # Demais meses usam o mesmo período do AnoMês
        if mes_consumo == 12:  # Dezembro → Janeiro do próximo ano
            ano_ref = ano_consumo + 1
            mes_ref_num = 1
        else:  # Outros meses → Mesmo período
            ano_ref = ano_consumo
            mes_ref_num = mes_consumo
        
        # Monta referência no formato MMM/YYYY
        meses = {
            1: "JAN", 2: "FEV", 3: "MAR", 4: "ABR", 5: "MAI", 6: "JUN",
            7: "JUL", 8: "AGO", 9: "SET", 10: "OUT", 11: "NOV", 12: "DEZ"
        }
        mes_ref = meses.get(mes_ref_num, "JAN")
        referencia = f"{mes_ref}/{ano_ref}"
        
        # Estrutura JSON compatível com formato atual da API  
        fatura_json = {
                "referencia": referencia,
                "periodo_consumo": ano_mes_str,  # AnoMês original para cache correto
                "identificacao": {
                    "numero_instalacao": safe_str(row['Instalação']),
                    "numero_cliente": safe_str(row.get('Cód. PN', '')),
                    "cnpj": safe_str(row.get('Número do CNPJ', '')),
                    "titular_contrato": safe_str(row.get('Titular do contrato', '')),
                    "categoria_tarifa": safe_str(row.get('Categoria tarifa', '')),
                    "desc_categoria_tarifa": safe_str(row.get('Desc. Categoria tarifa', '')),
                    "classe": safe_str(row.get('Classe', '')),
                    "desc_classe": safe_str(row.get('Desc. Classe', '')),
                    "municipio": safe_str(row.get('Município', '')),
                    "bairro": safe_str(row.get('Bairro', '')),
                    "endereco": f"{safe_str(row.get('Rua', ''))} {safe_str(row.get('Nº', ''))}",
                    "cep": safe_str(row.get('CEP', '')),
                    "mes_referencia": f"{mes_ref_num:02d}/{ano_ref}"
                },
                "leituras": {
                    "leitura_inicio": f"01/{mes_ref_num:02d}/{ano_ref}",
                    "leitura_fim": f"31/{mes_ref_num:02d}/{ano_ref}"  # Simplificado
                },
                "consumo_ativo": {
                    "ponta_kwh": safe_float(row.get('Energia Faturada Ponta', 0)),
                    "fora_ponta_kwh": safe_float(row.get('Energia Faturada Fora Ponta', 0)),
                    "energia_injetada_kwh": 0.0,
                    "total_kwh": safe_float(row.get('Energia Faturada Ponta', 0)) + safe_float(row.get('Energia Faturada Fora Ponta', 0))
                },
                "demanda": {
                    "contratada_fp_kw": safe_float(row.get('Demanda Contratada F.Ponta', 0)),
                    "maxima": [
                        {
                            "periodo": "ponta",
                            "valor_kw": safe_float(row.get('Demanda Faturada Ponta', 0))
                        },
                        {
                            "periodo": "fora_ponta", 
                            "valor_kw": safe_float(row.get('Demanda Faturada Fora Ponta', 0))
                        }
                    ],
                    "dmcr": [
                        {
                            "periodo": "ponta",
                            "valor_kw": safe_float(row.get('Demanda Registrada Ponta', 0))
                        },
                        {
                            "periodo": "fora_ponta",
                            "valor_kw": safe_float(row.get('Demanda Registrada F.Ponta', 0))
                        }
                    ]
                },
                "energia_reativa": {
                    "excedente": {
                        "total_kwh": safe_float(row.get('Importe UFER Ponta', 0)) + safe_float(row.get('Importe UFER Fora Ponta', 0))
                    },
                    "ponta_kvarh": safe_float(row.get('Importe UFER Ponta', 0)),
                    "fora_ponta_kvarh": safe_float(row.get('Importe UFER Fora Ponta', 0))
                },
                "valores_totais": {
                    "valor_total_fatura": safe_float(row.get('Receita Total', 0)),
                    "energia_eletrica": safe_float(row.get('Receita Energia Faturada Ponta', 0)) + safe_float(row.get('Receita Energia Faturada Fora Ponta', 0)),
                    "demanda_potencia": safe_float(row.get('Receita Demanda Faturada Ponta', 0)) + safe_float(row.get('Receita Demanda Faturada Fora Ponta', 0))
                },
                "impostos": [
                    {
                        "nome": "PIS",
                        "valor_impostos": safe_float(row.get('PIS', 0)),
                        "aliquota": 0.0
                    },
                    {
                        "nome": "COFINS", 
                        "valor_impostos": safe_float(row.get('COFINS', 0)),
                        "aliquota": 0.0
                    },
                    {
                        "nome": "ICMS",
                        "valor_impostos": safe_float(row.get('ICMS', 0)),
                        "aliquota": 0.0
                    }
                ],
                "componentes_extras": [
                    {
                        "descricao": "Juros Atraso Pagamento",
                        "valor_total": safe_float(row.get('Juros Atraso Pagamento', 0))
                    },
                    {
                        "descricao": "Multa Atraso Pagamento", 
                        "valor_total": safe_float(row.get('Multa Atraso Pagamento', 0))
                    },
                    {
                        "descricao": "CIP",
                        "valor_total": safe_float(row.get('CIP', 0))
                    },
                    {
                        "descricao": "Contribuicao Iluminacao Publica",
                        "valor_total": safe_float(row.get('CIP', 0))
                    },
                    {
                        "descricao": "Custo Disponibilidade MMGD",
                        "valor_total": safe_float(row.get('Cust. Disp. MMGD', 0))
                    },
                    {
                        "descricao": "Outros Valores",
                        "valor_total": safe_float(row.get('OUTROS VALORES', 0))
                    }
                ],
                "perdas": []
        }
        
        return fatura_json
        
    except Exception as e:
        logging.error(f"Erro ao transformar linha do CSV: {str(e)}")
        return None

