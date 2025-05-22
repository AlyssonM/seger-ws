import pandas as pd

# Carrega a planilha uma única vez
_tarifas_df = pd.read_excel("./src/data/dadosTarifasANEEL.xlsx", sheet_name="Export")

def get_tarifas_filtradas(
    mes_ano: str, 
    distribuidora: str, 
    modalidade: str = None, 
    subgrupo: str = None, 
    detalhe: str = "Não se aplica"
    ):
    """
    Filtra os dados tarifários com base no mês/ano (ex: JAN-2025), distribuidora, modalidade e subgrupo.
    Apenas linhas com "Base Tarifária" = "Tarifa de Aplicação" são consideradas.
    """
    import datetime

    # Mapeamento de abreviações PT -> EN
    meses_pt_para_en = {
        "JAN": "JAN", "FEV": "FEB", "MAR": "MAR", "ABR": "APR",
        "MAI": "MAY", "JUN": "JUN", "JUL": "JUL", "AGO": "AUG",
        "SET": "SEP", "OUT": "OCT", "NOV": "NOV", "DEZ": "DEC"
    }

    try:
        mes_pt, ano = mes_ano.upper().split("-")
        mes_en = meses_pt_para_en.get(mes_pt)
        if not mes_en:
            raise ValueError(f"Mês inválido: {mes_pt}")

        data_inicio = datetime.datetime.strptime(f"01-{mes_en}-{ano}", "%d-%b-%Y")
        data_fim = (data_inicio + pd.offsets.MonthEnd(1)).to_pydatetime()
    except Exception:
        return {"error": f"Formato inválido para o período: {mes_ano}. Use EX: JAN-2025"}
        
    df = _tarifas_df.copy()

    df = df[df["Sigla"].fillna("").str.upper().str.contains(distribuidora.strip().upper())]

    df = df[
        (pd.to_datetime(df["Início Vigência"]) <= data_fim) &
        (pd.to_datetime(df["Fim Vigência"]) >= data_inicio)
    ]

    df = df[df["Base Tarifária"].fillna("").str.upper() == "TARIFA DE APLICAÇÃO"]

    if modalidade:
        df = df[df["Modalidade"].fillna("").str.upper() == modalidade.strip().upper()]

    if subgrupo:
        df = df[df["Subgrupo"].fillna("").str.upper() == subgrupo.strip().upper()]

    if detalhe:
        df = df[df["Detalhe"].fillna("").str.upper() == detalhe.strip().upper()]

    if df.empty:
        return None

    return df.to_dict(orient="records")

def calcular_tarifa_verde(fatura_dados, tarifas, demanda_contratada):
    fatura_total = 0

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
        consumo = dados["consumo_ativo"]
        demanda = dados["demanda"]
        energia_injetada = consumo.get("energia_injetada_kwh", 0.0)

        # Tarifas
        tusd_fp = float(tarifas["TUSDforaPonta"])
        tusd_p = float(tarifas["TUSDponta"])
        te_fp = float(tarifas["TEforaPonta"])
        te_p = float(tarifas["TEponta"])
        demanda_fp_tarifa = float(tarifas["DemandaForaPonta"])  # mesma para ponta e fora

        energia_fp = max(0, consumo["fora_ponta_kwh"] - energia_injetada) * (tusd_fp + te_fp)
        energia_p = consumo["ponta_kwh"] * (tusd_p + te_p)

        energia_total = energia_fp + energia_p
        Ultrapassagem = 0
        Demanda = 0
        if demanda_contratada is None:
            demanda_contratada = demanda["contratada_kw"]
        maxima = demanda.get("maxima", [])
        demanda_max_ponta = next((d["valor_kw"] for d in maxima if d.get("periodo") == "ponta"), 0.0)
        demanda_max_fora_ponta = next((d["valor_kw"] for d in maxima if d.get("periodo") == "fora_ponta"), 0.0)
        demanda_max = max(demanda_max_ponta, demanda_max_fora_ponta)
        if demanda_max > demanda_contratada:
            Ultrapassagem = demanda_max - demanda_contratada
            Demanda = demanda_max
        else:
            Ultrapassagem = 0
            Demanda = demanda_contratada

        # if demanda["fora_ponta_kw"] > demanda_contratada:
        #     Ultrapassagem = demanda["fora_ponta_kw"] - demanda_contratada
        #     Demanda = demanda["fora_ponta_kw"]
        # else:
        #     Ultrapassagem = 0
        #     Demanda = demanda_contratada
        
        demanda_total = Demanda * demanda_fp_tarifa + Ultrapassagem*demanda_fp_tarifa*2

        # Extras
        iluminacao = next(
            (c["valor_total"] for c in dados["componentes_extras"]
            if "iluminação" in c["descricao"].lower() or "ilum." in c["descricao"].lower()),
            0.0
        )

        # pis = next((imp["aliquota"] for imp in dados.get("impostos", []) if imp["nome"] == "PIS"), 0.0)/100
        # cofins = next((imp["aliquota"] for imp in dados.get("impostos", []) if imp["nome"] == "COFINS"), 0.0)/100
        bandeira = sum([c["valor_total"] for c in dados["componentes_extras"] if "bandeira" in c["descricao"].lower()])
        
        bandeira_liquido = bandeira - bandeira * (pis_aliq + cofins_aliq) / 100
        
        extras = [
            {"descricao": c["descricao"], "valor_total": c["valor_total"]}
            for c in dados["componentes_extras"]
            if c["valor_total"] not in [bandeira, iluminacao]
        ]

        total_sem_imposto = energia_total + demanda_total + bandeira_liquido
        fatura_total += total_sem_imposto/(1 - (pis_aliq + cofins_aliq)/100) + iluminacao

    return round(fatura_total,2)
    # return {
    #     "total_sem_imposto": round(total_sem_imposto, 2),
    #     "energia_ativa": round(energia_total, 2),
    #     "demanda": round(demanda_total, 2),
    #     "bandeira": round(bandeira_liquido, 2),
    #     "iluminacao_publica": round(iluminacao, 2),
    #     "componentes_extras": extras,
    #     "fatura_total": round(fatura_total,2)
    # }

