#!/usr/bin/env python3
"""
Script para converter planilha Excel (2021-2024) para formato CSV
compatível com o sistema de fallback de faturas.
"""

import pandas as pd
import os
from datetime import datetime

def convert_excel_to_csv():
    """
    Converte a planilha Excel de dados 2021-2024 para CSV
    """
    
    # Caminhos dos arquivos
    excel_path = "/home/user/studio/seger-ws/src/data/Consumo_Governo_ES_EDP_21-24_Calculos.xlsx"
    csv_path = "/home/user/studio/seger-ws/src/data/Consumo_Governo_ES_EDP_21-24_Calculos.csv"
    
    print("🔄 Convertendo Excel para CSV...")
    print(f"📁 Origem: {excel_path}")
    print(f"💾 Destino: {csv_path}")
    
    try:
        # Carrega o arquivo Excel
        print("\n📊 Carregando planilha Excel...")
        df = pd.read_excel(excel_path)
        print(f"✅ Planilha carregada com {len(df)} linhas e {len(df.columns)} colunas")
        
        # Mostra as primeiras colunas para verificação
        print("\n📋 Colunas encontradas:")
        for i, col in enumerate(df.columns[:10]):  # Mostra as primeiras 10 colunas
            print(f"   {i+1:2d}. {col}")
        if len(df.columns) > 10:
            print(f"   ... e mais {len(df.columns) - 10} colunas")
        
        # Adiciona coluna AnoMês se não existir (baseada nas colunas Ano e Mês)
        if 'AnoMês' not in df.columns and 'Ano' in df.columns and 'Mês' in df.columns:
            print("\n🔧 Criando coluna AnoMês a partir de Ano e Mês...")
            df['AnoMês'] = df['Ano'].astype(str) + df['Mês'].astype(str).str.zfill(2)
            print(f"✅ Coluna AnoMês criada. Exemplo: {df['AnoMês'].iloc[0]}")
        
        # Se precisar adicionar uma coluna "Dt. Leitura" fictícia (para compatibilidade)
        if 'Dt. Leitura' not in df.columns:
            print("\n🔧 Adicionando coluna 'Dt. Leitura' fictícia...")
            # Cria data fictícia baseada no último dia do mês de referência
            df['Dt. Leitura'] = df.apply(lambda row: f"31/{int(row['Mês']):02d}/{int(row['Ano'])}", axis=1)
        
        # Reorganiza as colunas para ficar similar ao CSV 2025
        # Coloca AnoMês e Dt. Leitura no início
        cols = df.columns.tolist()
        if 'AnoMês' in cols:
            cols.remove('AnoMês')
            cols.insert(0, 'AnoMês')
        if 'Dt. Leitura' in cols:
            cols.remove('Dt. Leitura') 
            cols.insert(1, 'Dt. Leitura')
        df = df[cols]
        
        # Salva como CSV
        print(f"\n💾 Salvando como CSV...")
        df.to_csv(csv_path, index=False, encoding='utf-8')
        
        # Verifica o arquivo criado
        if os.path.exists(csv_path):
            file_size = os.path.getsize(csv_path) / (1024*1024)  # MB
            print(f"✅ CSV criado com sucesso!")
            print(f"📏 Tamanho: {file_size:.2f} MB")
            
            # Mostra uma amostra do CSV
            print(f"\n📋 Primeiras 3 linhas do CSV:")
            df_sample = pd.read_csv(csv_path, nrows=3)
            print(df_sample.to_string(max_colwidth=15))
            
            # Estatísticas
            print(f"\n📈 Estatísticas:")
            print(f"   • Total de registros: {len(df):,}")
            print(f"   • Instalações únicas: {df['Instalação'].nunique():,}")
            print(f"   • Período: {df['Ano'].min()} - {df['Ano'].max()}")
            if 'AnoMês' in df.columns:
                print(f"   • AnoMês min: {df['AnoMês'].min()}")
                print(f"   • AnoMês max: {df['AnoMês'].max()}")
        else:
            print("❌ Erro: arquivo CSV não foi criado")
            
    except FileNotFoundError:
        print(f"❌ Erro: Arquivo Excel não encontrado: {excel_path}")
    except Exception as e:
        print(f"❌ Erro durante conversão: {str(e)}")

def verify_csv_format():
    """
    Verifica se o CSV está no formato correto
    """
    csv_path = "/home/user/studio/seger-ws/src/data/Consumo_Governo_ES_EDP_21-24_Calculos.csv"
    
    if not os.path.exists(csv_path):
        print("❌ CSV não encontrado para verificação")
        return
        
    print("\n🔍 Verificando formato do CSV...")
    
    try:
        df = pd.read_csv(csv_path, nrows=100)  # Lê apenas as primeiras 100 linhas
        
        # Verifica colunas essenciais
        required_cols = ['Instalação', 'AnoMês']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            print(f"⚠️  Colunas faltando: {missing_cols}")
        else:
            print("✅ Colunas essenciais presentes")
            
        # Verifica formato AnoMês
        if 'AnoMês' in df.columns:
            sample_anomes = df['AnoMês'].iloc[0]
            if len(str(sample_anomes)) == 6:
                print(f"✅ Formato AnoMês correto: {sample_anomes}")
            else:
                print(f"⚠️  Formato AnoMês pode estar incorreto: {sample_anomes}")
                
        # Verifica se tem dados de várias instalações
        unique_installations = df['Instalação'].nunique()
        print(f"✅ Instalações na amostra: {unique_installations}")
        
    except Exception as e:
        print(f"❌ Erro na verificação: {str(e)}")

if __name__ == "__main__":
    print("🚀 Conversor Excel → CSV para dados de faturas (2021-2024)")
    print("=" * 60)
    
    convert_excel_to_csv()
    verify_csv_format()
    
    print("\n" + "=" * 60)
    print("✅ Conversão concluída!")
    print("\n💡 Próximos passos:")
    print("   1. Verificar se o CSV foi criado corretamente")
    print("   2. Atualizar excel_parser.py para usar CSV também para 2021-2024")
    print("   3. Testar com dados históricos")