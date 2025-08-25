#!/usr/bin/env python3
"""
Teste direto do Excel fallback sem dependências do Google Drive
"""

import sys
import os
import pandas as pd
from datetime import datetime

# Adiciona o diretório src ao path
sys.path.insert(0, 'src')

from utils.excel_parser import parse_excel_invoices, transform_excel_row_to_json

def test_excel_fallback():
    """Testa o fallback do Excel com dados mockados"""
    print("=== Teste do Excel Fallback ===")
    
    # Dados mockados baseados na estrutura da planilha
    mock_data = {
        'Conces.': ['EDP ES'],
        'Dt. Leitura': ['31/01/2024'],
        'Instalação': ['9502511'],
        'Cód. PN': ['12345'],
        'Parceiro de negócio': ['Cliente Teste'],
        'Número do CNPJ': ['12.345.678/0001-00'],
        'Recebedor alternativo': [''],
        'Nº de contrato': ['123456'],
        'Titular do contrato': ['Governo ES'],
        'Categoria tarifa': ['A4'],
        'Desc. Categoria tarifa': ['Alta Tensão'],
        'Fase': ['Trifásica'],
        'Tp Cli (BT,MT,AT)': ['AT'],
        'Lote de Leitura': ['001'],
        'Dt. Vencimento': ['15/02/2024'],
        'Classe': ['PODER PÚBLICO'],
        'Desc. Classe': ['PODER PUBLICO - ESTADUAL'],
        'Município': ['Vila Velha'],
        'Bairro': ['Olaria'],
        'Rua': ['Rua Teste'],
        'Nº': ['123'],
        'CEP': ['29000-000'],
        'Energia Faturada Ponta': [1500.5],
        'Receita Energia Faturada Ponta': [850.25],
        'Energia Faturada Fora Ponta': [8500.8],
        'Receita Energia Faturada Fora Ponta': [3200.50],
        'Demanda Faturada Ponta': [150.2],
        'Receita Demanda Faturada Ponta': [450.60],
        'Demanda Faturada Fora Ponta': [200.7],
        'Receita Demanda Faturada Fora Ponta': [600.21],
        'Demanda Registrada Ponta': [148.5],
        'Receita Demanda Registrada Ponta': [445.50],
        'Demanda Registrada F.Ponta': [195.3],
        'Receita Demanda Registrada F.Ponta': [585.90],
        'Demanda Contratada Ponta': [160.0],
        'Receita Demanda Contratada Ponta': [480.00],
        'Demanda Contratada F.Ponta': [210.0],
        'Receita Demanda Contratada F.Ponta': [630.00],
        'Demanda Ultrapassagem Ponta': [0.0],
        'Receita Demanda Ultrapassagem Ponta': [0.0],
        'Demanda Ultrapassagem Fora Ponta': [0.0],
        'Receita Demanda Ultrapassagem Fora Ponta': [0.0],
        'Importe UFER Ponta': [25.5],
        'Receita Importe UFER Ponta': [76.50],
        'Importe UFER Fora Ponta': [45.8],
        'Receita Importe UFER Fora Ponta': [137.40],
        'Importe UFDR': [0.0],
        'Receita Importe UFDR': [0.0],
        'Receita Total': [7500.86],
        'Juros Atraso Pagamento': [0.0],
        'IGPM': [0.0],
        'Multa Atraso Pagamento': [0.0],
        'CIP': [85.50],
        'COFINS': [225.02],
        'PIS': [48.75],
        'ICMS': [1875.21],
        'Parcelamentos': [0.0],
        'Cust. Disp. MMGD': [0.0],
        'Res. 77': [0.0],
        'Desconto AES': [0.0],
        'Energia Comp. MMGD': [0.0],
        'Receita Energia Comp. MMGD': [0.0],
        'Energia Injet. MMGD': [0.0],
        'Imp. Ret. Fonte': [0.0],
        'TUS Geração': [0.0],
        'Créditos': [0.0],
        'Outros Valores': [12.50],
        'Ano': [2024],
        'Mês': [1]
    }
    
    # Cria DataFrame mockado
    df_mock = pd.DataFrame(mock_data)
    
    # Testa transform_excel_row_to_json
    print("\n1. Testando transformação de linha Excel para JSON...")
    row = df_mock.iloc[0]  # Primeira linha
    json_result = transform_excel_row_to_json(row)
    
    if json_result:
        print("✅ Transformação bem-sucedida!")
        print(f"   - Referência: {json_result['referencia']}")
        print(f"   - Instalação: {json_result['dados']['identificacao']['numero_instalacao']}")
        print(f"   - Energia Ponta: {json_result['dados']['consumo_ativo']['ponta_kwh']} kWh")
        print(f"   - Energia Fora Ponta: {json_result['dados']['consumo_ativo']['fora_ponta_kwh']} kWh")
        print(f"   - Demanda Ponta: {json_result['dados']['demanda']['maxima'][0]['valor_kw']} kW")
        print(f"   - Valor Total: R$ {json_result['dados']['valores_totais']['valor_total_fatura']}")
        
        # Verifica se não tem perdas (deve ser array vazio)
        perdas = json_result['dados']['perdas']
        print(f"   - Perdas: {perdas} (deve ser array vazio)")
        
        return True
    else:
        print("❌ Falha na transformação")
        return False

