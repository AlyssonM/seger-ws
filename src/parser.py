# src/parser.py
from typing import Any, Dict, List, Optional
import os, json
import PyPDF2
from google import genai
from google.genai import types
from src.parser_regex import extrair_dados_completos_da_fatura_regex
from datetime import date
import re

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
        try:
            resultado = extrair_dados_completos_da_fatura_regex(texto)
            return resultado
        except Exception as e:
            import traceback
            traceback_str = traceback.format_exc()
            print("❌ ERRO ao aplicar regex:\n", traceback_str)
            return {"error": f"Erro ao aplicar regex: {str(e)}"}
    # 3) Monta conteúdo no formato chat
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
    
    # 4) Chamada ao Gemini via generate_content
    response = client.models.generate_content(
        model="gemini-2.0-flash-001",
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=5000
        )
    )
    # data_json = extrair_dados_completos_da_fatura_regex(texto)
    # print(f"resposta com regex:\n{data_json}")
    
    # 5) Parse do JSON retornado
    try:
        clean_text = re.sub(r"^```json\s*|\s*```$", "", response.text.strip(), flags=re.MULTILINE)
        # print(f"resposta do modelo:\n{clean_text}")
        return json.loads(clean_text)
        # return data_json
    except json.JSONDecodeError:
        print("❌ JSON mal formatado retornado pelo modelo:\n", response.text)
        # return {"raw": response.text}
        return {"error": "JSON decoding error", "raw_response": response.text}

def analisar_eficiencia_energetica(
    fatura_dados: List[Dict[str, Any]],
    tarifas,
    tarifas_atualizado,
    demanda_verde_otima,
    demanda_azul_p_otima,
    demanda_azul_fp_otima
) -> Dict[str, Any]:
    """
    Reproduz o cálculo da planilha 'Projeto Análise Tarifária – SEGER'.
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
            "ere": "0,27703",
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
        dmcr_ponta = next((d["valor_kw"] for d in demanda.get("dmcr", []) if d["periodo"] == "ponta"), 0.0)
        dmcr_fora = next((d["valor_kw"] for d in demanda.get("dmcr", []) if d["periodo"] == "fora_ponta"), demanda.get("fora_ponta_kw", 0.0))
        valor = f.get("valores_totais", {}).get("valor_total_fatura", 0.0)

        res["tabela_consumo"].append({
            "data": mes.lower().replace("/20", "/")[0:3] + mes[-2:],
            "demanda_ponta": formatar(dmcr_ponta),
            "demanda_fora_ponta": formatar(dmcr_fora),
            "energia_ponta": formatar(consumo.get("ponta_kwh", 0.0)),
            "energia_fora_ponta": formatar(consumo.get("fora_ponta_kwh", 0.0)),
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

    res["tabela_12meses_otimizados"] = calcular_tabela_12meses(fatura_dados, tarifas, demanda_verde_otima, demanda_azul_p_otima, demanda_azul_fp_otima)
    res["tabela_ajuste"] = calcular_tabela_ajuste(fatura_dados, tarifas_atualizado)
    res["tabela_contrato_comparado"], total_atual = calcular_tabela_contrato_atual(fatura_dados, tarifas_atualizado, pis_aliq, cofins_aliq, icms_aliq)
    tabela_proposto, total_proposto = calcular_tabela_contrato_proposto(fatura_dados, tarifas_atualizado, demanda_verde_otima, pis_aliq, cofins_aliq, icms_aliq)
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
    res.update(gerar_dados_contextuais_integrado(res, fatura_dados, demanda_verde_otima, demanda_azul_p_otima, demanda_azul_fp_otima))

    return res

# def analisar_eficiencia_energetica(
#     fatura_dados: List[Dict[str, Any]], 
#     tarifas, 
#     tarifas_atualizado,
#     demanda_verde_otima, 
#     demanda_azul_p_otima, 
#     demanda_azul_fp_otima
#     ) -> Dict[str, Any]:
#     """
#     Reproduz o cálculo da planilha 'Projeto Análise Tarifária – SEGER'.
#     """

#     # ---------- 1. tarifas de referência ---------- #
#     tarifas_referencia = {
#         "A VERDE A4": tarifas_atualizado.get("verde", {}),
#         "A AZUL A4": tarifas_atualizado.get("azul", {}),
#         "BT Optante B3": tarifas_atualizado.get("convencional", {})
#     }

