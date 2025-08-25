# google_drive_client.py
"""
Módulo para integração com Google Drive API para buscar PDFs de faturas como fallback.
"""

import os
import io
import logging
import time
from typing import List, Optional, Dict, Any
from datetime import datetime
import tempfile

try:
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.http import MediaIoBaseDownload
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    GOOGLE_DRIVE_AVAILABLE = False
    logging.warning("Google Drive dependencies not available. Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")

# Escopos necessários para acessar o Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

class GoogleDriveClient:
    """Cliente para buscar faturas no Google Drive como fallback"""
    
    def __init__(self, credentials_path: str = "credentials.json", token_path: str = "token.json"):
        """
        Inicializa o cliente do Google Drive
        
        Args:
            credentials_path: Caminho para o arquivo credentials.json do Google Cloud
            token_path: Caminho para armazenar o token de acesso
        """
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        
        if not GOOGLE_DRIVE_AVAILABLE:
            logging.error("Google Drive client não disponível. Instale as dependências necessárias.")
            return
            
        self._authenticate()
    
    def _authenticate(self):
        """Autentica com a API do Google Drive"""
        creds = None
        
        # Verifica se já existe um token salvo
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        
        # Se não há credenciais válidas disponíveis, solicita login
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    logging.error(f"Arquivo de credenciais {self.credentials_path} não encontrado.")
                    return
                
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                # Configuração para ambiente Cloud Workstation
                try:
                    # Tenta autenticação local primeiro
                    creds = flow.run_local_server(
                        port=8080, 
                        open_browser=False,
                        bind_addr='0.0.0.0'
                    )
                    logging.info("Autenticação OAuth local concluída com sucesso")
                except Exception as e:
                    logging.error(f"Erro na autenticação OAuth local: {e}")
                    try:
                        # Fallback para console (método correto)
                        auth_url, _ = flow.authorization_url(prompt='consent')
                        logging.error(f"Abra esta URL no navegador para autorizar: {auth_url}")
                        return  # Sai da função se não conseguir autenticar
                    except Exception as e2:
                        logging.error(f"Erro na autenticação manual: {e2}")
                        return
            
            # Salva as credenciais para próximas execuções
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())
        
        self.service = build('drive', 'v3', credentials=creds)
        logging.info("Cliente Google Drive autenticado com sucesso")
    
    def is_available(self) -> bool:
        """Verifica se o cliente está disponível e autenticado"""
        return GOOGLE_DRIVE_AVAILABLE and self.service is not None
    
    def search_invoice_files(self, codinstalacao: str, folder_name: str = "Faturas EDP") -> List[Dict[str, Any]]:
        """
        Busca arquivos PDF de faturas no Google Drive usando estrutura de pastas por instalação
        
        Args:
            codinstalacao: Código da instalação
            folder_name: Nome da pasta raiz no Drive (padrão: "Faturas EDP")
            
        Returns:
            Lista de arquivos encontrados com metadados
        """
        if not self.is_available():
            return []
        
        try:
            # Primeiro, encontra a pasta raiz "Faturas EDP"
            root_folder_query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
            root_folder_results = self.service.files().list(q=root_folder_query).execute()
            root_folders = root_folder_results.get('files', [])
            
            if not root_folders:
                logging.warning(f"Pasta raiz '{folder_name}' não encontrada no Google Drive")
                return []
            
            root_folder_id = root_folders[0]['id']
            
            # Busca a subpasta com o código da instalação
            instalacao_folder_query = (
                f"'{root_folder_id}' in parents and "
                f"name='{codinstalacao}' and "
                f"mimeType='application/vnd.google-apps.folder'"
            )
            
            instalacao_folder_results = self.service.files().list(q=instalacao_folder_query).execute()
            instalacao_folders = instalacao_folder_results.get('files', [])
            
            if not instalacao_folders:
                logging.warning(f"Pasta da instalação '{codinstalacao}' não encontrada em '{folder_name}'")
                return []
            
            instalacao_folder_id = instalacao_folders[0]['id']
            
            # Busca todos os PDFs na pasta da instalação
            file_query = (
                f"'{instalacao_folder_id}' in parents and "
                f"mimeType='application/pdf'"
            )
            
            results = self.service.files().list(
                q=file_query,
                fields="files(id,name,size,modifiedTime,parents)"
            ).execute()
            
            files = results.get('files', [])
            logging.info(f"Encontrados {len(files)} arquivos no Google Drive para instalação {codinstalacao} (pasta: {folder_name}/{codinstalacao})")
            
            return files
            
        except Exception as e:
            logging.error(f"Erro ao buscar arquivos no Google Drive: {str(e)}")
            return []
    
    def download_file(self, file_id: str, filename: str, download_path: str = None) -> Optional[str]:
        """
        Baixa um arquivo do Google Drive com retry e melhor tratamento de erros
        
        Args:
            file_id: ID do arquivo no Google Drive
            filename: Nome do arquivo
            download_path: Pasta de destino (se None, usa tempfile)
            
        Returns:
            Caminho do arquivo baixado ou None se erro
        """
        if not self.is_available():
            return None
        
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                request = self.service.files().get_media(fileId=file_id)
                
                if download_path:
                    os.makedirs(download_path, exist_ok=True)
                    file_path = os.path.join(download_path, filename)
                else:
                    # Usa pasta temporária
                    temp_dir = tempfile.mkdtemp()
                    file_path = os.path.join(temp_dir, filename)
                
                # Remove arquivo existente se houver
                if os.path.exists(file_path):
                    os.remove(file_path)
                
                with io.FileIO(file_path, 'wb') as fh:
                    downloader = MediaIoBaseDownload(fh, request, chunksize=1024*1024)  # 1MB chunks
                    done = False
                    while done is False:
                        try:
                            status, done = downloader.next_chunk()
                            if status:
                                logging.debug(f"Download progress: {int(status.progress() * 100)}%")
                        except Exception as chunk_error:
                            logging.warning(f"Erro no chunk, tentando continuar: {str(chunk_error)}")
                            break
                
                # Verifica se o arquivo foi baixado com sucesso
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    logging.info(f"Arquivo {filename} baixado para {file_path}")
                    return file_path
                else:
                    raise Exception("Arquivo baixado está vazio ou não foi criado")
                    
            except Exception as e:
                logging.error(f"Tentativa {attempt + 1}/{max_retries} - Erro ao baixar arquivo {filename}: {str(e)}")
                
                if attempt < max_retries - 1:
                    logging.info(f"Aguardando {retry_delay}s antes de tentar novamente...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logging.error(f"Falha definitiva ao baixar arquivo {filename} após {max_retries} tentativas")
                    return None
    
    def extract_reference_from_filename(self, filename: str) -> Optional[str]:
        """
        Extrai a referência (MÊS-ANO) do nome do arquivo
        
        Args:
            filename: Nome do arquivo
            
        Returns:
            Referência extraída ou None
        """
        # Padrões possíveis:
        # fatura_JAN-2025.pdf
        # 0000144112_JAN-2025.pdf
        # Fatura_EDP_JAN-2025_0000144112.pdf
        
        import re
        
        # Padrão para extrair MES-ANO
        patterns = [
            r'[_-]([A-Z]{3}-\d{4})',  # _JAN-2025 ou -JAN-2025
            r'([A-Z]{3}-\d{4})[_-]',  # JAN-2025_ ou JAN-2025-
            r'([A-Z]{3}-\d{4})'       # JAN-2025 sozinho
        ]
        
        filename_upper = filename.upper()
        
        for pattern in patterns:
            match = re.search(pattern, filename_upper)
            if match:
                return match.group(1)
        
        return None
    
    def search_and_download_excel_file(self, filename: str = "Consumo_Governo_ES_EDP_21-25_Calculos.xlsx", download_path: str = None) -> Optional[str]:
        """
        Busca e baixa arquivo Excel do Google Drive
        
        Args:
            filename: Nome do arquivo Excel
            download_path: Pasta onde baixar o arquivo (padrão: temp)
            
        Returns:
            Caminho completo do arquivo baixado ou None se não encontrado
        """
        if not self.is_available():
            return None
        
        try:
            # Busca o arquivo Excel no Drive
            query = f"name='{filename}' and mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'"
            results = self.service.files().list(q=query).execute()
            files = results.get('files', [])
            
            if not files:
                logging.warning(f"Arquivo Excel '{filename}' não encontrado no Google Drive")
                return None
            
            file_id = files[0]['id']
            logging.info(f"Arquivo Excel '{filename}' encontrado no Google Drive")
            
            # Define pasta de download
            if download_path is None:
                download_path = tempfile.gettempdir()
            
            # Baixa o arquivo
            downloaded_path = self.download_file(file_id, filename, download_path)
            return downloaded_path
            
        except Exception as e:
            logging.error(f"Erro ao buscar/baixar arquivo Excel '{filename}': {str(e)}")
            return None


def create_google_drive_client() -> GoogleDriveClient:
    """
    Factory function para criar cliente Google Drive
    """
    credentials_path = os.getenv('GOOGLE_DRIVE_CREDENTIALS_PATH', 'credentials.json')
    token_path = os.getenv('GOOGLE_DRIVE_TOKEN_PATH', 'token.json')
    
    return GoogleDriveClient(credentials_path, token_path)