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
            logging.error("❌ ERRO ao aplicar regex:\n", traceback_str)
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
        logging.info(f"resposta do modelo:\n{clean_text}")
        return json.loads(clean_text)
    except json.JSONDecodeError:
        logging.error("❌ JSON mal formatado retornado pelo modelo:\n", response.text)
        return {"error": "JSON decoding error", "raw_response": response.text}

def analisar_eficiencia_energetica(
    fatura_dados: List[Dict[str, Any]],
    tarifas,
    tarifa_ere,
    tarifas_atualizado,
    tarifa_ere_atualizado,
    demanda_verde_otima,
    demanda_azul_p_otima,
    demanda_azul_fp_otima
) -> Dict[str, Any]:
    """
    Reproduz o cálculo da planilha 'Projeto Análise Tarifária – SEGER',
    com base nos dados das faturas de energia
    Monta as tabelas necessárias para a automação de geração do relatório

    Args:
        fatura_dados: Um dicionário contendo os dados estruturados extraídos
                      de um conjunto de faturas de energia, tipicamente obtidos da função
                      `extrair_dados_completos_da_fatura`.
        tarifas: Dicionário contendo os valores das tarifas referentes ao período de
                 de faturamento dos dados para a modalidade contratada (Azul, verde, etc..)
        tarifa_ere: Dicionário contendo os valores da tarifa ERE referentes ao período de
                    de faturamento dos dados para a modalidade contratada (Azul, verde, etc..)
        tarifas_atualizado: Dicionário contendo os valores das tarifas referentes ao período corrente
                            de faturamento da legislação para a modalidade contratada (Azul, verde, etc..)
        tarifa_ere_atualizado: Dicionário contendo os valores da tarifa ERE referente ao período corrente
                               de faturamento da legislação para a modalidade contratada (Azul, verde, etc..)
        demanda_verde_otima: demanda ótima para a modalidade verde
        demanda_azul_p_otima: demanda ótima para a modalidade azul (ponta)
        demanda_azul_fp_otima: demanda ótima para a modalidade azul (fora ponta)
    
    Returns:
        Um dicionário contendo os dados estruturados gerados a partir de um conjunto de faturas de energia,
        contendo as tabelas necessárias para a automação de geração do relatório.
    """
    from .utils.tarifas import (
        calcular_tarifa_verde,
        calcular_tarifa_azul,
        calcular_tarifa_bt,
    )
    from .utils.faturamento import (
        _pega_componente,
        gerar_resumo_proposta,
        gerar_dados_contextuais_integrado,
        formatar,
        format_real,
        format_kw,
        media_impostos
    )

    impostos = media_impostos(fatura_dados)
    pis_aliq = impostos["pis"]
    cofins_aliq = impostos["cofins"]
    icms_aliq = impostos["icms"]

    res: Dict[str, Any] = {
        "tabela_consumo": [],
        "tabela_tarifas": [],
        "tabela_ajuste": [],
        "tabela_12meses_otimizados": [],
        "tabela_contrato_comparado": [],
        "resumo_proposta": [],
    }

    # --- Tabela Tarifas ---
    def add_tarifa(grupo, t):
        def taxa(x): return f"{x:.5f}".replace('.', ',')
        def demanda(x): return f"{x:.2f}".replace('.', ',')
        consumo_fp = taxa(t.get("TEforaPonta", 0.0) + t.get("TUSDforaPonta", 0.0))
        consumo_p = taxa(t.get("TEponta", 0.0) + t.get("TUSDponta", 0.0))
        tarifa = {
            "grupo": grupo,
            "consumo_ponta": consumo_p if grupo != "BT Optante B3" else consumo_fp,
            "consumo_fora_ponta": consumo_fp,
            "demanda_ponta": demanda(t.get("DemandaPonta", 0.0)) if grupo == "A AZUL A4" else "-",
            "demanda_fora": demanda(t.get("DemandaForaPonta", 0.0)) if grupo != "BT Optante B3" else "-",
            "ere": str(tarifa_ere),
            "pis": f"{pis_aliq:.2f}".replace('.', ','),
            "cofins": f"{cofins_aliq:.2f}".replace('.', ','),
            "icms": f"{icms_aliq:.2f}".replace('.', ',')
        }
        res["tabela_tarifas"].append(tarifa)

    for grupo, t in {
        "A VERDE A4": tarifas_atualizado.get("verde", {}),
        "A AZUL A4": tarifas_atualizado.get("azul", {}),
        "BT Optante B3": tarifas_atualizado.get("convencional", {})
    }.items():
        add_tarifa(grupo, t)

    # --- Tabela Consumo ---
    total_faturas = 0.0
    for f in fatura_dados:
        ident = f.get("identificacao", {})
        mes = ident.get("mes_referencia", "N/A")
        consumo = f.get("consumo_ativo", {})
        demanda = f.get("demanda", {})
        ere = _pega_componente(f, "ere") or {"valor_total": 0.0}
        dmax_fponta = next((d["valor_kw"] for d in demanda.get("maxima", []) if d["periodo"] == "fora_ponta"), 0.0)
        dmax_ponta = next((d["valor_kw"] for d in demanda.get("maxima", []) if d["periodo"] == "ponta"), 0.0)
        dmcr_ponta = next((d["valor_kw"] for d in demanda.get("dmcr", []) if d["periodo"] == "ponta"), 0.0)
        dmcr_fora = next((d["valor_kw"] for d in demanda.get("dmcr", []) if d["periodo"] == "fora_ponta"), demanda.get("fora_ponta_kw", 0.0))
        valor = f.get("valores_totais", {}).get("valor_total_fatura", 0.0)

        res["tabela_consumo"].append({
            "data": mes.lower().replace("/20", "/")[0:3] + mes[-2:],
            "demanda_ponta": formatar(dmax_ponta),
            "demanda_fora_ponta": formatar(dmax_fponta),
            "energia_ponta": formatar(consumo.get("ponta_kwh", 0.0)),
            "energia_fora_ponta": formatar(consumo.get("fora_ponta_kwh", 0.0)),
            "energia_injetada": formatar(consumo.get("energia_injetada_kwh",0.0)),
            "ere": formatar(ere["valor_total"]),
            "valor_total": formatar(valor)
        })
        total_faturas += valor

    res["total_energia"] = formatar(total_faturas)

    # --- Tabelas Otimizadas, Ajustes, Contratos ---
    from .utils.faturamento import (
        calcular_tabela_12meses,
        calcular_tabela_ajuste,
        calcular_tabela_contrato_atual,
        calcular_tabela_contrato_proposto
    )

    res["tabela_12meses_otimizados"] = calcular_tabela_12meses(fatura_dados, tarifas_atualizado, tarifa_ere_atualizado, demanda_verde_otima, demanda_azul_p_otima, demanda_azul_fp_otima)
    res["tabela_ajuste"] = calcular_tabela_ajuste(fatura_dados, tarifas_atualizado, tarifa_ere_atualizado)
    res["tabela_contrato_comparado"], total_atual = calcular_tabela_contrato_atual(fatura_dados, tarifas_atualizado, tarifa_ere_atualizado, pis_aliq, cofins_aliq, icms_aliq)
    tabela_proposto, total_proposto = calcular_tabela_contrato_proposto(fatura_dados, tarifas_atualizado, tarifa_ere_atualizado, demanda_verde_otima, pis_aliq, cofins_aliq, icms_aliq)
    res["tabela_contrato_comparado"] += tabela_proposto
    # --- Ajustes finais ---
    try:
        linha_total = next((l for l in res["tabela_ajuste"] if "TOTAL" in l["mes"].upper()), None)
        if linha_total:
            atualizado = float(linha_total["atualizado"].replace(".", "").replace(",", "."))
            realizado = float(linha_total["realizado"].replace(".", "").replace(",", "."))
            acrescimo = atualizado - realizado
            percentual = (acrescimo / realizado) * 100 if realizado else 0
            res["ajuste_acrescimo"] = formatar(acrescimo)
            res["ajuste_percentual"] = f"{percentual:.2f}".replace(".", ",")
        else:
            res["ajuste_acrescimo"] = "0,00"
            res["ajuste_percentual"] = "0,00"
    except:
        res["ajuste_acrescimo"] = "-1,00"
        res["ajuste_percentual"] = "-1,00"

    res["resumo_proposta"] = gerar_resumo_proposta(demanda_verde_otima, res["tabela_contrato_comparado"])
    ultrapassagem_ocorre = True if total_atual["ultrapassagem"] > 0 else False
    ajuste_total = next(
        (linha["ajuste"] for linha in res["tabela_ajuste"] if linha["mes"] == "TOTAL"),
        0  # valor padrão caso não encontre
    )
    atualizado_aumento = ajuste_total > 0
    res.update(gerar_dados_contextuais_integrado(res, fatura_dados, ultrapassagem_ocorre, atualizado_aumento, demanda_verde_otima, demanda_azul_p_otima, demanda_azul_fp_otima))

    return res