#     # ---------- Cálculo das médias de impostos ---------- #
#     pis_total = 0.0
#     cofins_total = 0.0
#     icms_total = 0.0
#     count_pis = count_cofins = count_icms = 0

#     for f in fatura_dados:
#         impostos = f.get("impostos", [])

#         for imp in impostos:
#             nome = imp.get("nome", "").upper()
#             aliq = imp.get("aliquota", 0.0)
#             if nome == "PIS":
#                 pis_total += aliq/100
#                 count_pis += 1
#             elif nome == "COFINS":
#                 cofins_total += aliq/100
#                 count_cofins += 1
#             elif nome == "ICMS":
#                 icms_total += aliq/100
#                 count_icms += 1

#     # Médias em percentual (já prontas para uso)
#     pis_media = pis_total / count_pis if count_pis else 0.0
#     cofins_media = cofins_total / count_cofins if count_cofins else 0.0
#     icms_media = icms_total / count_icms if count_icms else 0.0

#     # Para uso nos cálculos posteriores (convertendo para frações)
#     pis_aliq = pis_media
#     cofins_aliq = cofins_media
#     icms_aliq = icms_media

#     # ---------- 2. estrutura de saída ------------- #
#     res: Dict[str, Any] = {
#         "tabela_consumo":            [],
#         "tabela_tarifas":            [],
#         "tabela_ajuste":             [],
#         "tabela_12meses_otimizados": [],
#         "tabela_contrato_comparado": [],
#         "resumo_proposta":           [],
#     }

#     ere = "0,27703"
#     # pis = "1,03916"
#     # cofins = "4,78583"
#     # icms = "0,00"
#     for grupo, t in tarifas_referencia.items():
#         if grupo == "A VERDE A4":
#             res["tabela_tarifas"].append({
#                 "grupo": grupo,
#                 "consumo_ponta":       f"{(t.get('TEponta') or 0.0) + (t.get('TUSDponta') or 0.0):.5f}".replace('.', ','),
#                 "consumo_fora_ponta":  f"{(t.get('TEforaPonta') or 0.0) + (t.get('TUSDforaPonta') or 0.0):.5f}".replace('.', ','),
#                 "demanda_ponta":       "-",
#                 "demanda_fora":        f"{(t.get('DemandaForaPonta') or 0.0):.2f}".replace('.', ','),
#                 "ere":                 ere,
#                 "pis":                 f"{pis_aliq:.2f}".replace(".", ","),
#                 "cofins":              f"{cofins_aliq:.2f}".replace(".", ","),
#                 "icms":                f"{icms_aliq:.2f}".replace(".", ",")
#             })
#         elif grupo == "A AZUL A4":
#             res["tabela_tarifas"].append({
#                 "grupo": grupo,
#                 "consumo_ponta":       f"{t.get('TEponta', 0.0) + t.get('TUSDponta', 0.0):.5f}".replace('.', ','),
#                 "consumo_fora_ponta":  f"{t.get('TEforaPonta', 0.0) + t.get('TUSDforaPonta', 0.0):.5f}".replace('.', ','),
#                 "demanda_ponta":       f"{t.get('DemandaPonta', 0.0):.2f}".replace('.', ','),
#                 "demanda_fora":        f"{t.get('DemandaForaPonta', 0.0):.2f}".replace('.', ','),
#                 "ere":                 ere,
#                 "pis":                 f"{pis_aliq:.2f}".replace(".", ","),
#                 "cofins":              f"{cofins_aliq:.2f}".replace(".", ","),
#                 "icms":                f"{icms_aliq:.2f}".replace(".", ",")
#             })
#         elif grupo == "BT Optante B3":
#             consumo_total = t.get("TE", 0.0) + t.get("TUSD", 0.0)
#             consumo_str = f"{consumo_total:.5f}".replace('.', ',')
#             res["tabela_tarifas"].append({
#                 "grupo": grupo,
#                 "consumo_ponta":       consumo_str,
#                 "consumo_fora_ponta":  consumo_str,
#                 "demanda_ponta":       "-",
#                 "demanda_fora":        "-",
#                 "ere":                 ere,
#                 "pis":                 f"{pis_aliq:.2f}".replace(".", ","),
#                 "cofins":              f"{cofins_aliq:.2f}".replace(".", ","),
#                 "icms":                f"{icms_aliq:.2f}".replace(".", ",")
#             })


