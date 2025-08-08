#!/usr/bin/env python3
"""
Script para obter código de autorização Google Drive
"""
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)

# Define redirect_uri explicitamente
flow.redirect_uri = 'http://localhost'

auth_url, _ = flow.authorization_url(
    access_type='offline',
    include_granted_scopes='true',
    prompt='consent'
)

print("📋 Abra esta URL no navegador e copie o código:")
print(f"🔗 {auth_url}")
print()
print("📝 Depois execute:")
print("python complete_auth.py COLE_O_CODIGO_AQUI")