def test_create_mock_excel():
    """Cria arquivo Excel mockado para teste"""
    print("\n2. Criando arquivo Excel mockado...")
    
    # Dados de várias instalações e meses
    mock_data = []
    instalacoes = ['9502511', '9502512', '9502513']
    meses = [(2024, 1), (2024, 2), (2024, 3)]
    
    for instalacao in instalacoes:
        for ano, mes in meses:
            row_data = {
                'Conces.': 'EDP ES',
                'Dt. Leitura': f'31/{mes:02d}/{ano}',
                'Instalação': instalacao,
                'Cód. PN': f'{instalacao}_PN',
                'Parceiro de negócio': f'Cliente {instalacao}',
                'Número do CNPJ': '12.345.678/0001-00',
                'Recebedor alternativo': '',
                'Nº de contrato': f'123456_{instalacao}',
                'Titular do contrato': 'Governo ES',
                'Categoria tarifa': 'A4',
                'Desc. Categoria tarifa': 'Alta Tensão',
                'Fase': 'Trifásica',
                'Tp Cli (BT,MT,AT)': 'AT',
                'Lote de Leitura': '001',
                'Dt. Vencimento': f'15/{(mes%12)+1:02d}/{ano}',
                'Classe': 'PODER PÚBLICO',
                'Desc. Classe': 'PODER PUBLICO - ESTADUAL',
                'Município': 'Vila Velha',
                'Bairro': 'Olaria',
                'Rua': 'Rua Teste',
                'Nº': '123',
                'CEP': '29000-000',
                'Energia Faturada Ponta': 1500.5 + (mes * 10),
                'Receita Energia Faturada Ponta': 850.25 + (mes * 5),
                'Energia Faturada Fora Ponta': 8500.8 + (mes * 50),
                'Receita Energia Faturada Fora Ponta': 3200.50 + (mes * 25),
                'Demanda Faturada Ponta': 150.2 + mes,
                'Receita Demanda Faturada Ponta': 450.60 + (mes * 3),
                'Demanda Faturada Fora Ponta': 200.7 + mes,
                'Receita Demanda Faturada Fora Ponta': 600.21 + (mes * 4),
                'Demanda Registrada Ponta': 148.5 + mes,
                'Receita Demanda Registrada Ponta': 445.50 + (mes * 3),
                'Demanda Registrada F.Ponta': 195.3 + mes,
                'Receita Demanda Registrada F.Ponta': 585.90 + (mes * 4),
                'Demanda Contratada Ponta': 160.0,
                'Receita Demanda Contratada Ponta': 480.00,
                'Demanda Contratada F.Ponta': 210.0,
                'Receita Demanda Contratada F.Ponta': 630.00,
                'Demanda Ultrapassagem Ponta': 0.0,
                'Receita Demanda Ultrapassagem Ponta': 0.0,
                'Demanda Ultrapassagem Fora Ponta': 0.0,
                'Receita Demanda Ultrapassagem Fora Ponta': 0.0,
                'Importe UFER Ponta': 25.5,
                'Receita Importe UFER Ponta': 76.50,
                'Importe UFER Fora Ponta': 45.8,
                'Receita Importe UFER Fora Ponta': 137.40,
                'Importe UFDR': 0.0,
                'Receita Importe UFDR': 0.0,
                'Receita Total': 7500.86 + (mes * 100),
                'Juros Atraso Pagamento': 0.0,
                'IGPM': 0.0,
                'Multa Atraso Pagamento': 0.0,
                'CIP': 85.50,
                'COFINS': 225.02,
                'PIS': 48.75,
                'ICMS': 1875.21,
                'Parcelamentos': 0.0,
                'Cust. Disp. MMGD': 0.0,
                'Res. 77': 0.0,
                'Desconto AES': 0.0,
                'Energia Comp. MMGD': 0.0,
                'Receita Energia Comp. MMGD': 0.0,
                'Energia Injet. MMGD': 0.0,
                'Imp. Ret. Fonte': 0.0,
                'TUS Geração': 0.0,
                'Créditos': 0.0,
                'Outros Valores': 12.50,
                'Ano': ano,
                'Mês': mes
            }
            mock_data.append(row_data)
    
    df_mock = pd.DataFrame(mock_data)
    excel_path = 'test_Consumo_Governo_ES_EDP_21-25_Calculos.xlsx'
    
    try:
        df_mock.to_excel(excel_path, index=False)
        print(f"✅ Arquivo Excel criado: {excel_path}")
        print(f"   - Total de linhas: {len(df_mock)}")
        return excel_path
    except Exception as e:
        print(f"❌ Erro ao criar Excel: {e}")
        return None