#     # ---------- 3. loop das faturas --------------- #
#     otimizados: List[Dict[str, Any]] = []
#     # for f in faturas_data:
#     #     ident   = f.get("identificacao", {})
#     #     mesref  = ident.get("mes_referencia", "N/A")

#     #     # --- energia ---
#     #     kwh_ponta = f.get("consumo_ativo", {}).get("ponta_kwh", 0.0)
#     #     kwh_fora  = f.get("consumo_ativo", {}).get("fora_ponta_kwh", 0.0)

#     #     # --- demandas ---
#     #     dm = f.get("demanda", {})
#     #     dmcr_ponta = next((d["valor_kw"] for d in dm.get("dmcr", []) if d["periodo"] == "ponta"), 0.0)
#     #     dmcr_fora  = next((d["valor_kw"] for d in dm.get("dmcr", []) if d["periodo"] == "fora_ponta"), 0.0)
#     #     dmax_ponta = next((d["valor_kw"] for d in dm.get("maxima", []) if d["periodo"] == "ponta"), 0.0)
#     #     dmax_fora  = next((d["valor_kw"] for d in dm.get("maxima", []) if d["periodo"] == "fora_ponta"), 0.0)
#     #     d_contrat  = dm.get("contratada_kw", 0.0)
        
#     #     if not dmcr_fora:                                # ← alterado
#     #       dmcr_fora = dm.get("fora_ponta_kw", 0.0)     #   usa linha de faturamento (verde)



#     #     # --- componentes adicionais ---
#     #     comp_bandeira = _pega_componente(f, "bandeira")
#     #     comp_iluminacao = _pega_componente(f, "ilum")
#     #     comp_juros = _pega_componente(f, "juros")
#     #     comp_multa = _pega_componente(f, "multa")
#     #     ere_comp = _pega_componente(f, "ere") or {"valor_total": 0.0}
#     #     valor_fatura = f.get("valores_totais", {}).get("valor_total_fatura", 0.0)

#     # ---------- registra tabela_consumo ----------
#     def formatar(valor):
#         return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

#     total_faturas = 0.0
#     for f in fatura_dados:
#         ident   = f.get("identificacao", {})
#         mesref  = ident.get("mes_referencia", "N/A")

#         # Energia
#         kwh_ponta = f.get("consumo_ativo", {}).get("ponta_kwh", 0.0)
#         kwh_fora  = f.get("consumo_ativo", {}).get("fora_ponta_kwh", 0.0)

#         # Demandas
#         dm = f.get("demanda", {})
#         dmcr_ponta = next((d["valor_kw"] for d in dm.get("dmcr", []) if d["periodo"] == "ponta"), 0.0)
#         dmcr_fora  = next((d["valor_kw"] for d in dm.get("dmcr", []) if d["periodo"] == "fora_ponta"), 0.0)

#         if not dmcr_fora:
#             dmcr_fora = dm.get("fora_ponta_kw", 0.0)  # verde

#         # ERE
#         ere_comp = _pega_componente(f, "ere") or {"valor_total": 0.0}
#         valor_fatura = f.get("valores_totais", {}).get("valor_total_fatura", 0.0)
#         total_faturas += valor_fatura
#         # Adiciona à tabela consumo
#         res["tabela_consumo"].append({
#             "data": mesref.lower().replace("/20", "/")[0:3] + mesref[-2:],  # Ex: mar/23
#             "demanda_ponta": formatar(dmcr_ponta),
#             "demanda_fora_ponta": formatar(dmcr_fora),
#             "energia_ponta": formatar(kwh_ponta),
#             "energia_fora_ponta": formatar(kwh_fora),
#             "ere": formatar(ere_comp["valor_total"]),
#             "valor_total": formatar(valor_fatura)
#         })
#     res["total_energia"] = f"{total_faturas:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")    

#     # ---------- 4. simulação mês a mês ----------- #
#     tabela_otimizada = []
#     total_azul = 0.0
#     total_verde = 0.0
#     total_bt = 0.0

