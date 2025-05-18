from datetime import date
from typing import List, Dict, Tuple, Any, Optional
from .tarifas import calcular_tarifa_verde, calcular_tarifa_azul, calcular_tarifa_bt

def _pega_componente(fatura: Dict[str, Any], termo: str) -> Optional[Dict[str, Any]]:
    """Retorna o 1º componente_extra cujo texto contenha <termo>."""
    for c in fatura.get("componentes_extras", []):
        if termo.lower() in c["descricao"].lower():
            return c
    return None

def formatar(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def format_real(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def format_kw(valor: float) -> str:
    return f"{int(round(valor))} kW"

def media_impostos(fatura_dados: List[Dict[str, Any]]) -> Dict[str, float]:
    total = {"PIS": 0.0, "COFINS": 0.0, "ICMS": 0.0}
    count = {"PIS": 0, "COFINS": 0, "ICMS": 0}

    for fatura in fatura_dados:
        for imposto in fatura.get("impostos", []):
            nome = imposto.get("nome", "").upper()
            aliq = imposto.get("aliquota", 0.0) / 100
            if nome in total:
                total[nome] += aliq
                count[nome] += 1

    return {
        "pis": total["PIS"] / count["PIS"] if count["PIS"] else 0.0,
        "cofins": total["COFINS"] / count["COFINS"] if count["COFINS"] else 0.0,
        "icms": total["ICMS"] / count["ICMS"] if count["ICMS"] else 0.0
    }

def gerar_resumo_proposta(
    demanda_verde_otima: float,
    tabela_contrato_comparado: List[Dict[str, str]]
) -> List[Dict[str, str]]:

    def parse_valor(valor_str: str) -> float:
        return float(valor_str.replace("R\\$", "").replace("\\textbf{", "").replace("}", "").replace(".", "").replace(",", "."))

    atual = next((item for item in tabela_contrato_comparado if "ATUAL" in item["data"]), None)
    proposto = next((item for item in tabela_contrato_comparado if "PROPOSTO" in item["data"]), None)

    custo_atual = parse_valor(atual["total"]) if atual else 0.0
    custo_proposto = parse_valor(proposto["total"]) if proposto else 0.0
    economia = custo_atual - custo_proposto

    demanda_atual_fp = "-"
    if atual:
        demanda_atual_fp = atual.get("demanda", "-").replace("\\textbf{", "").replace("}", "").strip()
        if demanda_atual_fp.replace(",", "").replace(".", "").isdigit():
            demanda_atual_fp += " kW"

    return [
        {"titulo": "Modalidade", "atual": "Tarifa Horária Verde", "proposto": "Tarifa Horária Verde"},
        {"titulo": "Demanda Ponta", "atual": "-", "proposto": "-"},
        {"titulo": "Demanda Fora Ponta", "atual": demanda_atual_fp, "proposto": f"{int(round(demanda_verde_otima))} kW"},
        {"titulo": "Custo anual", "atual": f"R\\$ {formatar(custo_atual)}", "proposto": f"R\\$ {formatar(custo_proposto)}"},
        {"titulo": "Economia em relação à Atual", "atual": "-", "proposto": f"(R\\$ {formatar(economia)}/ano)"}
    ]

def gerar_dados_contextuais_integrado(res, fatura_dados, demanda_verde_otima, demanda_azul_p, demanda_azul_fp):
    atual = next((x for x in res["tabela_contrato_comparado"] if "ATUAL" in x["data"]), {})
    proposto = next((x for x in res["tabela_contrato_comparado"] if "PROPOSTO" in x["data"]), {})

    f1 = fatura_dados[0]
    ident = f1.get("identificacao", {})

    grupo = ident.get("grupo_tarifario", "A")
    subgrupo = "A4" if grupo == "A" else "-"
    classe = ident.get("classe", "").title()

    dados_meta = {
        "Unidade": ident.get("unidade", ""),
        "Autores": "Alysson Machado",
        "data": date.today().strftime("%d-%m-%Y"),
        "Endereco": ident.get("endereco", "rua A."),
        "NivelTensao": ident.get("nivel_tensao", "média tensão" if grupo == "A" else "baixa tensão"),
        "tensao": ident.get("tensao", "11"),
        "tensaoUnid": ident.get("tensaoUnid", "kV"),
        "distribuidora": "EDP ES",
        "instalacao": ident.get("numero_instalacao", "N/A"),
        "TipoContrato": "cativo (Contrato de Compra de Energia Elétrica Regulada)",
        "grupoAtual": grupo,
        "subGrupoAtual": subgrupo,
        "subGrupoNovo": subgrupo,
        "classe": classe,
        "TarifaAtual": "Tarifa Horária Verde",
        "TarifaAnalise": "Tarifa Horária Azul",
        "TarifaAnalisePonta": format_kw(demanda_azul_p),
        "TarifaAnaliseForaPonta": format_kw(demanda_azul_fp),
        "TarifaNova": "Tarifa Horária Verde",
        "demandaAtual": format_kw(f1.get("demanda", {}).get("contratada_kw", 0.0)),
        "demandaNova": format_kw(demanda_verde_otima),
        "numContas": str(len(fatura_dados)),
        "baseDadosInic": ident.get("mes_referencia", "n/a"),
        "baseDadosFinal": fatura_dados[-1].get("identificacao", {}).get("mes_referencia", "n/a"),
        "dadosAnaliseInic": ident.get("mes_referencia", "n/a"),
        "dadosAnaliseFinal": fatura_dados[-1].get("identificacao", {}).get("mes_referencia", "n/a"),
        "custoContratoAtual": atual.get("total", "0,00").replace("\\textbf{", "").replace("}", ""),
        "custoContratoNovo": proposto.get("total", "0,00").replace("\\textbf{", "").replace("}", "")
    }

    try:
        atual_float = float(dados_meta["custoContratoAtual"].replace(".", "").replace(",", "."))
        novo_float = float(dados_meta["custoContratoNovo"].replace(".", "").replace(",", "."))
        economia = atual_float - novo_float
        economia_pct = economia / atual_float * 100
        dados_meta["economiaContrato"] = format_real(economia).replace("R$ ", "")
        dados_meta["economiaPercentual"] = f"{economia_pct:.1f}"
    except Exception:
        dados_meta["economiaContrato"] = "0,00"
        dados_meta["economiaPercentual"] = "0,0"

    return dados_meta

def calcular_tabela_12meses(fatura_dados, tarifas, demanda_verde_otima, demanda_azul_p_otima, demanda_azul_fp_otima):
    def formatar(valor):
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    tabela_otimizada = []
    total_azul = total_verde = total_bt = 0.0

    for f in fatura_dados:
        ident = f.get("identificacao", {})
        mesref = ident.get("mes_referencia", "N/A")
        mes_label = mesref.lower().replace("/20", "/")[0:3] + mesref[-2:]  # exemplo: "jul/23"

        custo_verde = calcular_tarifa_verde([f], tarifas["verde"], demanda_verde_otima)
        custo_azul = calcular_tarifa_azul([f], tarifas["azul"], [demanda_azul_p_otima, demanda_azul_fp_otima])
        custo_bt = calcular_tarifa_bt([f], tarifas["convencional"])

        total_verde += custo_verde
        total_azul += custo_azul
        total_bt += custo_bt

        tabela_otimizada.append({
            "data": mes_label,
            "verde": formatar(custo_verde),
            "azul": formatar(custo_azul),
            "bt": formatar(custo_bt),
        })

    tabela_otimizada.append({
        "data": "TOTAL APÓS 12 MESES",
        "verde": formatar(total_verde),
        "azul": formatar(total_azul),
        "bt": formatar(total_bt),
    })

    return tabela_otimizada

def calcular_tabela_ajuste(fatura_dados, tarifas_atualizado, demanda_base=570.0):
    def formatar(valor):
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    tabela_ajuste = []
    total_realizado = 0.0
    total_atualizado = 0.0

    for f in fatura_dados:
        ident = f.get("identificacao", {})
        mesref = ident.get("mes_referencia", "N/A")
        mes_label = mesref.lower().replace("/20", "/")[0:3] + mesref[-2:]

        valor_real = f.get("valores_totais", {}).get("valor_total_fatura", 0.0)
        total_realizado += valor_real

        custo_atualizado = calcular_tarifa_verde([f], tarifas_atualizado["verde"], demanda_base)
        total_atualizado += custo_atualizado

        tabela_ajuste.append({
            "mes": mes_label,
            "realizado": formatar(valor_real),
            "atualizado": formatar(custo_atualizado)
        })

    tabela_ajuste.append({
        "mes": "TOTAL",
        "realizado": formatar(total_realizado),
        "atualizado": formatar(total_atualizado)
    })

    return tabela_ajuste

def calcular_tabela_contrato_atual(
    fatura_dados, 
    tarifas_atualizado, 
    pis_aliq, 
    cofins_aliq, 
    icms_aliq
    ):
    def fmt(v):
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    tabela = []
    total = {
        "consumo": 0.0,
        "demanda": 0.0,
        "ultrapassagem": 0.0,
        "bip": 0.0,
        "ere": 0.0,
        "impostos": 0.0,
        "total": 0.0
    }

    for f in fatura_dados:
        ident = f.get("identificacao", {})
        mesref = ident.get("mes_referencia", "N/A")
        mes_formatado = mesref.lower().replace("/20", "/")[0:3] + mesref[-2:]

        consumo = f.get("consumo_ativo", {})
        demanda = f.get("demanda", {})
        componentes = f.get("componentes_extras", [])
        impostos = f.get("impostos", [])

        tusd_fp = tarifas_atualizado["verde"].get("TUSDforaPonta", 0.0)
        tusd_p = tarifas_atualizado["verde"].get("TUSDponta", 0.0)
        te_fp = tarifas_atualizado["verde"].get("TEforaPonta", 0.0)
        te_p = tarifas_atualizado["verde"].get("TEponta", 0.0)
        tarifa_energia_fp = tusd_fp + te_fp
        tarifa_energia_p = tusd_p + te_p

        energia_fp = consumo.get("fora_ponta_kwh", 0.0)
        energia_p = consumo.get("ponta_kwh", 0.0)
        total_consumo = energia_fp * tarifa_energia_fp + energia_p * tarifa_energia_p

        demanda_fp_tarifa = tarifas_atualizado["verde"].get("DemandaForaPonta", 0.0)
        contratada = demanda.get("contratada_kw", 0.0)
        medida_fp = demanda.get("fora_ponta_kw", 0.0)
        medida_fp = max(medida_fp, next((d["valor_kw"] for d in demanda.get("maxima", []) if d["periodo"] == "fora_ponta"), 0.0))

        ultrapassagem = max(medida_fp - contratada, 0.0)
        valor_demanda = contratada * demanda_fp_tarifa
        valor_ultrapassagem = ultrapassagem * demanda_fp_tarifa * 2

        bandeira = sum(c["valor_total"] for c in componentes if "bandeira" in c["descricao"].lower())
        iluminacao = sum(c["valor_total"] for c in componentes if "ilum" in c["descricao"].lower())
        ere = (_pega_componente(f, "ere") or {"valor_total": 0.0})["valor_total"]

        bandeira_liquido = bandeira - bandeira * (pis_aliq + cofins_aliq) / 100
        base = total_consumo + valor_demanda + valor_ultrapassagem + bandeira_liquido
        impostos_valor = base / (1 - (pis_aliq + cofins_aliq + icms_aliq)/100) * (pis_aliq + cofins_aliq + icms_aliq)/100

        total_geral = base + impostos_valor + ere + iluminacao

        tabela.append({
            "data": mes_formatado,
            "consumo": fmt(total_consumo),
            "demanda": fmt(valor_demanda),
            "ultrapassagem": fmt(valor_ultrapassagem),
            "bip": fmt(bandeira_liquido),
            "ilum": fmt(iluminacao),
            "ere": fmt(ere),
            "pis": fmt(pis_aliq),
            "cofins": fmt(cofins_aliq),
            "icms": fmt(icms_aliq),
            "impostos": fmt(impostos_valor),
            "total": fmt(total_geral)
        })

        total["consumo"] += total_consumo
        total["demanda"] += valor_demanda
        total["ultrapassagem"] += valor_ultrapassagem
        total["bip"] += bandeira_liquido + iluminacao
        total["ere"] += ere
        total["impostos"] += impostos_valor
        total["total"] += total_geral

    tabela.append({
        "data": "\\textbf{CONTRATO ATUAL}",
        "consumo": f"\\textbf{{{fmt(total['consumo'])}}}",
        "demanda": f"\\textbf{{{fmt(total['demanda'])}}}",
        "ultrapassagem": f"\\textbf{{{fmt(total['ultrapassagem'])}}}",
        "bip": f"\\textbf{{{fmt(total['bip'])}}}",
        "ere": f"\\textbf{{{fmt(total['ere'])}}}",
        "impostos": f"\\textbf{{{fmt(total['impostos'])}}}",
        "total": f"\\textbf{{{fmt(total['total'])}}}"
    })

    return tabela, total


def calcular_tabela_contrato_proposto(
    fatura_dados, 
    tarifas_atualizado, 
    demanda_verde_otima, 
    pis_aliq, 
    cofins_aliq, 
    icms_aliq
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    def fmt(v):
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    tabela = []
    total = {
        "consumo": 0.0,
        "demanda": 0.0,
        "ultrapassagem": 0.0,
        "bip": 0.0,
        "ere": 0.0,
        "impostos": 0.0,
        "total": 0.0
    }

    demanda_fp_tarifa = tarifas_atualizado["verde"].get("DemandaForaPonta", 0.0)

    for f in fatura_dados:
        consumo = f.get("consumo_ativo", {})
        demanda = f.get("demanda", {})
        componentes = f.get("componentes_extras", [])

        # Tarifas otimizadas
        tusd_fp = tarifas_atualizado["verde"].get("TUSDforaPonta", 0.0)
        tusd_p = tarifas_atualizado["verde"].get("TUSDponta", 0.0)
        te_fp = tarifas_atualizado["verde"].get("TEforaPonta", 0.0)
        te_p = tarifas_atualizado["verde"].get("TEponta", 0.0)
        tarifa_energia_fp = tusd_fp + te_fp
        tarifa_energia_p = tusd_p + te_p

        energia_fp = consumo.get("fora_ponta_kwh", 0.0)
        energia_p = consumo.get("ponta_kwh", 0.0)
        total_energia = energia_fp * tarifa_energia_fp + energia_p * tarifa_energia_p

        # Demanda otimizada
        demanda_contratada = demanda_verde_otima
        maxima = demanda.get("maxima", [])
        demanda_max_ponta = next((d["valor_kw"] for d in maxima if d.get("periodo") == "ponta"), 0.0)
        demanda_max_fora_ponta = next((d["valor_kw"] for d in maxima if d.get("periodo") == "fora_ponta"), 0.0)
        demanda_max = max(demanda_max_ponta, demanda_max_fora_ponta)

        if demanda_max > demanda_contratada:
            ultrapassagem = demanda_max - demanda_contratada
            demanda_faturada = demanda_max
        else:
            ultrapassagem = 0.0
            demanda_faturada = demanda_contratada

        valor_demanda = demanda_faturada * demanda_fp_tarifa
        valor_ultrapassagem = ultrapassagem * demanda_fp_tarifa * 2

        # Componentes
        bandeira = sum(c["valor_total"] for c in componentes if "bandeira" in c["descricao"].lower())
        iluminacao = sum(c["valor_total"] for c in componentes if "ilum" in c["descricao"].lower())
        ere_valor = (_pega_componente(f, "ere") or {"valor_total": 0.0})["valor_total"]

        bandeira_liquido = bandeira - bandeira * (pis_aliq + cofins_aliq) / 100
        base = total_energia + valor_demanda + valor_ultrapassagem + bandeira_liquido
        impostos_valor = base / (1 - (pis_aliq + cofins_aliq + icms_aliq)/100) * (pis_aliq + cofins_aliq + icms_aliq)/100

        total_geral = base + impostos_valor + ere_valor + iluminacao

        total["consumo"] += total_energia
        total["demanda"] += valor_demanda
        total["ultrapassagem"] += valor_ultrapassagem
        total["bip"] += bandeira_liquido + iluminacao
        total["ere"] += ere_valor
        total["impostos"] += impostos_valor
        total["total"] += total_geral

    tabela.append({
        "data": "\\textbf{CONTRATO PROPOSTO}",
        "consumo": f"\\textbf{{{fmt(total['consumo'])}}}",
        "demanda": f"\\textbf{{{fmt(total['demanda'])}}}",
        "ultrapassagem": f"\\textbf{{{fmt(total['ultrapassagem'])}}}",
        "bip": f"\\textbf{{{fmt(total['bip'])}}}",
        "ere": f"\\textbf{{{fmt(total['ere'])}}}",
        "impostos": f"\\textbf{{{fmt(total['impostos'])}}}",
        "total": f"\\textbf{{{fmt(total['total'])}}}"
    })

    return tabela, total
