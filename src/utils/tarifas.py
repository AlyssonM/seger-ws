import pandas as pd
import logging
import datetime
import re

# Carrega a planilha uma única vez
_tarifas_df = pd.read_excel("./src/data/dadosTarifasANEEL.xlsx", sheet_name="Export")

def get_tarifas_filtradas(
    mes_ano: str, 
    distribuidora: str, 
    modalidade: str = None, 
    subgrupo: str = None, 
    classe: str = None,
    detalhe: str = None
    ):

    # logging.info(f"get_tarifas_filtradas(mes_ano={mes_ano}, distribuidora={distribuidora}, modalidade={modalidade}, subgrupo={subgrupo}, classe={classe}, detalhe={detalhe})")
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
        
    try:
        df = _tarifas_df.copy()

        # Filtro por distribuidora
        distribuidora_pattern = re.escape(distribuidora.strip().upper())
        df = df[df["Sigla"].fillna("").str.upper().str.contains(distribuidora_pattern, na=False, regex=True)]

        # Filtro por vigência
        df = df[
            (pd.to_datetime(df["Início Vigência"], errors="coerce") <= data_fim) &
            (pd.to_datetime(df["Fim Vigência"], errors="coerce") >= data_inicio)
        ]

        # Base Tarifária
        df = df[df["Base Tarifária"].fillna("").str.upper().str.strip() == "TARIFA DE APLICAÇÃO"]

        # Modalidade
        if modalidade:
            pattern = re.escape(modalidade.strip().upper())
            df = df[df["Modalidade"].fillna("").str.upper().str.contains(pattern, na=False, regex=True)]

        # Subgrupo
        if subgrupo:
            pattern = re.escape(subgrupo.strip().upper())
            df = df[df["Subgrupo"].fillna("").str.upper().str.contains(pattern, na=False, regex=True)]

        # Classe
        if classe:
            pattern = re.escape(classe.strip().upper())
            df = df[df["Classe"].fillna("").str.upper().str.contains(pattern, na=False, regex=True)]

        # Detalhe
        if detalhe:
            pattern = re.escape(detalhe.strip().upper())
            df = df[df["Detalhe"].fillna("").str.upper().str.contains(pattern, na=False, regex=True)]

        if df.empty:
            return None

        return df.to_dict(orient="records")

    except Exception as e:
        return {"error": f"Erro ao filtrar dados: {e}"}

def calcular_tarifa_verde(fatura_dados, tarifas, tarifa_ere, demanda_contratada):
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
        # logging.info(f"Mes: {dados['identificacao']['mes_referencia']}")
        consumo = dados["consumo_ativo"]
        demanda = dados["demanda"]
        energia_reativa_ere = dados["energia_reativa"]
        energia_injetada = consumo.get("energia_injetada_kwh", 0.0)
        extras = dados["componentes_extras"]

        # Tarifas
        tusd_fp = float(tarifas["TUSDforaPonta"])
        tusd_p = float(tarifas["TUSDponta"])
        te_fp = float(tarifas["TEforaPonta"])
        te_p = float(tarifas["TEponta"])
    
        demanda_fp_tarifa = float(tarifas["DemandaForaPonta"])  # mesma para ponta e fora
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
        if consumo["energia_injetada_kwh"]:
            demanda_max = demanda["fora_ponta_kw"]
            demanda_contratada = float(demanda["contratada_kw"])
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
                demanda_contratada = float(demanda["contratada_kw"])
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
        
    return round(fatura_total,2),faturas_mensais