#     for f in fatura_dados:
#         ident   = f.get("identificacao", {})
#         mesref  = ident.get("mes_referencia", "N/A")
#         mes_label = mesref.lower().replace("/20", "/")[0:3] + mesref[-2:]  # ex: "mai/23"

#         custo_verde = calcular_tarifa_verde([f], tarifas["verde"], demanda_verde_otima)
#         custo_azul  = calcular_tarifa_azul([f], tarifas["azul"], [demanda_azul_p_otima, demanda_azul_fp_otima])
#         custo_bt    = calcular_tarifa_bt([f], tarifas["convencional"])

#         total_verde += custo_verde
#         total_azul  += custo_azul
#         total_bt    += custo_bt

#         tabela_otimizada.append({
#             "data": mes_label,
#             "verde": formatar(custo_verde),
#             "azul": formatar(custo_azul),
#             "bt": formatar(custo_bt)
#         })

#     # Adiciona o total final na tabela otimizada
#     tabela_otimizada.append({
#         "data": "TOTAL APÓS 12 MESES",
#         "verde": formatar(total_verde),
#         "azul": formatar(total_azul),
#         "bt": formatar(total_bt)
#     })

#     res["tabela_12meses_otimizados"] = tabela_otimizada

#     # ---------- 5. tabela_ajuste ---------- #
#     tabela_ajuste = []
#     total_realizado = 0.0
#     total_atualizado = 0.0

#     for f in fatura_dados:
#         ident   = f.get("identificacao", {})
#         mesref  = ident.get("mes_referencia", "N/A")
#         mes_label = mesref.lower().replace("/20", "/")[0:3] + mesref[-2:]  # ex: "mar/23"

#         valor_real = f.get("valores_totais", {}).get("valor_total_fatura", 0.0)
#         total_realizado += valor_real

#         # custo atualizado com tarifas atuais (simulação com base nas mesmas regras)
#         custo_atualizado = calcular_tarifa_verde([f], tarifas_atualizado["verde"], 570)
#         total_atualizado += custo_atualizado

#         tabela_ajuste.append({
#             "mes": mes_label,
#             "realizado": formatar(valor_real),
#             "atualizado": formatar(custo_atualizado)
#         })

#     # Linha TOTAL
#     tabela_ajuste.append({
#         "mes": "TOTAL",
#         "realizado": formatar(total_realizado),
#         "atualizado": formatar(total_atualizado)
#     })

#     res["tabela_ajuste"] = tabela_ajuste

#     #--------- 6. contrato comparado ---------- #
#     res["tabela_contrato_comparado"] = []
#     total_contrato = {
#         "consumo": 0.0,
#         "demanda": 0.0,
#         "ultrapassagem": 0.0,
#         "bip": 0.0,
#         "ere": 0.0,
#         "impostos": 0.0,
#         "total": 0.0
#     }

#     for f in fatura_dados:
#         ident = f.get("identificacao", {})
#         mesref = ident.get("mes_referencia", "N/A")
#         mes_formatado = mesref.lower().replace("/20", "/")[0:3] + mesref[-2:]

#         consumo = f.get("consumo_ativo", {})
#         demanda = f.get("demanda", {})
#         componentes = f.get("componentes_extras", [])
#         impostos = f.get("impostos", [])
#         valores = f.get("valores_totais", {})

#         # Cálculo consumo = energia ativa * tarifa
#         tusd_fp = tarifas_atualizado["verde"].get("TUSDforaPonta", 0.0)
#         tusd_p = tarifas_atualizado["verde"].get("TUSDponta", 0.0)
#         te_fp = tarifas_atualizado["verde"].get("TEforaPonta", 0.0)
#         te_p = tarifas_atualizado["verde"].get("TEponta", 0.0)
#         tarifa_energia_fp = tusd_fp + te_fp
#         tarifa_energia_p = tusd_p + te_p

#         energia_fp = consumo.get("fora_ponta_kwh", 0.0)
#         energia_p = consumo.get("ponta_kwh", 0.0)
#         total_consumo = energia_fp * tarifa_energia_fp + energia_p * tarifa_energia_p

