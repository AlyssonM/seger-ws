# src/parser.py
"""
Módulo responsável por analisar e extrair informações de documentos,
como faturas em formato PDF.

Inclui funcionalidades para leitura de PDFs, extração de texto e
processamento para obter dados estruturados.
"""
from typing import Any, Dict, List, Optional
import os, json
import PyPDF2
from google import genai
from google.genai import types
from src.parser_regex import extrair_dados_completos_da_fatura_regex
from datetime import date
import re
import logging

parser_logger = logging.getLogger("parser")
parser_logger.setLevel(logging.INFO)
handler = logging.FileHandler("src/logs/parser.log")
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
parser_logger.addHandler(handler)

# 1) Cliente Gemini configurado via API key
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"), http_options=types.HttpOptions(api_version='v1alpha'))

def _extrair_texto_pdf(pdf_path: str) -> str:
    """
        Extrai o texto contido em um arquivo PDF.

        Processa cada página do arquivo PDF especificado e concatena o texto
        extraído de cada uma.

        Args:
            pdf_path: O caminho para o arquivo PDF a ser processado.

        Returns:
            Uma string contendo todo o texto extraído do PDF, com as páginas
            separadas por quebras de linha.
    """
    texto = []
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            texto.append(page.extract_text() or "")
    
    return "\n".join(texto)

def extrair_dados_completos_da_fatura(
    pdf_path: str, 
    via_regex: bool = True
) -> Dict[str, Any]:
    """
        Extrai dados completos de uma fatura em formato PDF.

        Esta função analisa o conteúdo da fatura PDF e extrai informações
        estruturadas relevantes, como dados do cliente, valores, consumo,
        etc. A extração pode ser realizada via regex ou outros métodos.

        Args:
            pdf_path: O caminho para o arquivo PDF da fatura.
            via_regex: Booleano indicando se a extração deve usar expressões
                    regulares (regex). O valor padrão é True.

        Returns:
            Um dicionário contendo os dados extraídos da fatura. A estrutura
            do dicionário depende das informações encontradas e do método de
            extração utilizado.

        Raises:
            FileNotFoundError: Se o arquivo PDF especificado não for encontrado.
            ValueError: Se o conteúdo do PDF não puder ser processado como fatura.
            # Adicione outras exceções relevantes aqui.
    """
    # 1) Extrar os dados do PDF via texto
    texto = _extrair_texto_pdf(pdf_path)
    # logging.info(f"texto:\n{texto}\n\n")
    if via_regex:
        try:
            resultado = extrair_dados_completos_da_fatura_regex(texto)
            return resultado
        except Exception as e:
            import traceback
            traceback_str = traceback.format_exc()
            parser_logger.error("❌ ERRO ao aplicar regex:\n", traceback_str)
            return {"error": f"Erro ao aplicar regex: {str(e)}"}

    # 2) Monta conteúdo no formato chat
    system_prompt = """
    Você é um assistente especializado em extrair dados de faturas de energia elétrica da EDP.

    Retorne **somente** um JSON com a estrutura abaixo, preenchendo cada campo que aparecer na fatura
    (e omitindo chaves cujo dado não exista). 

    **Regras obrigatórias:**
    - Use ponto como separador decimal.
    - Não inclua unidades nos números (como kWh, R$ ou kW).
    - Não acrescente nenhum texto fora do JSON.
    - **Não** adicione crase tripla (```json) antes ou depois do JSON.

    Estrutura esperada:

    {
    "identificacao": {
        "numero_instalacao": <string>,
        "numero_cliente": <string>,
        "mes_referencia": <string>,  // formato mm/aaaa
        "grupo_tarifario": <string>,
        "classe": <string>,
        "endereco": <string>,        // rua, número, bairro, cidade, CEP
        "tensao": <string>,          // ex: "11400"
        "tensaoUnid": <string>,      // "V" ou "kV"
        "nivel_tensao": <string>,    // baixa tensão, média tensão, alta tensão
        "unidade": <string>          // nome da unidade consumidora
    },

    "leituras": {
        "leitura_inicio": "dd/mm/aaaa",
        "leitura_fim": "dd/mm/aaaa",
        "leitura_anterior_kwh": <number>,
        "leitura_atual_kwh": <number>
    },

    "consumo_ativo": {
        "ponta_kwh": <number>,
        "fora_ponta_kwh": <number>,
        "intermediario_kwh": <number>,   // apenas se existir
        "total_kwh": <number>
    },

    "demanda": {
        "maxima": [
        { "periodo": "ponta", "valor_kw": <number> },
        { "periodo": "fora_ponta", "valor_kw": <number> }
        ],
        "contratada_kw": <number>,
        "nao_utilizada_kw": <number>,
        "dmcr": [
        { "periodo": "ponta", "valor_kw": <number> },
        { "periodo": "fora_ponta", "valor_kw": <number> }
        ],
        "fora_ponta_kw": <number>,       // valor da demanda faturada (separado do 'maxima')
        "tarifa_unitaria": <number>,     // valor unitário da demanda
        "valor_total": <number>          // valor total cobrado pela demanda
    },

    "energia_reativa": {
        "ponta_kvarh": <number>,
        "fora_ponta_kvarh": <number>,
        "total_kvarh": <number>,
        "excedente": {
        "ponta_kwh": <number>,
        "fora_ponta_kwh": <number>,
        "total_kwh": <number>
        }
    },

    "tarifas": [
        {
        "descricao": <string>,
        "periodo": <string>,  // ponta, fora_ponta, intermediario, etc.
        "quantidade": <number>,
        "tarifa_unitaria": <number>,
        "valor_total": <number>
        }
    ],

    "componentes_extras": [
        {
        "descricao": "Contribuição de Ilum. Pública - Lei Municipal",
        "quantidade": <number>,
        "tarifa_unitaria": <number>,
        "valor_total": <number>,
        "valor_impostos": <number>
        },
        {
        "descricao": "Bandeira Tarifária",
        "quantidade": <number>,
        "tarifa_unitaria": <number>,
        "valor_total": <number>,
        "valor_impostos": <number>
        }
    ],

    "impostos": [
        {
        "nome": <string>,                // PIS, COFINS, ICMS
        "base_calculo": <number>,
        "aliquota": <number>,
        "valor": <number>
        }
    ],

    "valores_totais": {
        "subtotal_servicos": <number>,
        "subtotal_encargos": <number>,
        "valor_total_fatura": <number>
    }
    }
    """

    contents = types.Content(
        role='user',
        parts=[
            types.Part.from_text(text=system_prompt.strip()),
            types.Part.from_text(text=texto[:100000])]
    )
    
    # 3) Chamada ao Gemini via generate_content
    response = client.models.generate_content(
        model="gemini-2.0-flash-001",
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=5000
        )
    )

    # 4) Parse do JSON retornado
    try:
        clean_text = re.sub(r"^```json\s*|\s*```$", "", response.text.strip(), flags=re.MULTILINE)
        parser_logger.info(f"resposta do modelo:\n{clean_text}")
        return json.loads(clean_text)
    except json.JSONDecodeError:
        parser_logger.error("❌ JSON mal formatado retornado pelo modelo:\n", response.text)
        return {"error": "JSON decoding error", "raw_response": response.text}