def test_parse_excel_with_mock_file():
    """Testa parse_excel_invoices com arquivo mockado"""
    print("\n3. Testando parse_excel_invoices com arquivo mockado...")
    
    excel_path = test_create_mock_excel()
    if not excel_path:
        return False
    
    try:
        # Testa busca por instalação 9502511 para Jan-Mar 2024
        faturas = parse_excel_invoices(
            codinstalacao='9502511',
            data_inicio='2024-01-01',
            data_fim='2024-03-31',
            excel_path=excel_path
        )
        
        if faturas:
            print(f"✅ Parse bem-sucedido! Encontradas {len(faturas)} faturas")
            for fatura in faturas:
                ref = fatura['referencia']
                energia_total = fatura['dados']['consumo_ativo']['total_kwh']
                valor_total = fatura['dados']['valores_totais']['valor_total_fatura']
                print(f"   - {ref}: {energia_total:.1f} kWh, R$ {valor_total:.2f}")
            
            # Cleanup
            if os.path.exists(excel_path):
                os.remove(excel_path)
                print(f"✅ Arquivo de teste removido: {excel_path}")
            
            return True
        else:
            print("❌ Nenhuma fatura encontrada")
            return False
            
    except Exception as e:
        print(f"❌ Erro no parse: {e}")
        return False

if __name__ == "__main__":
    success1 = test_excel_fallback()
    success2 = test_parse_excel_with_mock_file()
    
    print(f"\n=== Resumo dos Testes ===")
    print(f"Transformação JSON: {'✅ OK' if success1 else '❌ FALHOU'}")
    print(f"Parse Excel completo: {'✅ OK' if success2 else '❌ FALHOU'}")
    
    if success1 and success2:
        print("\n🎉 Todos os testes do Excel fallback passaram!")
        sys.exit(0)
    else:
        print("\n❌ Alguns testes falharam")
        sys.exit(1)