#         # Demanda
#         demanda_fp_tarifa = tarifas_atualizado["verde"].get("DemandaForaPonta", 0.0)
#         contratada = demanda.get("contratada_kw", 0.0)
#         medida_fp = demanda.get("fora_ponta_kw", 0.0)
#         medida_fp = max(medida_fp, next((d["valor_kw"] for d in demanda.get("maxima", []) if d["periodo"] == "fora_ponta"), 0.0))

#         ultrapassagem = max(medida_fp - contratada, 0.0)
#         valor_demanda = contratada * demanda_fp_tarifa
#         valor_ultrapassagem = ultrapassagem * demanda_fp_tarifa * 2

#         # Componentes
#         bandeira = sum([
#             c["valor_total"]
#             for c in componentes
#             if "bandeira" in c["descricao"].lower()
#         ])

#         iluminacao = sum([
#             c["valor_total"]
#             for c in componentes
#             if "ilum" in c["descricao"].lower()
#         ])

#         ere = (_pega_componente(f, "ere") or {"valor_total": 0.0})["valor_total"]

#         # Impostos
#         # pis_aliq = next((imp["aliquota"] for imp in impostos if imp["nome"] == "PIS"), 0.0) / 100
#         # cofins_aliq = next((imp["aliquota"] for imp in impostos if imp["nome"] == "COFINS"), 0.0) / 100
#         # icms_aliq = next((imp["aliquota"] for imp in impostos if imp["nome"] == "ICMS"), 0.0) / 100
        
#         bandeira_liquido = bandeira - bandeira*(pis_aliq + cofins_aliq)/100

#         base = total_consumo + valor_demanda + valor_ultrapassagem + bandeira_liquido
#         impostos_valor = base/(1-(pis_aliq/100) - (cofins_aliq/100)) * (pis_aliq + cofins_aliq + icms_aliq)/100

#         total_geral = base + impostos_valor + ere + iluminacao

#         def fmt(v): return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

#         res["tabela_contrato_comparado"].append({
#             "data": mes_formatado,
#             "consumo": fmt(total_consumo),
#             "demanda": fmt(valor_demanda),
#             "ultrapassagem": fmt(valor_ultrapassagem),
#             "bip": fmt(bandeira_liquido),
#             "ilum": fmt(iluminacao),
#             "ere": fmt(ere),
#             "pis": fmt(pis_aliq),
#             "cofins": fmt(cofins_aliq),
#             "icms": fmt(icms_aliq),
#             "impostos": fmt(impostos_valor),
#             "total": fmt(total_geral)
#         })

#         total_contrato["consumo"] += total_consumo
#         total_contrato["demanda"] += valor_demanda
#         total_contrato["ultrapassagem"] += valor_ultrapassagem
#         total_contrato["bip"] += bandeira_liquido + iluminacao
#         total_contrato["ere"] += ere
#         total_contrato["impostos"] += impostos_valor
#         total_contrato["total"] += total_geral

#     # Linha final do contrato proposto
#     res["tabela_contrato_comparado"].append({
#         "data": "\\textbf{CONTRATO ATUAL}",
#         "consumo": f"\\textbf{{{fmt(total_contrato['consumo'])}}}",
#         "demanda": f"\\textbf{{{fmt(total_contrato['demanda'])}}}",
#         "ultrapassagem": f"\\textbf{{{fmt(total_contrato['ultrapassagem'])}}}",
#         "bip": f"\\textbf{{{fmt(total_contrato['bip'])}}}",
#         "ere": f"\\textbf{{{fmt(total_contrato['ere'])}}}",
#         "impostos": f"\\textbf{{{fmt(total_contrato['impostos'])}}}",
#         "total": f"\\textbf{{{fmt(total_contrato['total'])}}}"
#     })

#     # ---------- 7. CONTRATO PROPOSTO (com demanda otimizada) ---------- #
#     total_proposto = {
#         "consumo": 0.0,
#         "demanda": 0.0,
#         "ultrapassagem": 0.0,
#         "bip": 0.0,
#         "ere": 0.0,
#         "impostos": 0.0,
#         "total": 0.0
#     }

#     for f in fatura_dados:
#         consumo = f.get("consumo_ativo", {})
#         demanda = f.get("demanda", {})
#         componentes = f.get("componentes_extras", [])
#         impostos = f.get("impostos", [])