def calcular_tarifa_azul(fatura_dados, tarifas, dm):
    demanda_p, demanda_fp = dm
    fatura_total = 0

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
        consumo = dados["consumo_ativo"]
        demanda = dados["demanda"]
        energia_injetada = consumo.get("energia_injetada_kwh", 0.0)

        # Tarifas
        tusd_fp = float(tarifas["TUSDforaPonta"])
        tusd_p = float(tarifas["TUSDponta"])
        te_fp = float(tarifas["TEforaPonta"])
        te_p = float(tarifas["TEponta"])
        demanda_fp_tarifa = float(tarifas["DemandaForaPonta"])
        demanda_p_tarifa = float(tarifas["DemandaPonta"])

        energia_fp = max(0, consumo["fora_ponta_kwh"] - energia_injetada) * (tusd_fp + te_fp)
        energia_p = consumo["ponta_kwh"] * (tusd_p + te_p)

        energia_total = energia_fp + energia_p
        Ultrapassagem_ponta = 0
        Ultrapassagem_fora_ponta = 0
        Demanda_ponta = 0
        Demanda_fora_ponta = 0
        maxima = demanda.get("maxima", [])
        demanda_max_ponta = next((d["valor_kw"] for d in maxima if d.get("periodo") == "ponta"), 0.0)
        demanda_max_fora_ponta = next((d["valor_kw"] for d in maxima if d.get("periodo") == "fora_ponta"), 0.0)

        if demanda_max_fora_ponta > demanda_fp:
            Ultrapassagem_fora_ponta = demanda_max_fora_ponta - demanda_fp
            Demanda_fora_ponta = demanda_max_fora_ponta
        else:
            Ultrapassagem_fora_ponta = 0
            Demanda_fora_ponta = demanda_fp

        if demanda_max_ponta > demanda_p:
            Ultrapassagem_ponta = demanda_max_ponta - demanda_p
            Demanda_ponta = demanda_max_ponta
        else:
            Ultrapassagem_ponta = 0
            Demanda_ponta = demanda_p

        demanda_total = Demanda_fora_ponta*demanda_fp_tarifa + Ultrapassagem_fora_ponta*demanda_fp_tarifa*2 + Demanda_ponta*demanda_p_tarifa + Ultrapassagem_ponta*demanda_p_tarifa*2

        # Extras
        iluminacao = next(
            (c["valor_total"] for c in dados["componentes_extras"]
            if "iluminação" in c["descricao"].lower() or "ilum." in c["descricao"].lower()),
            0.0
        )

        # pis = next((imp["aliquota"] for imp in dados.get("impostos", []) if imp["nome"] == "PIS"), 0.0)/100
        # cofins = next((imp["aliquota"] for imp in dados.get("impostos", []) if imp["nome"] == "COFINS"), 0.0)/100
        
        bandeira = sum([c["valor_total"] for c in dados["componentes_extras"] if "bandeira" in c["descricao"].lower()])
        bandeira_liquido = bandeira - bandeira * (pis_aliq + cofins_aliq) / 100

        extras = [
            {"descricao": c["descricao"], "valor_total": c["valor_total"]}
            for c in dados["componentes_extras"]
            if c["valor_total"] not in [bandeira, iluminacao]
        ]

        total_sem_imposto = energia_total + demanda_total + bandeira_liquido
        fatura_total += total_sem_imposto/(1 - (pis_aliq + cofins_aliq)/100) + iluminacao
        
    return round(fatura_total,2)
    # return {
    #     "total_sem_imposto": round(total_sem_imposto, 2),
    #     "energia_ativa": round(energia_total, 2),
    #     "demanda_total": round(demanda_total, 2),
    #     "bandeira": round(bandeira_liquido, 2),
    #     "iluminacao_publica": round(iluminacao, 2),
    #     "componentes_extras": extras,
    #     "fatura_total": round(fatura_total,2)
    # }

