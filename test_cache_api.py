#!/usr/bin/env python3
"""
Teste dos endpoints da API de cache.
"""

import requests
import json

BASE_URL = "http://localhost:5001"

def test_cache_endpoints():
    """Testa os endpoints da API de cache."""
    
    print("🔧 TESTE DOS ENDPOINTS DA API DE CACHE")
    print("=" * 50)
    
    # Teste 1: Estatísticas globais do cache
    print("\n1️⃣ Testando GET /cache/stats")
    try:
        response = requests.get(f"{BASE_URL}/cache/stats")
        if response.status_code == 200:
            data = response.json()
            print("✅ Estatísticas obtidas com sucesso:")
            print(f"   - Instalações: {data.get('total_installations', 0)}")
            print(f"   - Arquivos cached: {data.get('total_cached_files', 0)}")
            print(f"   - Tamanho: {data.get('cache_size_mb', 0)} MB")
        else:
            print(f"❌ Erro: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Erro na requisição: {str(e)}")
    
    # Teste 2: Status do cache para instalação específica
    print("\n2️⃣ Testando GET /cache/status/0000144112")
    try:
        response = requests.get(f"{BASE_URL}/cache/status/0000144112")
        if response.status_code == 200:
            data = response.json()
            print("✅ Status obtido com sucesso:")
            print(f"   - Cache enabled: {data.get('cache_enabled', False)}")
            if data.get('cache_info'):
                print(f"   - Arquivos: {data['cache_info'].get('cached_files', 0)}")
                print(f"   - Range: {data['cache_info'].get('data_range', {})}")
        else:
            print(f"❌ Erro: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Erro na requisição: {str(e)}")
    
    # Teste 3: Limpar cache de período específico
    print("\n3️⃣ Testando DELETE /cache/0000144112/2024-09")
    try:
        response = requests.delete(f"{BASE_URL}/cache/0000144112/2024-09")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ {data.get('message', 'Cache removido')}")
        else:
            print(f"❌ Erro: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Erro na requisição: {str(e)}")
    
    # Teste 4: Verificar se cache foi removido
    print("\n4️⃣ Verificando se cache foi removido")
    try:
        response = requests.get(f"{BASE_URL}/cache/stats")
        if response.status_code == 200:
            data = response.json()
            print(f"   - Arquivos cached após remoção: {data.get('total_cached_files', 0)}")
        else:
            print(f"❌ Erro: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Erro na requisição: {str(e)}")
    
    print("\n✅ TESTE DOS ENDPOINTS CONCLUÍDO!")
    print("=" * 50)

if __name__ == "__main__":
    test_cache_endpoints()