#         # Tarifas otimizadas
#         tusd_fp = tarifas_atualizado["verde"].get("TUSDforaPonta", 0.0)
#         tusd_p = tarifas_atualizado["verde"].get("TUSDponta", 0.0)
#         te_fp = tarifas_atualizado["verde"].get("TEforaPonta", 0.0)
#         te_p = tarifas_atualizado["verde"].get("TEponta", 0.0)
#         tarifa_energia_fp = tusd_fp + te_fp
#         tarifa_energia_p = tusd_p + te_p

#         energia_fp = consumo.get("fora_ponta_kwh", 0.0)
#         energia_p = consumo.get("ponta_kwh", 0.0)
#         total_energia = energia_fp * tarifa_energia_fp + energia_p * tarifa_energia_p

#         # Demanda otimizada
#         # demanda_fp_tarifa = tarifas_atualizado["verde"].get("DemandaForaPonta", 0.0)
#         # contratada = demanda_verde_otima
#         # medida_fp = demanda.get("fora_ponta_kw", 0.0)
#         # medida_fp = max(medida_fp, next((d["valor_kw"] for d in demanda.get("maxima", []) if d["periodo"] == "fora_ponta"), 0.0))
        
#         # ultrapassagem = max(medida_fp - contratada, 0.0)
#         # valor_demanda = contratada * demanda_fp_tarifa
#         # valor_ultrapassagem = ultrapassagem * demanda_fp_tarifa * 2
        
#         demanda_contratada = demanda_verde_otima
#         maxima = demanda.get("maxima", [])
#         demanda_max_ponta = next((d["valor_kw"] for d in maxima if d.get("periodo") == "ponta"), 0.0)
#         demanda_max_fora_ponta = next((d["valor_kw"] for d in maxima if d.get("periodo") == "fora_ponta"), 0.0)
#         demanda_max = max(demanda_max_ponta, demanda_max_fora_ponta)
#         if demanda_max > demanda_contratada:
#             Ultrapassagem = demanda_max - demanda_contratada
#             Demanda = demanda_max
#         else:
#             Ultrapassagem = 0
#             Demanda = demanda_contratada
#         valor_demanda = Demanda * demanda_fp_tarifa
#         valor_ultrapassagem = Ultrapassagem * demanda_fp_tarifa * 2
        
#         # Ultrapassagem = 0
#         # Demanda = 0
        
#         # if demanda["fora_ponta_kw"] > contratada:
#         #     Ultrapassagem = demanda["fora_ponta_kw"] - contratada
#         #     Demanda = demanda["fora_ponta_kw"]
#         # else:
#         #     Ultrapassagem = 0
#         #     Demanda = contratada

#         # valor_demanda = Demanda * demanda_fp_tarifa
#         # valor_ultrapassagem = Ultrapassagem * demanda_fp_tarifa * 2
#         # Componentes
#         bandeira = sum([c["valor_total"] for c in componentes if "bandeira" in c["descricao"].lower()])
#         iluminacao = sum([c["valor_total"] for c in componentes if "ilum" in c["descricao"].lower()])
#         ere_valor = (_pega_componente(f, "ere") or {"valor_total": 0.0})["valor_total"]

#         # Impostos
#         # pis_aliq = next((imp["aliquota"] for imp in impostos if imp["nome"] == "PIS"), 0.0) / 100
#         # cofins_aliq = next((imp["aliquota"] for imp in impostos if imp["nome"] == "COFINS"), 0.0) / 100
#         # icms_aliq = next((imp["aliquota"] for imp in impostos if imp["nome"] == "ICMS"), 0.0) / 100

#         bandeira_liquido = bandeira - bandeira * (pis_aliq + cofins_aliq) / 100

#         base = total_energia + valor_demanda + valor_ultrapassagem + bandeira_liquido
#         impostos_valor = base / (1 - (pis_aliq + cofins_aliq + icms_aliq)/100) * (pis_aliq + cofins_aliq + icms_aliq)/100

#         total_geral = base + impostos_valor + ere_valor + iluminacao

#         total_proposto["consumo"] += total_energia
#         total_proposto["demanda"] += valor_demanda
#         total_proposto["ultrapassagem"] += valor_ultrapassagem
#         total_proposto["bip"] += bandeira_liquido + iluminacao
#         total_proposto["ere"] += ere_valor
#         total_proposto["impostos"] += impostos_valor
#         total_proposto["total"] += total_geral

