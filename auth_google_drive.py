#!/usr/bin/env python3
"""
Script para autenticação manual do Google Drive
Execute este script para gerar o token.json necessário
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def authenticate():
    """Autentica e gera token.json"""
    
    credentials_path = "credentials.json"
    token_path = "token.json"
    
    if not os.path.exists(credentials_path):
        print(f"❌ Arquivo {credentials_path} não encontrado!")
        return
    
    print("🔐 Iniciando autenticação Google Drive...")
    
    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
    
    # Gera URL de autorização
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    print(f"\n📋 Abra esta URL no seu navegador:")
    print(f"🔗 {auth_url}")
    
    print(f"\n📝 Após autorizar, copie o código de autorização e cole aqui:")
    auth_code = input("Código: ").strip()
    
    try:
        # Troca código por token
        flow.fetch_token(code=auth_code)
        creds = flow.credentials
        
        # Salva token
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
        
        print(f"✅ Token salvo em {token_path}")
        print("🚀 Agora você pode usar o Google Drive na API!")
        
    except Exception as e:
        print(f"❌ Erro ao processar código: {e}")

if __name__ == "__main__":
    authenticate()