def calcular_tarifa_azul(fatura_dados, tarifas, tarifa_ere, dm):
    demanda_p, demanda_fp = dm
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

    # logging.info(f"pis:{pis_aliq} cofins:{cofins_aliq}")

    for dados in fatura_dados:
        # logging.info(f"Mes: {dados['identificacao']['mes_referencia']}")
        consumo = dados["consumo_ativo"]
        demanda = dados["demanda"]
        energia_reativa_ere = dados["energia_reativa"]
        energia_injetada = consumo.get("energia_injetada_kwh", 0.0)
        
        # Tarifas
        tusd_fp = float(tarifas["TUSDforaPonta"])
        tusd_p = float(tarifas["TUSDponta"])
        te_fp = float(tarifas["TEforaPonta"])
        te_p = float(tarifas["TEponta"])
        demanda_fp_tarifa = float(tarifas["DemandaForaPonta"])
        demanda_p_tarifa = float(tarifas["DemandaPonta"])

        energia_fp = consumo["fora_ponta_kwh"] * (tusd_fp + te_fp)
        energia_p = consumo["ponta_kwh"] * (tusd_p + te_p)
        energia_compensada = energia_injetada * (tusd_fp + te_fp)
        energia_reativa_ex = tarifa_ere * energia_reativa_ere["excedente"]["total_kwh"]
        # logging.info(f"custo energia fp: {energia_fp}")
        # logging.info(f"custo energia p: {energia_p}")
        # logging.info(f"custo energia reativa excedente: {energia_reativa_ex}")
        # logging.info(f"custo energia compensada: {energia_compensada}")
        energia_total = energia_fp + energia_p
        Ultrapassagem_ponta = 0
        Ultrapassagem_fora_ponta = 0
        Demanda_ponta = 0
        Demanda_fora_ponta = 0
        maxima = demanda.get("maxima", [])
        demanda_max_ponta = next((d["valor_kw"] for d in maxima if d.get("periodo") == "ponta"), 0.0)
        demanda_max_fora_ponta = next((d["valor_kw"] for d in maxima if d.get("periodo") == "fora_ponta"), 0.0)

        if demanda_max_fora_ponta > demanda_fp and demanda_max_fora_ponta/demanda_fp > 1.05:
            Ultrapassagem_fora_ponta = demanda_max_fora_ponta - demanda_fp
            Demanda_fora_ponta = demanda_max_fora_ponta
        else:
            Ultrapassagem_fora_ponta = 0
            if demanda_max_fora_ponta > demanda_fp:
                Demanda_fora_ponta = demanda_max_fora_ponta
            else:
                Demanda_fora_ponta = demanda_fp
            
        if demanda_max_ponta > demanda_p and demanda_max_ponta/demanda_p > 1.05:
            Ultrapassagem_ponta = demanda_max_ponta - demanda_p
            Demanda_ponta = demanda_max_ponta
        else:
            Ultrapassagem_ponta = 0
            if demanda_max_ponta > demanda_p:
                Demanda_ponta = demanda_max_ponta
            else:
                Demanda_ponta = demanda_p
            

        custo_demanda_fp = Demanda_fora_ponta*demanda_fp_tarifa
        custo_demanda_p = Demanda_ponta*demanda_p_tarifa
        custo_ultrapassagem = Ultrapassagem_fora_ponta*demanda_fp_tarifa*2 + Ultrapassagem_ponta*demanda_p_tarifa*2
        demanda_total = custo_demanda_fp + custo_demanda_p + custo_ultrapassagem  
        # logging.info(f"custo demanda fp: {custo_demanda_fp}")
        # logging.info(f"custo demanda p: {custo_demanda_p}")
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

        bandeira_liquido = bandeira - bandeira_impostos #bandeira * (pis_aliq + cofins_aliq) / 100

        # logging.info(f"custo iluminacao: {iluminacao}")
        # logging.info(f"custo bandeira: {bandeira_liquido}")

        extras = [
            {"descricao": c["descricao"], "valor_total": c["valor_total"]}
            for c in dados["componentes_extras"]
            if c["valor_total"] not in [bandeira, iluminacao]
        ]
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

        total_sem_imposto = energia_total + demanda_total + bandeira_liquido - energia_compensada + energia_reativa_ex
        # logging.info(f"custo total sem imposto: {total_sem_imposto}")

        fatura_mes = (total_sem_imposto / (1 - (pis_aliq + cofins_aliq) / 100)
            + iluminacao
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

    return round(fatura_total,2),faturas_mensais

def calcular_tarifa_bt(fatura_dados, tarifas):
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
        
        bandeira_impostos = sum(
            c.get("valor_impostos", 0.0) or 0.0
            for c in dados["componentes_extras"]
            if "bandeira" in c.get("descricao", "").lower()
        )

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

        bandeira_liquido = bandeira - bandeira_impostos #bandeira * (pis_aliq + cofins_aliq) / 100

        extras = [
            {"descricao": c["descricao"], "valor_total": c["valor_total"]}
            for c in dados["componentes_extras"]
            if c["valor_total"] not in [bandeira, iluminacao]
        ]

        total_sem_imposto = energia_total + bandeira_liquido
        # fatura_total += total_sem_imposto/(1 - (pis_aliq + cofins_aliq)/100) + iluminacao

        fatura_mes = (total_sem_imposto / (1 - (pis_aliq + cofins_aliq) / 100)
            + iluminacao
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

    return round(fatura_total,2),faturas_mensais

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
        
        elif modalidade == "convencional pré-pagamento":
            if unidade == "r$/mwh":
                r["TEforaPonta"] = te
                r["TUSDforaPonta"] = tusd

    return resultado