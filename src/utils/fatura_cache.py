# fatura_cache.py
"""
Sistema de cache JSON para dados extraídos de faturas PDF.
Otimiza performance evitando reprocessamento de PDFs já analisados.
"""

import os
import json
import hashlib
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

class FaturaCache:
    """
    Gerenciador de cache para dados extraídos de faturas PDF.
    
    Estrutura do cache:
    cache/faturas/{codinstalacao}/
    ├── metadata.json
    ├── 2024-01_processed.json
    ├── 2024-02_processed.json
    └── ...
    """
    
    def __init__(self, cache_base_path: str = None, ttl_days: int = 365, max_size_gb: float = 5.0):
        """
        Inicializa o sistema de cache.
        
        Args:
            cache_base_path: Caminho base para o cache (default: cache/faturas)
            ttl_days: Tempo de vida do cache em dias
            max_size_gb: Tamanho máximo do cache em GB
        """
        self.cache_base_path = cache_base_path or os.path.join(os.getcwd(), "cache", "faturas")
        self.ttl_days = ttl_days
        self.max_size_gb = max_size_gb
        
        # Cria diretório base se não existir
        os.makedirs(self.cache_base_path, exist_ok=True)
        
        logging.info(f"Cache de faturas inicializado em: {self.cache_base_path}")
    
    def _get_installation_cache_dir(self, codinstalacao: str) -> str:
        """Retorna o diretório de cache para uma instalação específica."""
        return os.path.join(self.cache_base_path, codinstalacao)
    
    def _get_metadata_path(self, codinstalacao: str) -> str:
        """Retorna o caminho do arquivo de metadata."""
        return os.path.join(self._get_installation_cache_dir(codinstalacao), "metadata.json")
    
    def _get_cache_file_path(self, codinstalacao: str, periodo: str) -> str:
        """
        Retorna o caminho do arquivo de cache para um período específico.
        
        Args:
            codinstalacao: Código da instalação
            periodo: Período no formato YYYY-MM
        """
        return os.path.join(
            self._get_installation_cache_dir(codinstalacao), 
            f"{periodo}_processed.json"
        )
    
    def _calculate_file_hash(self, file_path: str) -> Optional[str]:
        """Calcula hash SHA256 de um arquivo."""
        try:
            with open(file_path, 'rb') as f:
                file_hash = hashlib.sha256()
                while chunk := f.read(8192):
                    file_hash.update(chunk)
                return f"sha256:{file_hash.hexdigest()}"
        except Exception as e:
            logging.error(f"Erro ao calcular hash do arquivo {file_path}: {str(e)}")
            return None
    
    def _extract_period_from_filename(self, filename: str) -> Optional[str]:
        """
        Extrai período (YYYY-MM) do nome do arquivo da fatura.
        
        Suporta formatos como:
        - fatura_JAN-2025.pdf -> 2025-01
        - fatura_SET-2024.pdf -> 2024-09
        - fatura_01-2025.pdf -> 2025-01
        """
        try:
            # Remove extensão
            name = filename.replace('.pdf', '').replace('.PDF', '')
            
            # Mapear meses em português
            meses_pt = {
                'JAN': '01', 'FEV': '02', 'MAR': '03', 'ABR': '04',
                'MAI': '05', 'JUN': '06', 'JUL': '07', 'AGO': '08',
                'SET': '09', 'OUT': '10', 'NOV': '11', 'DEZ': '12'
            }
            
            # Tenta extrair padrão MÊS-ANO ou ANO-MÊS
            if '-' in name:
                parts = name.split('_')[-1].split('-')  # Pega a última parte após _
                if len(parts) >= 2:
                    parte1 = parts[0].upper()
                    parte2 = parts[1].upper()
                    
                    # Caso 1: MÊS-ANO (ex: SET-2024)
                    if parte1 in meses_pt and parte2.isdigit() and len(parte2) == 4:
                        return f"{parte2}-{meses_pt[parte1]}"
                    
                    # Caso 2: ANO-MÊS (ex: 2024-09)
                    if parte1.isdigit() and len(parte1) == 4 and parte2.isdigit() and len(parte2) <= 2:
                        mes_num = parte2.zfill(2)
                        return f"{parte1}-{mes_num}"
                    
                    # Caso 3: ANO-MÊS_NOME (ex: 2024-SET)
                    if parte1.isdigit() and len(parte1) == 4 and parte2 in meses_pt:
                        return f"{parte1}-{meses_pt[parte2]}"
            
            return None
        except Exception as e:
            logging.warning(f"Não foi possível extrair período do arquivo {filename}: {str(e)}")
            return None
    
    def _load_metadata(self, codinstalacao: str) -> Dict[str, Any]:
        """Carrega metadata da instalação ou cria novo se não existir."""
        metadata_path = self._get_metadata_path(codinstalacao)
        
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Erro ao carregar metadata {metadata_path}: {str(e)}")
        
        # Cria metadata inicial
        return {
            "codinstalacao": codinstalacao,
            "cache_created": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "total_faturas_cached": 0,
            "data_range": {
                "inicio": None,
                "fim": None
            },
            "cache_version": "1.0"
        }
    
    def _save_metadata(self, codinstalacao: str, metadata: Dict[str, Any]) -> None:
        """Salva metadata da instalação."""
        try:
            cache_dir = self._get_installation_cache_dir(codinstalacao)
            os.makedirs(cache_dir, exist_ok=True)
            
            metadata["last_updated"] = datetime.now().isoformat()
            
            metadata_path = self._get_metadata_path(codinstalacao)
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logging.error(f"Erro ao salvar metadata para {codinstalacao}: {str(e)}")
    
    def save_cached_data(self, codinstalacao: str, file_path: str, extracted_data: Dict[str, Any], 
                        processing_stats: Dict[str, Any] = None) -> bool:
        """
        Salva dados extraídos no cache.
        
        Args:
            codinstalacao: Código da instalação
            file_path: Caminho do arquivo PDF original
            extracted_data: Dados extraídos da fatura
            processing_stats: Estatísticas do processamento
            
        Returns:
            bool: True se salvou com sucesso
        """
        try:
            filename = os.path.basename(file_path)
            periodo = self._extract_period_from_filename(filename)
            
            if not periodo:
                logging.warning(f"Não foi possível determinar período para {filename}")
                return False
            
            # Calcula hash do arquivo
            file_hash = self._calculate_file_hash(file_path)
            
            # Prepara dados do cache
            cache_data = {
                "file_info": {
                    "filename": filename,
                    "file_path": file_path,
                    "file_hash": file_hash,
                    "processed_at": datetime.now().isoformat(),
                    "parser_version": "v2.0"
                },
                "extracted_data": extracted_data,
                "processing_stats": processing_stats or {}
            }
            
            # Salva no cache
            cache_file_path = self._get_cache_file_path(codinstalacao, periodo)
            os.makedirs(os.path.dirname(cache_file_path), exist_ok=True)
            
            with open(cache_file_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            # Atualiza metadata
            metadata = self._load_metadata(codinstalacao)
            metadata["total_faturas_cached"] = metadata.get("total_faturas_cached", 0) + 1
            
            # Atualiza range de datas
            if not metadata["data_range"]["inicio"] or periodo < metadata["data_range"]["inicio"]:
                metadata["data_range"]["inicio"] = periodo
            if not metadata["data_range"]["fim"] or periodo > metadata["data_range"]["fim"]:
                metadata["data_range"]["fim"] = periodo
            
            self._save_metadata(codinstalacao, metadata)
            
            logging.info(f"Dados da fatura {filename} salvos no cache para instalação {codinstalacao}")
            return True
            
        except Exception as e:
            logging.error(f"Erro ao salvar no cache: {str(e)}")
            return False
    
    def load_cached_data_by_period(self, codinstalacao: str, periodo: str) -> Optional[Dict[str, Any]]:
        """
        Carrega dados do cache diretamente por período.
        
        Args:
            codinstalacao: Código da instalação  
            periodo: Período no formato YYYY-MM
            
        Returns:
            Dados extraídos se cache válido, None caso contrário
        """
        try:
            cache_file_path = self._get_cache_file_path(codinstalacao, periodo)
            
            if not os.path.exists(cache_file_path):
                return None
            
            # Carrega dados do cache
            with open(cache_file_path, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            return cached_data.get('extracted_data')
            
        except Exception as e:
            logging.error(f"Erro ao carregar cache por período {periodo}: {str(e)}")
            return None

    def load_cached_data(self, codinstalacao: str, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Carrega dados do cache se válidos.
        
        Args:
            codinstalacao: Código da instalação
            file_path: Caminho do arquivo PDF
            
        Returns:
            Dados extraídos se cache válido, None caso contrário
        """
        try:
            filename = os.path.basename(file_path)
            periodo = self._extract_period_from_filename(filename)
            
            if not periodo:
                return None
            
            cache_file_path = self._get_cache_file_path(codinstalacao, periodo)
            
            if not os.path.exists(cache_file_path):
                return None
            
            # Carrega dados do cache
            with open(cache_file_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Valida se cache é válido
            if self.is_cache_valid(cache_data, file_path):
                logging.info(f"Cache hit para {filename} (instalação: {codinstalacao})")
                return cache_data["extracted_data"]
            else:
                logging.info(f"Cache inválido para {filename}, será reprocessado")
                return None
                
        except Exception as e:
            logging.error(f"Erro ao carregar cache: {str(e)}")
            return None
    
    def is_cache_valid_by_period(self, codinstalacao: str, periodo: str) -> bool:
        """
        Verifica se o cache é válido para um período específico.
        
        Args:
            codinstalacao: Código da instalação
            periodo: Período no formato YYYY-MM
            
        Returns:
            bool: True se cache é válido
        """
        try:
            cache_file_path = self._get_cache_file_path(codinstalacao, periodo)
            
            if not os.path.exists(cache_file_path):
                return False
            
            # Carrega dados do cache
            with open(cache_file_path, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            # Verifica TTL
            processed_at = datetime.fromisoformat(cached_data["file_info"]["processed_at"])
            if datetime.now() - processed_at > timedelta(days=self.ttl_days):
                return False
            
            return True
            
        except Exception as e:
            logging.error(f"Erro ao verificar validade do cache para {periodo}: {str(e)}")
            return False

    def is_cache_valid(self, cache_data: Dict[str, Any], current_file_path: str) -> bool:
        """
        Verifica se o cache é válido.
        
        Args:
            cache_data: Dados do cache
            current_file_path: Caminho atual do arquivo
            
        Returns:
            bool: True se cache é válido
        """
        try:
            # Verifica se arquivo ainda existe
            if not os.path.exists(current_file_path):
                return False
            
            # Verifica TTL
            processed_at = datetime.fromisoformat(cache_data["file_info"]["processed_at"])
            if datetime.now() - processed_at > timedelta(days=self.ttl_days):
                return False
            
            # Verifica hash do arquivo
            current_hash = self._calculate_file_hash(current_file_path)
            cached_hash = cache_data["file_info"].get("file_hash")
            
            if current_hash and cached_hash and current_hash != cached_hash:
                return False
            
            return True
            
        except Exception as e:
            logging.error(f"Erro ao validar cache: {str(e)}")
            return False
    
    def clear_cache(self, codinstalacao: str = None, periodo: str = None) -> bool:
        """
        Remove cache específico ou global.
        
        Args:
            codinstalacao: Se especificado, remove apenas desta instalação
            periodo: Se especificado, remove apenas este período
            
        Returns:
            bool: True se removeu com sucesso
        """
        try:
            if codinstalacao and periodo:
                # Remove período específico
                cache_file = self._get_cache_file_path(codinstalacao, periodo)
                if os.path.exists(cache_file):
                    os.remove(cache_file)
                    logging.info(f"Cache removido: {codinstalacao}/{periodo}")
            elif codinstalacao:
                # Remove toda a instalação
                install_dir = self._get_installation_cache_dir(codinstalacao)
                if os.path.exists(install_dir):
                    import shutil
                    shutil.rmtree(install_dir)
                    logging.info(f"Cache da instalação {codinstalacao} removido")
            else:
                # Remove todo o cache
                if os.path.exists(self.cache_base_path):
                    import shutil
                    shutil.rmtree(self.cache_base_path)
                    os.makedirs(self.cache_base_path, exist_ok=True)
                    logging.info("Todo o cache foi limpo")
            
            return True
            
        except Exception as e:
            logging.error(f"Erro ao limpar cache: {str(e)}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas do cache.
        
        Returns:
            Dicionário com estatísticas do cache
        """
        try:
            stats = {
                "cache_base_path": self.cache_base_path,
                "total_installations": 0,
                "total_cached_files": 0,
                "cache_size_mb": 0,
                "installations": {}
            }
            
            if not os.path.exists(self.cache_base_path):
                return stats
            
            # Calcula tamanho total
            total_size = 0
            for root, dirs, files in os.walk(self.cache_base_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.exists(file_path):
                        total_size += os.path.getsize(file_path)
            
            stats["cache_size_mb"] = round(total_size / (1024 * 1024), 2)
            
            # Processa cada instalação
            for install_dir in os.listdir(self.cache_base_path):
                install_path = os.path.join(self.cache_base_path, install_dir)
                if os.path.isdir(install_path):
                    stats["total_installations"] += 1
                    
                    metadata = self._load_metadata(install_dir)
                    cached_files = len([f for f in os.listdir(install_path) 
                                     if f.endswith('_processed.json')])
                    
                    stats["total_cached_files"] += cached_files
                    stats["installations"][install_dir] = {
                        "cached_files": cached_files,
                        "data_range": metadata.get("data_range", {}),
                        "last_updated": metadata.get("last_updated")
                    }
            
            return stats
            
        except Exception as e:
            logging.error(f"Erro ao obter estatísticas do cache: {str(e)}")
            return {"error": str(e)}


# Instância global do cache
_cache_instance = None

def get_cache_instance() -> FaturaCache:
    """Retorna instância global do cache (singleton)."""
    global _cache_instance
    if _cache_instance is None:
        # Configurações vindas de variáveis de ambiente
        cache_path = os.environ.get('FATURA_CACHE_PATH')
        ttl_days = int(os.environ.get('FATURA_CACHE_TTL_DAYS', 365))
        max_size = float(os.environ.get('FATURA_CACHE_MAX_SIZE_GB', 5.0))
        
        _cache_instance = FaturaCache(cache_path, ttl_days, max_size)
    
    return _cache_instance