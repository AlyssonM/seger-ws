# seger/parser.py
from typing import Any, Dict
import os, json
import PyPDF2
from google import genai
from google.genai import types
from src.parser_regex import extrair_dados_completos_da_fatura_regex
# 1) Cliente Gemini configurado via API key
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"), http_options=types.HttpOptions(api_version='v1alpha'))



def _extrair_texto_pdf(pdf_path: str) -> str:
    texto = []
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            texto.append(page.extract_text() or "")
    return "\n".join(texto)

def extrair_dados_completos_da_fatura(pdf_path: str, via_regex: bool = True) -> Dict[str, Any]:
    # 2) Extrai texto do PDF
    texto = _extrair_texto_pdf(pdf_path)
    # print(f"texto:\n{texto}\n\n")
    if via_regex:
        return extrair_dados_completos_da_fatura_regex(texto)
    # 3) Monta conteúdo no formato chat
    system_prompt = """
      Você é um assistente especializado em extrair dados de faturas de energia elétrica da EDP.
      Retorne **somente** um JSON com a estrutura abaixo, preenchendo cada campo que aparecer na fatura
      (e omitindo chaves cujo dado não exista). Use ponto como separador decimal, não inclua unidades
      e não acrescente nenhum texto fora do JSON.

      {
        "identificacao": {
          "numero_instalacao":         <string>,
          "numero_cliente":            <string>,
          "mes_referencia":            <string>,      # formato mm/aaaa
          "grupo_tarifario":           <string>,
          "classe":                    <string>
        },

        "leituras": {
          "leitura_inicio":            "dd/mm/aaaa",
          "leitura_fim":               "dd/mm/aaaa",
          "leitura_anterior_kwh":      <number>,
          "leitura_atual_kwh":         <number>
        },

        "consumo_ativo": {
          "ponta_kwh":                 <number>,
          "fora_ponta_kwh":            <number>,
          "intermediario_kwh":         <number>,      # caso exista
          "total_kwh":                 <number>
        },

        "demanda": {
          "maxima": [
            { "periodo": "ponta",       "valor_kw": <number> },
            { "periodo": "fora_ponta",  "valor_kw": <number> }
          ],
          "contratada_kw":             <number>,
          "nao_utilizada_kw":          <number>,
          "dmcr": [
            { "periodo": "ponta",       "valor_kw": <number> },
            { "periodo": "fora_ponta",  "valor_kw": <number> }
          ]
        },

        "energia_reativa": {
          "ponta_kvarh":               <number>,
          "fora_ponta_kvarh":          <number>,
          "total_kvarh":               <number>,
          "excedente": {
            "ponta_kwh":               <number>,
            "fora_ponta_kwh":          <number>,
            "total_kwh":               <number>
          }
        },

        "tarifas": [
          { "descricao": <string>, "periodo": <string>, "quantidade": <number>, "tarifa_unitaria": <number>, "valor_total": <number> }
        ],

        "impostos": [
          { "nome": <string>, "base_calculo": <number>, "aliquota": <number>, "valor": <number> }
        ],

        "valores_totais": {
          "subtotal_servicos":         <number>,
          "subtotal_encargos":         <number>,
          "valor_total_fatura":        <number>
        }
      }
      """

    contents = types.Content(
        role='user',
        parts=[
            types.Part.from_text(text=system_prompt.strip()),
            types.Part.from_text(text=texto[:100000])]
    )
    
    # 4) Chamada ao Gemini via generate_content
    # response = client.models.generate_content(
    #     model="gemini-2.0-flash-001",
    #     contents=contents,
    #     config=types.GenerateContentConfig(
    #         temperature=0.0,
    #         max_output_tokens=1200
    #     )
    # )
    data_json = extrair_dados_completos_da_fatura_regex(texto)
    print(f"resposta com regex:\n{data_json}")
    
    # 5) Parse do JSON retornado
    # print(f"resposta do modelo:\n{response.text}")
    try:
        # return json.loads(response.text)
        return data_json
    except json.JSONDecodeError:
        # return {"raw": response.text}
        return {"error": "JSON decoding error"}
