# invoice_locator.py
"""
Módulo para localizar faturas com fallback entre armazenamento local e Google Drive.
"""

import os
import glob
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from .google_drive_client import create_google_drive_client, GoogleDriveClient

class InvoiceLocator:
    """Classe para localizar faturas com sistema de fallback"""
    
    def __init__(self, enable_google_drive_fallback: bool = True, cache_downloads: bool = True):
        """
        Inicializa o localizador de faturas
        
        Args:
            enable_google_drive_fallback: Se deve usar Google Drive como fallback
            cache_downloads: Se deve fazer cache local dos arquivos baixados do Drive
        """
        self.enable_google_drive_fallback = enable_google_drive_fallback
        self.cache_downloads = cache_downloads
        self.google_drive_client: Optional[GoogleDriveClient] = None
        
        if self.enable_google_drive_fallback:
            try:
                self.google_drive_client = create_google_drive_client()
                if not self.google_drive_client.is_available():
                    logging.warning("Google Drive client não disponível, usando apenas busca local")
                    self.enable_google_drive_fallback = False
            except Exception as e:
                logging.warning(f"Erro ao inicializar Google Drive client: {e}")
                self.enable_google_drive_fallback = False
    
    def find_invoice_files(self, codinstalacao: str, data_inicio: str = None, data_fim: str = None) -> List[Dict]:
        """
        Busca arquivos de faturas para uma instalação
        
        Args:
            codinstalacao: Código da instalação
            data_inicio: Data de início no formato MES-ANO (opcional)
            data_fim: Data de fim no formato MES-ANO (opcional)
            
        Returns:
            Lista de dicionários com informações dos arquivos encontrados:
            {
                'arquivo': str,           # Nome do arquivo
                'caminho_completo': str,  # Caminho completo do arquivo
                'referencia': str,        # Referência MES-ANO extraída
                'fonte': str,            # 'local' ou 'google_drive'
                'drive_file_id': str     # ID do arquivo no Drive (se aplicável)
            }
        """
        arquivos_encontrados = []
        
        # 1. Busca local
        arquivos_locais = self._find_local_files(codinstalacao, data_inicio, data_fim)
        arquivos_encontrados.extend(arquivos_locais)
        
        # 2. Busca no Google Drive (fallback)
        if self.enable_google_drive_fallback and self.google_drive_client:
            arquivos_drive = self._find_google_drive_files(codinstalacao, data_inicio, data_fim)
            
            # Remove duplicatas (arquivos já encontrados localmente)
            arquivos_locais_refs = {arq['referencia'] for arq in arquivos_locais if arq.get('referencia')}
            
            for arquivo_drive in arquivos_drive:
                ref = arquivo_drive.get('referencia')
                if not ref or ref not in arquivos_locais_refs:
                    arquivos_encontrados.append(arquivo_drive)
                else:
                    logging.debug(f"Arquivo {arquivo_drive['arquivo']} já existe localmente, ignorando versão do Drive")
        
        logging.info(f"Total de {len(arquivos_encontrados)} arquivos encontrados para instalação {codinstalacao}")
        return arquivos_encontrados
    
    def _find_local_files(self, codinstalacao: str, data_inicio: str = None, data_fim: str = None) -> List[Dict]:
        """Busca arquivos locais na pasta faturas_edp"""
        pasta_instalacao = os.path.join("faturas_edp", codinstalacao)
        padrao_arquivos = os.path.join(pasta_instalacao, "*.pdf")
        arquivos_pdf = glob.glob(padrao_arquivos)
        
        arquivos_encontrados = []
        
        # Converte datas para filtros
        dt_ini, dt_fim = None, None
        if data_inicio and data_fim:
            dt_ini = self._ref_to_date(data_inicio)
            dt_fim = self._ref_to_date(data_fim)
            if dt_ini > dt_fim:
                dt_ini, dt_fim = dt_fim, dt_ini
        
        for arquivo in arquivos_pdf:
            nome_arquivo = os.path.basename(arquivo)
            ref = self._extract_reference_from_filename(nome_arquivo)
            
            # Aplica filtro de data se especificado
            if dt_ini and dt_fim and ref:
                ref_dt = self._ref_to_date(ref)
                if not (dt_ini <= ref_dt <= dt_fim):
                    continue
            
            arquivos_encontrados.append({
                'arquivo': nome_arquivo,
                'caminho_completo': arquivo,
                'referencia': ref,
                'fonte': 'local',
                'drive_file_id': None
            })
        
        logging.info(f"Encontrados {len(arquivos_encontrados)} arquivos locais para instalação {codinstalacao}")
        return arquivos_encontrados
    
    def _find_google_drive_files(self, codinstalacao: str, data_inicio: str = None, data_fim: str = None) -> List[Dict]:
        """Busca arquivos no Google Drive"""
        if not self.google_drive_client:
            return []
        
        arquivos_drive = self.google_drive_client.search_invoice_files(codinstalacao)
        arquivos_encontrados = []
        
        # Converte datas para filtros
        dt_ini, dt_fim = None, None
        if data_inicio and data_fim:
            dt_ini = self._ref_to_date(data_inicio)
            dt_fim = self._ref_to_date(data_fim)
            if dt_ini > dt_fim:
                dt_ini, dt_fim = dt_fim, dt_ini
        
        for arquivo_drive in arquivos_drive:
            nome_arquivo = arquivo_drive['name']
            ref = self.google_drive_client.extract_reference_from_filename(nome_arquivo)
            
            # Aplica filtro de data se especificado
            if dt_ini and dt_fim and ref:
                ref_dt = self._ref_to_date(ref)
                if not (dt_ini <= ref_dt <= dt_fim):
                    continue
            
            arquivos_encontrados.append({
                'arquivo': nome_arquivo,
                'caminho_completo': None,  # Será preenchido quando baixar
                'referencia': ref,
                'fonte': 'google_drive',
                'drive_file_id': arquivo_drive['id']
            })
        
        logging.info(f"Encontrados {len(arquivos_encontrados)} arquivos no Google Drive para instalação {codinstalacao}")
        return arquivos_encontrados
    
    def get_file_path(self, arquivo_info: Dict) -> Optional[str]:
        """
        Obtém o caminho do arquivo, baixando do Google Drive se necessário
        
        Args:
            arquivo_info: Informações do arquivo retornadas por find_invoice_files()
            
        Returns:
            Caminho para o arquivo local ou None se erro
        """
        if arquivo_info['fonte'] == 'local':
            return arquivo_info['caminho_completo']
        
        elif arquivo_info['fonte'] == 'google_drive':
            if not self.google_drive_client:
                logging.error("Google Drive client não disponível")
                return None
            
            # Determina onde salvar o arquivo
            download_path = None
            if self.cache_downloads:
                # Salva na pasta local para futuras buscas
                codinstalacao = self._extract_codinstalacao_from_filename(arquivo_info['arquivo'])
                if codinstalacao:
                    download_path = os.path.join("faturas_edp", codinstalacao)
            
            # Baixa o arquivo
            caminho_arquivo = self.google_drive_client.download_file(
                arquivo_info['drive_file_id'],
                arquivo_info['arquivo'],
                download_path
            )
            
            return caminho_arquivo
        
        return None
    
    def _extract_reference_from_filename(self, filename: str) -> Optional[str]:
        """Extrai referência MES-ANO do nome do arquivo"""
        # Usa o mesmo método do Google Drive client
        if self.google_drive_client:
            return self.google_drive_client.extract_reference_from_filename(filename)
        
        # Implementação simples local
        import re
        patterns = [
            r'[_-]([A-Z]{3}-\d{4})',
            r'([A-Z]{3}-\d{4})[_-]',
            r'([A-Z]{3}-\d{4})'
        ]
        
        filename_upper = filename.upper()
        for pattern in patterns:
            match = re.search(pattern, filename_upper)
            if match:
                return match.group(1)
        return None
    
    def _extract_codinstalacao_from_filename(self, filename: str) -> Optional[str]:
        """Extrai código da instalação do nome do arquivo"""
        import re
        # Padrão para códigos de instalação (geralmente 10 dígitos)
        pattern = r'(\d{10})'
        match = re.search(pattern, filename)
        if match:
            return match.group(1)
        return None
    
    def _ref_to_date(self, ref: str) -> datetime:
        """Converte referência MES-ANO para datetime"""
        MES_MAP = {
            "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4,
            "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8,
            "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12
        }
        
        try:
            mes, ano = ref.upper().split("-")
            return datetime(int(ano), MES_MAP[mes], 1)
        except:
            return datetime.min


# Instância global para reutilização
_invoice_locator = None

def get_invoice_locator(enable_google_drive: bool = None, cache_downloads: bool = None) -> InvoiceLocator:
    """
    Obtém instância do localizador de faturas (singleton)
    """
    global _invoice_locator
    
    # Usa variáveis de ambiente como padrão
    if enable_google_drive is None:
        enable_google_drive = os.getenv('ENABLE_GOOGLE_DRIVE_FALLBACK', 'true').lower() == 'true'
    
    if cache_downloads is None:
        cache_downloads = os.getenv('CACHE_GOOGLE_DRIVE_DOWNLOADS', 'true').lower() == 'true'
    
    if _invoice_locator is None:
        _invoice_locator = InvoiceLocator(enable_google_drive, cache_downloads)
    
    return _invoice_locator