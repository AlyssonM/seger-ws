#!/usr/bin/env python3
"""
Teste rápido do formato de datas MÊS-YYYY
"""

import sys
sys.path.insert(0, 'src')

from utils.excel_parser import parse_excel_invoices

def test_format():
    """Testa formato MÊS-YYYY"""
    print("Testando formato MÊS-YYYY...")
    
    try:
        faturas = parse_excel_invoices(
            codinstalacao='9502511',
            data_inicio='JAN-2024',
            data_fim='MAR-2024',
            excel_path='Consumo_Governo_ES_EDP_21-25_Calculos.xlsx'
        )
        
        if faturas:
            print(f"✅ Sucesso! {len(faturas)} faturas encontradas:")
            for fatura in faturas:
                ref = fatura['referencia']
                print(f"   - {ref}")
        else:
            print("❌ Nenhuma fatura encontrada")
            
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    test_format()