#     res["tabela_contrato_comparado"].append({
#         "data": "\\textbf{CONTRATO PROPOSTO}",
#         "consumo": f"\\textbf{{{fmt(total_proposto['consumo'])}}}",
#         "demanda": f"\\textbf{{{fmt(total_proposto['demanda'])}}}",
#         "ultrapassagem": f"\\textbf{{{fmt(total_proposto['ultrapassagem'])}}}",
#         "bip": f"\\textbf{{{fmt(total_proposto['bip'])}}}",
#         "ere": f"\\textbf{{{fmt(total_proposto['ere'])}}}",
#         "impostos": f"\\textbf{{{fmt(total_proposto['impostos'])}}}",
#         "total": f"\\textbf{{{fmt(total_proposto['total'])}}}"
#     })

#     # Calcular ajuste_acrescimo e ajuste_percentual com base na tabela_ajuste
#     try:
#         tabela_ajuste = res.get("tabela_ajuste", [])
       
#         total_row = next((linha for linha in tabela_ajuste if "TOTAL" in linha["mes"].upper()), None)
#         print(f"tabela ajuste row: {total_row}")
#         if total_row:
#             realizado_str = total_row.get("realizado", "").strip().replace(".", "").replace(",", ".")
#             atualizado_str = total_row.get("atualizado", "").strip().replace(".", "").replace(",", ".")
#             realizado = float(realizado_str) if realizado_str else 0.0
#             atualizado = float(atualizado_str) if atualizado_str else 0.0
#             acrescimo = atualizado - realizado
#             percentual = (acrescimo / realizado) * 100 if realizado else 0
#             print(f"acrescimo: {acrescimo}")
#             print(f"percentual: {percentual}")
#             res["ajuste_acrescimo"] = f"{acrescimo:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
#             res["ajuste_percentual"] = f"{percentual:.2f}".replace(".", ",")
#         else:
#             res["ajuste_acrescimo"] = "0,00"
#             res["ajuste_percentual"] = "0,00"
#     except Exception as e:
#         res["ajuste_acrescimo"] = "-1,00"
#         res["ajuste_percentual"] = "-1,00"

#     def gerar_resumo_proposta(
#     demanda_verde_otima: float,
#     tabela_contrato_comparado: List[Dict[str, str]]
#     ) -> List[Dict[str, str]]:
#         def parse_valor(valor_str: str) -> float:
#             return float(valor_str.replace("R\\$", "").replace("\\textbf{", "").replace("}", "").replace(".", "").replace(",", "."))

#         atual = next((item for item in tabela_contrato_comparado if "ATUAL" in item["data"]), None)
#         proposto = next((item for item in tabela_contrato_comparado if "PROPOSTO" in item["data"]), None)

#         custo_atual = parse_valor(atual["total"]) if atual else 0.0
#         custo_proposto = parse_valor(proposto["total"]) if proposto else 0.0
#         economia = custo_atual - custo_proposto

#         # Demanda fora ponta atual
#         demanda_atual_fp = "-"
#         if atual:
#             demanda_atual_fp = atual.get("demanda", "-").replace("\\textbf{", "").replace("}", "").strip()
#             if demanda_atual_fp.replace(",", "").replace(".", "").isdigit():
#                 demanda_atual_fp += " kW"

#         return [
#             {"titulo": "Modalidade", "atual": "Tarifa Horária Verde", "proposto": "Tarifa Horária Verde"},
#             {"titulo": "Demanda Ponta", "atual": "-", "proposto": "-"},
#             {"titulo": "Demanda Fora Ponta", "atual": demanda_atual_fp, "proposto": f"{int(round(demanda_verde_otima))} kW"},
#             {"titulo": "Custo anual", "atual": f"R\\$ {formatar(custo_atual)}", "proposto": f"R\\$ {formatar(custo_proposto)}"},
#             {"titulo": "Economia em relação à Atual", "atual": "-", "proposto": f"(R\\$ {formatar(economia)}/ano)"}
#         ]



#     def format_real(valor):
#         return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

#     def format_kw(valor):
#         return f"{valor:.0f} kW"

