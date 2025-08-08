#!/usr/bin/env python3
"""
Script para completar autenticação Google Drive com código
"""
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

if len(sys.argv) != 2:
    print("❌ Uso: python complete_auth.py CODIGO_DE_AUTORIZACAO")
    sys.exit(1)

auth_code = sys.argv[1].strip()

try:
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    flow.redirect_uri = 'http://localhost'
    flow.fetch_token(code=auth_code)
    creds = flow.credentials
    
    with open("token.json", 'w') as token:
        token.write(creds.to_json())
    
    print("✅ Token salvo em token.json")
    print("🚀 Google Drive configurado com sucesso!")
    
except Exception as e:
    print(f"❌ Erro: {e}")
    print("💡 Certifique-se de copiar o código completo da URL")