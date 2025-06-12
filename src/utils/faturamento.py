from datetime import date
from typing import List, Dict, Tuple, Any, Optional
from .tarifas import calcular_tarifa_verde, calcular_tarifa_azul, calcular_tarifa_bt
import logging

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

def gerar_dados_contextuais_integrado(res, fatura_dados, ultrapassagem_ocorre, atualizado_aumento, demanda_verde_otima, demanda_azul_p, demanda_azul_fp):
    atual = next((x for x in res["tabela_contrato_comparado"] if "ATUAL" in x["data"]), {})
    proposto = next((x for x in res["tabela_contrato_comparado"] if "PROPOSTO" in x["data"]), {})

    f1 = fatura_dados[0]
    ident = f1.get("identificacao", {})

    grupo = ident.get("grupo_tarifario", "A")
    subgrupo = "A4" if grupo == "A" else "-"
    classe = ident.get("classe", "").title()

    dados_meta = {
        "Unidade": ident.get("unidade", ""),
        "Autores": "Alysson Machado \\\ Helder Rocha \\\ Lohane \\\ Jules Carneiro \\\ Lohane Palaoro \\\ Luiz Virgílio Aranda \\\ Rodrigo Fiorotti \\\ Marcelo Segatto",
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
        "demandaAtual": format_kw(f1.get("demanda", {}).get("contratada_fp_kw", 0.0)),
        "demandaNova": format_kw(demanda_verde_otima),
        "numContas": str(len(fatura_dados)),
        "baseDadosInic": ident.get("mes_referencia", "n/a"),
        "baseDadosFinal": fatura_dados[-1].get("identificacao", {}).get("mes_referencia", "n/a"),
        "dadosAnaliseInic": ident.get("mes_referencia", "n/a"),
        "dadosAnaliseFinal": fatura_dados[-1].get("identificacao", {}).get("mes_referencia", "n/a"),
        "custoContratoAtual": atual.get("total", "0,00").replace("\\textbf{", "").replace("}", ""),
        "custoContratoNovo": proposto.get("total", "0,00").replace("\\textbf{", "").replace("}", ""),
        "ultrapassagem_ocorre": ultrapassagem_ocorre,
        "atualizado_aumento": atualizado_aumento,
        "DemandaAzulPonta": format_kw(demanda_azul_p),
        "DemandaAzulForaPonta": format_kw(demanda_azul_fp),
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

def calcular_tabela_12meses(fatura_dados, tarifas, tarifa_ere, demanda_verde_otima, demanda_azul_p_otima, demanda_azul_fp_otima):
    def formatar(valor):
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    tabela_otimizada = []
    total_azul = total_verde = total_bt = 0.0

    total_verde, lista_verde_mensal = calcular_tarifa_verde(fatura_dados, tarifas["verde"], tarifa_ere, demanda_verde_otima)
    total_azul, lista_azul_mensal = calcular_tarifa_azul(fatura_dados, tarifas["azul"], tarifa_ere, [demanda_azul_p_otima, demanda_azul_fp_otima])
    total_bt, lista_bt_mensal = calcular_tarifa_bt(fatura_dados, tarifas["convencional"])

    for verde, azul, bt in zip(lista_verde_mensal, lista_azul_mensal, lista_bt_mensal):
        mesref = verde["mes"].lower().replace("/20", "/")[0:3] + verde["mes"][-2:]  # exemplo: "jul/23"
        tabela_otimizada.append({
            "data": mesref,
            "verde": formatar(verde["valor_fatura"]),
            "azul": formatar(azul["valor_fatura"]),
            "bt": formatar(bt["valor_fatura"]),
        })

    tabela_otimizada.append({
        "data": "TOTAL APÓS 12 MESES",
        "verde": formatar(total_verde),
        "azul": formatar(total_azul),
        "bt": formatar(total_bt),
    })

    return tabela_otimizada

def calcular_tabela_ajuste(fatura_dados, tarifas_atualizado, tarifa_ere, demanda_base=570.0):
    def formatar(valor):
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    tabela_ajuste = []
    valor_real = []
    total_realizado = 0.0
    total_atualizado = 0.0

    # Chamada única com todo o histórico
    total_verde, lista_verde_mensal = calcular_tarifa_verde(fatura_dados, tarifas_atualizado["verde"], tarifa_ere, demanda_base)
    # total_azul, lista_azul_mensal = calcular_tarifa_azul(fatura_dados, tarifas_atualizado["azul"], tarifa_ere, [demanda_azul_p_otima, demanda_azul_fp_otima])

    for f in fatura_dados:
    #     ident = f.get("identificacao", {})
    #     mesref = ident.get("mes_referencia", "N/A")
    #     mes_label = mesref.lower().replace("/20", "/")[0:3] + mesref[-2:]
        valor_mensal = f.get("valores_totais", {}).get("valor_total_fatura", 0.0)
        valor_real.append(valor_mensal)
        # valor_real = f.get("valores_totais", {}).get("valor_total_fatura", 0.0)
        total_realizado += valor_mensal

    for real, atualizado in zip(valor_real,lista_verde_mensal):
        mesref = atualizado["mes"].lower().replace("/20", "/")[0:3] + atualizado["mes"][-2:]  # exemplo: "jul/23"
        tabela_ajuste.append({
            "mes": mesref,
            "realizado": formatar(real),
            "atualizado": formatar(atualizado["valor_fatura"]),
        })
    
    tabela_ajuste.append({
        "mes": "TOTAL",
        "realizado": formatar(sum(valor_real)),
        "atualizado": formatar(total_verde),
        "ajuste": total_realizado - sum(valor_real)
    })

    return tabela_ajuste

def calcular_tabela_contrato_atual(
    fatura_dados, 
    tarifas_atualizado,
    tarifa_ere, 
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

    fatura_total = 0
    faturas_mensais = []
    # ---------- Cálculo das médias de impostos ---------- #
    pis_total = 0.0
    cofins_total = 0.0
    icms_total = 0.0
    count_pis = count_cofins = count_icms = 0

    for f in fatura_dados:
        impostos = f.get("impostos", [])

        for imp in impostos:
            nome = imp.get("nome", "").upper()
            aliq = imp.get("aliquota", 0.0)
            if nome == "PIS":
                pis_total += aliq/100
                count_pis += 1
            elif nome == "COFINS":
                cofins_total += aliq/100
                count_cofins += 1
            elif nome == "ICMS":
                icms_total += aliq/100
                count_icms += 1

    # Médias em percentual (já prontas para uso)
    pis_media = pis_total / count_pis if count_pis else 0.0
    cofins_media = cofins_total / count_cofins if count_cofins else 0.0
    icms_media = icms_total / count_icms if count_icms else 0.0

    # Para uso nos cálculos posteriores (convertendo para frações)
    pis_aliq = pis_media
    cofins_aliq = cofins_media
    icms_aliq = icms_media

    for dados in fatura_dados:
        ident = dados.get("identificacao", {})
        mesref = ident.get("mes_referencia", "N/A")
        mes_formatado = mesref.lower().replace("/20", "/")[0:3] + mesref[-2:]
        # logging.info(f"Mes: {dados['identificacao']['mes_referencia']}")
        consumo = dados["consumo_ativo"]
        demanda = dados["demanda"]
        energia_reativa_ere = dados["energia_reativa"]
        energia_injetada = consumo.get("energia_injetada_kwh", 0.0)
        extras = dados["componentes_extras"]

        # Tarifas
        logging.info(f"Tarifas atualizadas: {tarifas_atualizado}")
        tusd_fp = float(tarifas_atualizado['verde']["TUSDforaPonta"])
        tusd_p = float(tarifas_atualizado['verde']["TUSDponta"])
        te_fp = float(tarifas_atualizado['verde']["TEforaPonta"])
        te_p = float(tarifas_atualizado['verde']["TEponta"])
    
        demanda_fp_tarifa = float(tarifas_atualizado['verde']["DemandaForaPonta"])  # mesma para ponta e fora
        # # logging.info(f"SCEE = {energia_injetada}")
        energia_fp = consumo["fora_ponta_kwh"] * (tusd_fp + te_fp)
        energia_p = consumo["ponta_kwh"] * (tusd_p + te_p)
        energia_compensada = energia_injetada * (tusd_fp + te_fp)
        energia_reativa_ex = tarifa_ere * energia_reativa_ere["excedente"]["total_kwh"]
        energia_total = energia_fp + energia_p
        # logging.info(f"custo energia fp: {energia_fp}")
        # logging.info(f"custo energia p: {energia_p}")
        # logging.info(f"custo energia compensada: {energia_compensada}")
        # logging.info(f"custo energia reativa excedente: {energia_reativa_ex}")
        Ultrapassagem = 0
        Demanda = 0
        demanda_contratada = float(demanda["contratada_fp_kw"])
        if consumo["energia_injetada_kwh"]:
            demanda_max = demanda["fora_ponta_kw"]
            # logging.info(f"demanda contratada: {demanda_contratada}")
            # logging.info(f"demanda fora ponta: {demanda_max}")
            if demanda_max > demanda_contratada and demanda_max/demanda_contratada > 1.05:
                Ultrapassagem = demanda_max - demanda_contratada
                Demanda = demanda_max
            else:
                Ultrapassagem = 0
                Demanda = demanda_contratada
        else:
            if demanda_contratada is None:
                demanda_contratada = float(demanda["contratada_fp_kw"])
            maxima = demanda.get("maxima", [])
            demanda_max_ponta = next((d["valor_kw"] for d in maxima if d.get("periodo") == "ponta"), 0.0)
            demanda_max_fora_ponta = next((d["valor_kw"] for d in maxima if d.get("periodo") == "fora_ponta"), 0.0)
            demanda_max = max(demanda_max_ponta, demanda_max_fora_ponta)
            # logging.info(f"demanda contratada: {demanda_contratada}")
            # logging.info(f"demanda fora ponta: {demanda_max}")
            if demanda_max > demanda_contratada and demanda_max/demanda_contratada > 1.05:
                Ultrapassagem = demanda_max - demanda_contratada
                Demanda = demanda_max
            else:
                Ultrapassagem = 0
                if demanda_max > demanda_contratada:
                    Demanda = demanda_max
                else:
                    Demanda = demanda_contratada
   
        custo_demanda_fp = Demanda * demanda_fp_tarifa
        custo_ultrapassagem = Ultrapassagem * demanda_fp_tarifa * 2
        demanda_total = custo_demanda_fp + custo_ultrapassagem
        # logging.info(f"custo demanda fp: {custo_demanda_fp}")
        # logging.info(f"custo ultrapassagem: {custo_ultrapassagem}")
        # logging.info(f"custo demanda: {demanda_total}")
        # Extras
        iluminacao = next(
            (c["valor_total"] for c in dados["componentes_extras"]
            if "iluminação" in c["descricao"].lower() or "ilum." in c["descricao"].lower()),
            0.0
        )

        # pis = next((imp["aliquota"] for imp in dados.get("impostos", []) if imp["nome"] == "PIS"), 0.0)/100
        # cofins = next((imp["aliquota"] for imp in dados.get("impostos", []) if imp["nome"] == "COFINS"), 0.0)/100
        bandeira = sum([c["valor_total"] for c in dados["componentes_extras"] if "bandeira" in c["descricao"].lower()])
        
        bandeira_impostos = sum(
            c.get("valor_impostos", 0.0) or 0.0
            for c in dados["componentes_extras"]
            if "bandeira" in c.get("descricao", "").lower()
        )
        bandeira_liquido = bandeira - bandeira_impostos  #bandeira * (pis_aliq + cofins_aliq) / 100
        
        extras = [
            {"descricao": c["descricao"], "valor_total": c["valor_total"]}
            for c in dados["componentes_extras"]
            if c["valor_total"] not in [bandeira, iluminacao]
        ]
        # logging.info(f"custo iluminacao: {iluminacao}")
        # logging.info(f"custo bandeira: {bandeira_liquido}")

        irrf_demanda = 0
        
        if consumo["energia_injetada_kwh"]:
            irrf_demanda = (demanda_total * 4.8/100)/(1 - (pis_aliq + cofins_aliq)/100)
        total_sem_imposto = energia_total + demanda_total + bandeira_liquido - energia_compensada + energia_reativa_ex
        # # logging.info(f"custo total sem imposto: {total_sem_imposto}")
        # # logging.info(f"pis:{pis_aliq} cofins:{cofins_aliq}")

        # irrf_comp = next((c["valor_impostos"] for c in dados["componentes_extras"] if ("imposto de renda" or "Demanda Imposto Renda") in c["descricao"].lower()), 0.0)
        irrf_comp = sum(
            c.get("valor_impostos", 0.0) or 0.0
            for c in dados["componentes_extras"]
            if any(
                termo in c.get("descricao", "").lower()
                for termo in ["imposto de renda", "demanda imposto renda"]
            )
        )
        juros = next((c["valor_total"] for c in dados["componentes_extras"] if "juros" in c["descricao"].lower()), 0.0)
        multa = next((c["valor_total"] for c in dados["componentes_extras"] if "multa" in c["descricao"].lower()), 0.0)

        # logging.info(f"Juros: {juros}, Multa: {multa}")
        # logging.info(f"custo imposto de renda: {irrf_comp}")
        fatura_mes = (total_sem_imposto / (1 - (pis_aliq + cofins_aliq) / 100)
            + iluminacao
            - irrf_demanda*0
            + irrf_comp
            + juros
            + multa
        )
        # logging.info(f"fatura mes {dados['identificacao']['mes_referencia']}: {fatura_mes}")
        fatura_total += fatura_mes
        faturas_mensais.append({
            "mes": dados["identificacao"].get("mes_referencia", "N/A"),
            "valor_fatura": round(fatura_mes, 2)
        })
        
        total_consumo = energia_total
        contratada = demanda_contratada
        valor_ultrapassagem = Ultrapassagem
        valor_demanda = custo_demanda_fp
        ere = energia_reativa_ex
        impostos_valor = total_sem_imposto / (1 - (pis_aliq + cofins_aliq + icms_aliq)/100) * (pis_aliq + cofins_aliq + icms_aliq)/100
        total_geral = fatura_mes
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
    tarifa_ere, 
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

    fatura_total = 0
    faturas_mensais = []
    # ---------- Cálculo das médias de impostos ---------- #
    pis_total = 0.0
    cofins_total = 0.0
    icms_total = 0.0
    count_pis = count_cofins = count_icms = 0

    for f in fatura_dados:
        impostos = f.get("impostos", [])

        for imp in impostos:
            nome = imp.get("nome", "").upper()
            aliq = imp.get("aliquota", 0.0)
            if nome == "PIS":
                pis_total += aliq/100
                count_pis += 1
            elif nome == "COFINS":
                cofins_total += aliq/100
                count_cofins += 1
            elif nome == "ICMS":
                icms_total += aliq/100
                count_icms += 1

    # Médias em percentual (já prontas para uso)
    pis_media = pis_total / count_pis if count_pis else 0.0
    cofins_media = cofins_total / count_cofins if count_cofins else 0.0
    icms_media = icms_total / count_icms if count_icms else 0.0

    # Para uso nos cálculos posteriores (convertendo para frações)
    pis_aliq = pis_media
    cofins_aliq = cofins_media
    icms_aliq = icms_media

    for dados in fatura_dados:
        ident = dados.get("identificacao", {})
        mesref = ident.get("mes_referencia", "N/A")
        mes_formatado = mesref.lower().replace("/20", "/")[0:3] + mesref[-2:]
        # logging.info(f"Mes: {dados['identificacao']['mes_referencia']}")
        consumo = dados["consumo_ativo"]
        demanda = dados["demanda"]
        energia_reativa_ere = dados["energia_reativa"]
        energia_injetada = consumo.get("energia_injetada_kwh", 0.0)
        extras = dados["componentes_extras"]

        # Tarifas
        logging.info(f"Tarifas atualizadas: {tarifas_atualizado}")
        tusd_fp = float(tarifas_atualizado['verde']["TUSDforaPonta"])
        tusd_p = float(tarifas_atualizado['verde']["TUSDponta"])
        te_fp = float(tarifas_atualizado['verde']["TEforaPonta"])
        te_p = float(tarifas_atualizado['verde']["TEponta"])
    
        demanda_fp_tarifa = float(tarifas_atualizado['verde']["DemandaForaPonta"])  # mesma para ponta e fora
        # # logging.info(f"SCEE = {energia_injetada}")
        energia_fp = consumo["fora_ponta_kwh"] * (tusd_fp + te_fp)
        energia_p = consumo["ponta_kwh"] * (tusd_p + te_p)
        energia_compensada = energia_injetada * (tusd_fp + te_fp)
        energia_reativa_ex = tarifa_ere * energia_reativa_ere["excedente"]["total_kwh"]
        energia_total = energia_fp + energia_p
        # logging.info(f"custo energia fp: {energia_fp}")
        # logging.info(f"custo energia p: {energia_p}")
        # logging.info(f"custo energia compensada: {energia_compensada}")
        # logging.info(f"custo energia reativa excedente: {energia_reativa_ex}")
        Ultrapassagem = 0
        Demanda = 0
        demanda_contratada = demanda_verde_otima
        if consumo["energia_injetada_kwh"]:
            demanda_max = demanda["fora_ponta_kw"]
            # logging.info(f"demanda contratada: {demanda_contratada}")
            # logging.info(f"demanda fora ponta: {demanda_max}")
            if demanda_max > demanda_contratada and demanda_max/demanda_contratada > 1.05:
                Ultrapassagem = demanda_max - demanda_contratada
                Demanda = demanda_max
            else:
                Ultrapassagem = 0
                Demanda = demanda_contratada
        else:
            if demanda_contratada is None:
                demanda_contratada = demanda_verde_otima
            maxima = demanda.get("maxima", [])
            demanda_max_ponta = next((d["valor_kw"] for d in maxima if d.get("periodo") == "ponta"), 0.0)
            demanda_max_fora_ponta = next((d["valor_kw"] for d in maxima if d.get("periodo") == "fora_ponta"), 0.0)
            demanda_max = max(demanda_max_ponta, demanda_max_fora_ponta)
            # logging.info(f"demanda contratada: {demanda_contratada}")
            # logging.info(f"demanda fora ponta: {demanda_max}")
            if demanda_max > demanda_contratada and demanda_max/demanda_contratada > 1.05:
                Ultrapassagem = demanda_max - demanda_contratada
                Demanda = demanda_max
            else:
                Ultrapassagem = 0
                if demanda_max > demanda_contratada:
                    Demanda = demanda_max
                else:
                    Demanda = demanda_contratada

        
        custo_demanda_fp = Demanda * demanda_fp_tarifa
        custo_ultrapassagem = Ultrapassagem * demanda_fp_tarifa * 2
        demanda_total = custo_demanda_fp + custo_ultrapassagem
        # logging.info(f"custo demanda fp: {custo_demanda_fp}")
        # logging.info(f"custo ultrapassagem: {custo_ultrapassagem}")
        # logging.info(f"custo demanda: {demanda_total}")
        # Extras
        iluminacao = next(
            (c["valor_total"] for c in dados["componentes_extras"]
            if "iluminação" in c["descricao"].lower() or "ilum." in c["descricao"].lower()),
            0.0
        )

        # pis = next((imp["aliquota"] for imp in dados.get("impostos", []) if imp["nome"] == "PIS"), 0.0)/100
        # cofins = next((imp["aliquota"] for imp in dados.get("impostos", []) if imp["nome"] == "COFINS"), 0.0)/100
        bandeira = sum([c["valor_total"] for c in dados["componentes_extras"] if "bandeira" in c["descricao"].lower()])
        
        bandeira_impostos = sum(
            c.get("valor_impostos", 0.0) or 0.0
            for c in dados["componentes_extras"]
            if "bandeira" in c.get("descricao", "").lower()
        )
        bandeira_liquido = bandeira - bandeira_impostos  #bandeira * (pis_aliq + cofins_aliq) / 100
        
        extras = [
            {"descricao": c["descricao"], "valor_total": c["valor_total"]}
            for c in dados["componentes_extras"]
            if c["valor_total"] not in [bandeira, iluminacao]
        ]
        # logging.info(f"custo iluminacao: {iluminacao}")
        # logging.info(f"custo bandeira: {bandeira_liquido}")

        irrf_demanda = 0
        
        if consumo["energia_injetada_kwh"]:
            irrf_demanda = (demanda_total * 4.8/100)/(1 - (pis_aliq + cofins_aliq)/100)
        total_sem_imposto = energia_total + demanda_total + bandeira_liquido - energia_compensada + energia_reativa_ex
        # # logging.info(f"custo total sem imposto: {total_sem_imposto}")
        # # logging.info(f"pis:{pis_aliq} cofins:{cofins_aliq}")

        # irrf_comp = next((c["valor_impostos"] for c in dados["componentes_extras"] if ("imposto de renda" or "Demanda Imposto Renda") in c["descricao"].lower()), 0.0)
        irrf_comp = sum(
            c.get("valor_impostos", 0.0) or 0.0
            for c in dados["componentes_extras"]
            if any(
                termo in c.get("descricao", "").lower()
                for termo in ["imposto de renda", "demanda imposto renda"]
            )
        )
        juros = next((c["valor_total"] for c in dados["componentes_extras"] if "juros" in c["descricao"].lower()), 0.0)
        multa = next((c["valor_total"] for c in dados["componentes_extras"] if "multa" in c["descricao"].lower()), 0.0)

        # logging.info(f"Juros: {juros}, Multa: {multa}")
        # logging.info(f"custo imposto de renda: {irrf_comp}")
        fatura_mes = (total_sem_imposto / (1 - (pis_aliq + cofins_aliq) / 100)
            + iluminacao
            - irrf_demanda*0
            + irrf_comp
            + juros
            + multa
        )
        # logging.info(f"fatura mes {dados['identificacao']['mes_referencia']}: {fatura_mes}")
        fatura_total += fatura_mes
        faturas_mensais.append({
            "mes": dados["identificacao"].get("mes_referencia", "N/A"),
            "valor_fatura": round(fatura_mes, 2)
        })
        
        total_consumo = energia_total
        contratada = demanda_contratada
        valor_ultrapassagem = Ultrapassagem
        valor_demanda = custo_demanda_fp
        ere = energia_reativa_ex
        impostos_valor = total_sem_imposto / (1 - (pis_aliq + cofins_aliq + icms_aliq)/100) * (pis_aliq + cofins_aliq + icms_aliq)/100
        total_geral = fatura_mes

        total["consumo"] += total_consumo
        total["demanda"] += valor_demanda
        total["ultrapassagem"] += valor_ultrapassagem
        total["bip"] += bandeira_liquido + iluminacao
        total["ere"] += ere
        total["impostos"] += impostos_valor
        total["total"] += total_geral
        logging.info(f'Total: {total["demanda"]}')

    logging.info(f'Total: {total["demanda"]}')
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