#     def gerar_dados_contextuais_integrado(res, fatura_dados, demanda_verde_otima, demanda_azul_p, demanda_azul_fp):
#         atual = next((x for x in res["tabela_contrato_comparado"] if "ATUAL" in x["data"]), {})
#         proposto = next((x for x in res["tabela_contrato_comparado"] if "PROPOSTO" in x["data"]), {})

#         # Extrair dados da primeira fatura
#         f1 = fatura_dados[0]
#         ident = f1.get("identificacao", {})
#         unidade_inst = ident.get("unidade","")
#         grupo = ident.get("grupo_tarifario", "A")
#         subgrupo = "A4" if grupo == "A" else "-"
#         classe = ident.get("classe", "").title()
#         demanda_data = f1.get("demanda")
#         endereco = ident.get("endereco", "rua A.")
#         tensao = ident.get("tensao", "11")
#         tensao_unid = ident.get("tensaoUnid", "kV")
#         nivel_tensao = ident.get("nivel_tensao", "média tensão" if grupo == "A" else "baixa tensão")

#         # Modalidades (fixas ou inferidas se necessário)
#         tarifa_atual = "Tarifa Horária Verde"
#         tarifa_nova = "Tarifa Horária Verde"
#         tarifa_analise = "Tarifa Horária Azul"
        
#         # Datas
#         mes_ini = f1.get("identificacao", {}).get("mes_referencia", "n/a")
#         mes_fim = fatura_dados[-1]["identificacao"].get("mes_referencia", "n/a")
#         num_contas = len(fatura_dados)

#         def format_kw(v): return f"{int(round(v))} kW"
#         def format_real(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

#         dados_meta = {
#             "Unidade": unidade_inst,
#             "Autores": "Alysson Machado",
#             "data": date.today().strftime("%d-%m-%Y"),
#             "Endereco": endereco,
#             "NivelTensao": nivel_tensao,
#             "tensao": tensao,
#             "tensaoUnid": tensao_unid,
#             "distribuidora": "EDP ES",
#             "instalacao": ident.get("numero_instalacao", "N/A"),
#             "TipoContrato": "cativo (Contrato de Compra de Energia Elétrica Regulada)",
#             "grupoAtual": grupo,
#             "subGrupoAtual": subgrupo,
#             "subGrupoNovo": subgrupo,
#             "classe": classe,
#             "TarifaAtual": tarifa_atual,
#             "TarifaAnalise": tarifa_analise,
#             "TarifaAnalisePonta": format_kw(demanda_azul_p),
#             "TarifaAnaliseForaPonta": format_kw(demanda_azul_fp),
#             "TarifaNova": tarifa_nova,
#             "demandaAtual": format_kw(demanda_data["contratada_kw"]),
#             "demandaNova": format_kw(demanda_verde_otima),
#             "numContas": str(num_contas),
#             "baseDadosInic": mes_ini,
#             "baseDadosFinal": mes_fim,
#             "dadosAnaliseInic": mes_ini,
#             "dadosAnaliseFinal": mes_fim,
#             "custoContratoAtual": atual.get("total", "0,00").replace("\\textbf{", "").replace("}", ""),
#             "custoContratoNovo": proposto.get("total", "0,00").replace("\\textbf{", "").replace("}", "")
#         }

#         # Cálculo da economia
#         try:
#             atual_float = float(dados_meta["custoContratoAtual"].replace(".", "").replace(",", "."))
#             novo_float = float(dados_meta["custoContratoNovo"].replace(".", "").replace(",", "."))
#             economia = atual_float - novo_float
#             economia_pct = economia / atual_float * 100
#             dados_meta["economiaContrato"] = format_real(economia).replace("R$ ", "")
#             dados_meta["economiaPercentual"] = f"{economia_pct:.1f}"
#         except Exception:
#             dados_meta["economiaContrato"] = "0,00"
#             dados_meta["economiaPercentual"] = "0,0"

#         return dados_meta

#     res["resumo_proposta"] = gerar_resumo_proposta(demanda_verde_otima, res["tabela_contrato_comparado"])
#     res.update(
#         gerar_dados_contextuais_integrado(
#             res,
#             fatura_dados,
#             demanda_verde_otima, 
#             demanda_azul_p_otima, 
#             demanda_azul_fp_otima
#         )
#     )

#     return res
