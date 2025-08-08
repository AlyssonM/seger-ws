#!/usr/bin/env python3
"""
Script de teste para o sistema de cache de faturas.
"""

import os
import sys
import time
import logging

# Adiciona o diretório src ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.parser import extrair_dados_completos_da_fatura
from src.utils.fatura_cache import get_cache_instance

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_cache_system():
    """Testa o sistema de cache de faturas."""
    
    # Arquivo de teste
    pdf_path = "/home/user/studio/seger-ws/faturas_edp/0000144112/fatura_SET-2024.pdf"
    codinstalacao = "0000144112"
    
    if not os.path.exists(pdf_path):
        print(f"❌ Arquivo de teste não encontrado: {pdf_path}")
        return
    
    print("🧪 TESTE DO SISTEMA DE CACHE DE FATURAS")
    print("=" * 50)
    
    # Limpa cache existente para teste limpo
    print("\n1️⃣ Limpando cache existente...")
    cache = get_cache_instance()
    cache.clear_cache(codinstalacao)
    
    # Teste 1: Processamento inicial (sem cache)
    print("\n2️⃣ Teste 1: Processamento inicial (sem cache)")
    start_time = time.time()
    
    dados1 = extrair_dados_completos_da_fatura(
        pdf_path, 
        via_regex=True,
        codinstalacao=codinstalacao,
        use_cache=True
    )
    
    tempo1 = time.time() - start_time
    print(f"⏱️  Tempo de processamento: {tempo1:.2f}s")
    
    if "error" in dados1:
        print(f"❌ Erro no processamento: {dados1['error']}")
        return
    else:
        print("✅ Dados extraídos com sucesso")
    
    # Teste 2: Processamento com cache (deve ser muito mais rápido)
    print("\n3️⃣ Teste 2: Processamento com cache")
    start_time = time.time()
    
    dados2 = extrair_dados_completos_da_fatura(
        pdf_path, 
        via_regex=True,
        codinstalacao=codinstalacao,
        use_cache=True
    )
    
    tempo2 = time.time() - start_time
    print(f"⏱️  Tempo de processamento: {tempo2:.2f}s")
    
    # Verifica se dados são iguais
    if dados1 == dados2:
        print("✅ Dados do cache são idênticos aos originais")
    else:
        print("❌ Dados do cache diferem dos originais")
    
    # Calcula melhoria de performance
    if tempo2 > 0:
        melhoria = ((tempo1 - tempo2) / tempo1) * 100
        print(f"🚀 Melhoria de performance: {melhoria:.1f}% ({tempo1/tempo2:.1f}x mais rápido)")
    
    # Teste 3: Estatísticas do cache
    print("\n4️⃣ Teste 3: Estatísticas do cache")
    stats = cache.get_cache_stats()
    
    print(f"📁 Caminho do cache: {stats['cache_base_path']}")
    print(f"🏢 Total de instalações: {stats['total_installations']}")
    print(f"📄 Total de arquivos em cache: {stats['total_cached_files']}")
    print(f"💾 Tamanho do cache: {stats['cache_size_mb']:.2f} MB")
    
    if codinstalacao in stats.get('installations', {}):
        install_info = stats['installations'][codinstalacao]
        print(f"📊 Cache para {codinstalacao}:")
        print(f"   - Arquivos: {install_info['cached_files']}")
        print(f"   - Range: {install_info['data_range']}")
    
    # Teste 4: Validação de integridade
    print("\n5️⃣ Teste 4: Validação de integridade do cache")
    cached_data = cache.load_cached_data(codinstalacao, pdf_path)
    if cached_data:
        print("✅ Cache carregado e validado com sucesso")
    else:
        print("❌ Falha na validação do cache")
    
    print("\n✅ TESTE CONCLUÍDO!")
    print("=" * 50)

if __name__ == "__main__":
    test_cache_system()