def calcular_tarifa_bt(fatura_dados, tarifas):
    fatura_total = 0

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
        consumo = dados["consumo_ativo"]
    
        # Tarifas
        tusd = float(tarifas["TUSDforaPonta"])
        te = float(tarifas["TEforaPonta"])


        energia_fp = consumo["fora_ponta_kwh"] * (tusd + te)
        energia_p = consumo["ponta_kwh"] * (tusd + te)

        energia_total = energia_fp + energia_p
    
        # Extras
        iluminacao = next(
            (c["valor_total"] for c in dados["componentes_extras"]
            if "iluminação" in c["descricao"].lower() or "ilum." in c["descricao"].lower()),
            0.0
        )

        # pis = next((imp["aliquota"] for imp in dados.get("impostos", []) if imp["nome"] == "PIS"), 0.0)/100
        # cofins = next((imp["aliquota"] for imp in dados.get("impostos", []) if imp["nome"] == "COFINS"), 0.0)/100
        bandeira = sum([c["valor_total"] for c in dados["componentes_extras"] if "bandeira" in c["descricao"].lower()])
        bandeira_liquido = bandeira - bandeira * (pis_aliq + cofins_aliq) / 100

        extras = [
            {"descricao": c["descricao"], "valor_total": c["valor_total"]}
            for c in dados["componentes_extras"]
            if c["valor_total"] not in [bandeira, iluminacao]
        ]

        total_sem_imposto = energia_total + bandeira_liquido
        fatura_total += total_sem_imposto/(1 - (pis_aliq + cofins_aliq)/100) + iluminacao

    return round(fatura_total,2)

def extrair_tarifa_compacta_por_modalidade(lista_tarifas):
    resultado = {}

    for item in lista_tarifas:
        modalidade = item.get("Modalidade", "Desconhecida").strip().lower()
        posto = item.get("Posto", "").strip().lower()
        unidade = item.get("Unidade", "").strip().lower()
        te = item.get("TE", 0.0)
        tusd = item.get("TUSD", 0.0)

        if modalidade not in resultado:
            resultado[modalidade] = {}

        r = resultado[modalidade]

        if modalidade == "azul":
            if unidade == "r$/mwh":
                if posto == "fora ponta":
                    r["TEforaPonta"] = te
                    r["TUSDforaPonta"] = tusd
                elif posto == "ponta":
                    r["TEponta"] = te
                    r["TUSDponta"] = tusd
            elif unidade == "r$/kw":
                if posto == "fora ponta":
                    r["DemandaForaPonta"] = tusd
                elif posto == "ponta":
                    r["DemandaPonta"] = tusd

        elif modalidade == "verde":
            if unidade == "r$/mwh":
                if posto == "fora ponta":
                    r["TEforaPonta"] = te
                    r["TUSDforaPonta"] = tusd
                elif posto == "ponta":
                    r["TEponta"] = te
                    r["TUSDponta"] = tusd
            elif unidade == "r$/kw":
                r["DemandaForaPonta"] = tusd

        elif modalidade == "branca":
            if unidade == "r$/mwh":
                if posto == "fora ponta":
                    r["TEforaPonta"] = te
                    r["TUSDforaPonta"] = tusd
                elif posto == "intermediário":
                    r["TEintermediario"] = te
                    r["TUSDintermediario"] = tusd
                elif posto == "ponta":
                    r["TEponta"] = te
                    r["TUSDponta"] = tusd

        elif modalidade == "convencional":
            if unidade == "r$/mwh":
                r["TEforaPonta"] = te
                r["TUSDforaPonta"] = tusd

    return resultado