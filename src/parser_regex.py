"""
edp_invoice_parser.py  –  (rev. 2025-05-13)
-------------------------------------------

$ python edp_invoice_parser.py fatura_EDP_fev_2025.pdf
"""
#src/parser_regex.py
from __future__ import annotations

import json, re, sys
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PyPDF2 import PdfReader


# ╭─────────────────────────  HELPERS  ─────────────────────────╮
NUMBER = r"\d+[.,]\d+|\d{1,3}(?:\.\d{3})*(?:[.,]\d+)?|\d+"
DECIMAL = r"-?\d{1,3}(?:\.\d{3})*(?:,\d+)?-?"

def _clean_num(n: str | None) -> float | None:
    if not n:
        return None
    s = n.strip()
    # detecta sinal no fim
    neg = s.endswith("-")
    # remove qualquer traço inicial ou final
    s = s.lstrip("-").rstrip("-")
    # normaliza para float Python
    s = s.replace(".", "").replace(",", ".")
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def _find(pat: str, text: str, flags=0, group: int | str = 1, default=None):
    m = re.search(pat, text, flags)
    if not m:
        return default
    try:
        return m[group]
    except IndexError:
        return m[0]


def _findall(pat: str, text: str, flags=0) -> List[Tuple[str, ...]]:
    return [m.groups() for m in re.finditer(pat, text, flags)]


def formatar_proprio_title(texto: str) -> str:
    # Corrige falta de espaço após vírgulas (ex: ",123" → ", 123")
    texto = re.sub(r",(?=\S)", ", ", texto)

    # Expansão de abreviações comuns (apenas se forem palavras isoladas)
    abrevs = {
        r'\bSec\b': 'Secretaria do',
        r'\bEst\b': 'Estado',
        r'\bRecurs\b': 'Recursos',  # para correções como "RECURS S HUMANOS"
        r'\bGovr\b': 'Governador',
        r'\bDept\b': 'Departamento',
        r'\bUnid\b': 'Unidade',
        r'\bAdm\b': 'Administrativo',
    }
    for padrao, subst in abrevs.items():
        texto = re.sub(padrao, subst, texto, flags=re.IGNORECASE)

    # Aplica capitalização
    def custom_title_case(text):
        words = text.lower().split()
        titled_words = []
        for word in words:
            # Lista de conjunções e preposições que não devem ser capitalizadas (pode ser expandida)
            if word in ["e", "de", "da", "do", "das", "dos", "para", "com"]:
                titled_words.append(word)
            else:
                titled_words.append(word.capitalize())
        return " ".join(titled_words)

    resultado = custom_title_case(texto)


    # Corrige siglas específicas que devem ficar em maiúsculas
    siglas = {
        r'\bEs\b': 'ES',
        r'\bSn\b': 'SN',
        r'\bIe\b': 'IE',
        r'\bCep\b': 'CEP',
        r'\bCnpj\b': 'CNPJ',
    }
    for padrao, subst in siglas.items():
        resultado = re.sub(padrao, subst, resultado)

    return resultado

# ╭────────────────────  NÚCLEO DE EXTRAÇÃO  ───────────────────╮
def extrair_dados_completos_da_fatura_regex(texto: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "identificacao": {},
        "leituras": {},
        "consumo_ativo": {},
        "demanda": {},
        "energia_reativa": {},
        "impostos": [],
        "tarifas": {},
        "componentes_extras": []
    }
    
    identificacao = {}
    # logging.info("Extraindo endereço...")
    # Endereço

    lines = texto.splitlines()

    # Busca o CNPJ da EDP (distribuidora) e do cliente
    cnpj_linhas = [(i, ln.strip()) for i, ln in enumerate(lines) if re.search(r"CNPJ[:\s]*\d{8,}", ln)]

    if len(cnpj_linhas) >= 2:
        # Segunda ocorrência é o CNPJ do cliente
        idx, _ = cnpj_linhas[1]
        
        # Procura linha com CEP (com ou sem "CEP:")
        for j in range(idx-1, max(idx-10, 0), -1):  # tenta mais linhas
            if re.search(r"\d{5}-\d{3}", lines[j]):
                cep_line = lines[j]
                local_line = lines[j-1].strip()
                logradouro_line = lines[j-2].strip()
                unidade_candidates = []

                # Coleta até 4 linhas acima do logradouro
                for k in range(j - 3, j - 7, -1):
                    if k < 0:
                        continue
                    l = lines[k].strip()
                    if not l or re.search(r"EDP|Distrib", l, re.I):
                        continue
                    if re.search(r"\b(trif[aá]sico|grupo\s+[a-z0-9]+|classe|verde|vermelha|\d{2}/\d{2}/\d{4})", l, re.I):
                        continue
                    # Se linha parece conter classe/subclasse (ex: "PODER PUBLICO - ESTADUAL")
                    if re.search(r"[A-Z\s]+-\s*[A-Z\s]+", l):
                        break
                    if re.search(r"\b(av|rua|rod|estrada|praça|alameda|sn|cep|cariacica|vit[oó]ria)\b", l, re.I):
                        break
                    unidade_candidates.insert(0, l)

                unidade = " ".join(unidade_candidates).strip()
                cep = re.search(r"\d{5}-\d{3}", cep_line).group(0)
                identificacao["unidade"] = formatar_proprio_title(unidade)
                identificacao["endereco"] = formatar_proprio_title(f"{logradouro_line}, {local_line}, CEP: {cep}")
                break

    else:
        identificacao["unidade"] = "N/A"
        identificacao["endereco"] = "N/A"

    # Tensão nominal e unidade
    # logging.info("Extraindo Tensão nominal...")
    tensao_match = re.search(r"\b(\d{1,3}[.,]?\d{0,3})\s*V\b", texto)
    if tensao_match:
        tensao_val = tensao_match.group(1).replace(",", ".")
        identificacao["tensao"] = tensao_val
        identificacao["tensaoUnid"] = "kV" if float(tensao_val) >= 1000 else "V"

        # Nível de tensão baseado no valor
        t = float(tensao_val)
        if t >= 1000:
            identificacao["nivel_tensao"] = "alta tensão"
        elif t >= 1:
            identificacao["nivel_tensao"] = "média tensão"
        else:
            identificacao["nivel_tensao"] = "baixa tensão"

    # Demais campos
    # logging.info("Extraindo demais campos de identificação...")
    identificacao.update({
        # Número da instalação (ex: 0009500016)
        "numero_instalacao": _find(r"\b(\d{10})PAG\b", texto),

        # Número do cliente (ex: 0152128200)
        "numero_cliente": _find(r"COD\. IDENT\. (\d{10})", texto),

        # Grupo tarifário (ex: A)
        "grupo_tarifario": _find(r"\bGrupo\s+([A-Z])\b", texto, re.IGNORECASE),

        # Subgrupo (ex: A4)
        "subgrupo": _find(r"\b(A[0-9])\b", texto),

        # Classe/Subclasse (ex: PODER PUBLICO - ESTADUAL)
        "classe": _find(r"(PODER\s+PUBLICO\s*-\s*[A-Z\s]+)", texto),
    })

    modalidade_match = re.search(r"\b(A\s+)?(AZUL|VERDE|BRANCA|CONVENCIONAL)(?=\b)", texto, re.IGNORECASE)
    if modalidade_match:
        modalidade = modalidade_match.group(2).lower()
        identificacao["modalidade"] = modalidade

    # Mês de referência
    mes_ano = re.search(
        r"(Janeiro|Fevereiro|Mar[çc]o|Abril|Maio|Junho|Julho|Agosto|"
        r"Setembro|Outubro|Novembro|Dezembro)/(\d{4})", texto
    )
    if mes_ano:
        nome, ano = mes_ano.groups()
        mes_map = {
            "Janeiro":"01","Fevereiro":"02","Março":"03","Marco":"03","Abril":"04",
            "Maio":"05","Junho":"06","Julho":"07","Agosto":"08","Setembro":"09",
            "Outubro":"10","Novembro":"11","Dezembro":"12"
        }
        identificacao["mes_referencia"] = f"{mes_map[nome]}/{ano}"

    # Atribuição final
    out["identificacao"] = {k: v for k, v in identificacao.items() if v}

    # ---------- LEITURAS ----------
    # logging.info("Extraindo informações das leituras...")
    out["leituras"] = {}
    if (m := re.search(r"Roteiro de leitura:.*?:\s*([0-3]\d/\d{2}/\d{4})\s*a\s*([0-3]\d/\d{2}/\d{4})", texto)):
        out["leituras"]["leitura_inicio"], out["leituras"]["leitura_fim"] = m.groups()

    out["leituras"] = {k: v for k, v in out["leituras"].items() if v}

    # ---------- CONSUMO ATIVO ----------
    # Ponta
    m = re.search(
        rf"(?:TUSD\s*-\s*.*?Fornecida\s+Ponta|Consumo\s+Ativo\s+Ponta)\s+kWh\s+({NUMBER})",
        texto, re.I
    )
    # logging.info(f"match energia Ponta: {m}")
    if m:
        out["consumo_ativo"]["ponta_kwh"] = _clean_num(m.group(1))

    # Fora-Ponta
    m = re.search(
        rf"(?:TUSD\s*-\s*.*?Fornecida\s+(?:Fora\s+Ponta|FPonta)|(?:TUSD\s*-\s*)?Cons\s+Ativo\s+(?:Fora\s+Ponta|FPonta))\s+kWh\s+({NUMBER})",
        texto, re.I
    )
    # logging.info(f"match energia Fora Ponta: {m}")
    if m:
        out["consumo_ativo"]["fora_ponta_kwh"] = _clean_num(m.group(1))

    # Energia Injetada (com possível "-" no fim)
    m = re.search(
        rf"(?:Inj\.\w+|Injetada)[^\n]*?\s({DECIMAL})\s+KWH",
        texto, re.I
    )
    # logging.info(f"match energia injetada: {m}")
    if m:
        energia_injetada = _clean_num(m.group(1))
        # logging.info(f"energia injetada: {energia_injetada}")
        out["consumo_ativo"]["energia_injetada_kwh"] = energia_injetada
    else:
        out["consumo_ativo"]["energia_injetada_kwh"] = 0.0

    # Total
    if "ponta_kwh" in out["consumo_ativo"] and "fora_ponta_kwh" in out["consumo_ativo"]:
        out["consumo_ativo"]["total_kwh"] = round(
            out["consumo_ativo"]["ponta_kwh"] +
            out["consumo_ativo"]["fora_ponta_kwh"], 4)


    # ---------- DEMANDA ----------
    contratada_fp_pat = rf"Demanda\s+Contratual\s+(?:FP-)?KW\s+({NUMBER})"
    contratada_p_pat = rf"Demanda\s+Contratual\s+P-KW\s+({NUMBER})"
    contratada_geral_pat = rf"Demanda\s+Contratual-?KW\s+({NUMBER})"

    # Extrações
    valor_p_kw = _find(contratada_p_pat, texto, re.I)
    valor_fp_kw = _find(contratada_fp_pat, texto, re.I)
    valor_geral_kw = _find(contratada_geral_pat, texto, re.I)

    # Registro no dicionário
    out.setdefault("demanda", {})

    if valor_p_kw:
        out["demanda"]["contratada_p_kw"] = _clean_num(valor_p_kw)

    if valor_fp_kw:
        out["demanda"]["contratada_fp_kw"] = _clean_num(valor_fp_kw)

    # Se não tiver FP-KW explícito mas tiver "Demanda Contratual KW", considerar como FP
    elif valor_geral_kw:
        out["demanda"]["contratada_fp_kw"] = _clean_num(valor_geral_kw)

    # contrat_pat = rf"Demanda\s+Contratual[- ]KW\s+({NUMBER})"
    # out.setdefault("demanda", {})["contratada_kw"] = _clean_num(_find(contrat_pat, texto, re.I))


    # ---------- DEMANDA MÁXIMA (leitura) ----------
    # aceita “Máx” ou “Máxima”
    out.setdefault("demanda", {})
    max_pat = rf"""
        Demanda\s+Máx(?:ima)?\s+           # “Máx” ou “Máxima”
        (Ponta|FPonta|Fora\s*Ponta)        # período
        .*?                                # ignora o que vier no meio
        ({NUMBER})\s*[kK][wW]              # valor em kW
    """
    for periodo, qtd in re.findall(max_pat, texto, re.I | re.X):
        chave = "ponta" if periodo.lower().startswith("ponta") else "fora_ponta"
        out["demanda"].setdefault("maxima", []).append({
            "periodo": chave,
            "valor_kw": _clean_num(qtd)
        })

    # ---------- ULTRAPASSAGEM ----------
    # caso exista a linha “Ultrapassagem kW 13,5420 …”
    m = re.search(
        rf"Ultrapassagem\s+kW\s+({NUMBER})",
        texto, re.I
    )
    if m:
        out["demanda"]["ultrapassagem_kw"] = _clean_num(m.group(1))

    dmcr_pat = rf"""
        (?m)                                # modo multiline, ^ e $ funcionam por linha
        ^(?!Perdas)                        # não captura linhas que comecem com “Perdas”
        DMCR\s+                            # linha começando com “DMCR”
        (Ponta|F(?:Ponta|ora\s*Ponta))     # captura “Ponta” ou “FPonta” / “F Ponta” / “Fora Ponta”
        .*?                                # ignora o resto
        ({NUMBER})\s*[kK][wW]              # o valor em kW
    """

    out.setdefault("demanda", {})
    for periodo, qtd in re.findall(dmcr_pat, texto, re.I | re.X):
        chave = "ponta" if periodo.lower().startswith("ponta") else "fora_ponta"
        out["demanda"].setdefault("dmcr", []).append({
            "periodo": chave,
            "valor_kw": _clean_num(qtd)
        })

    # ---------- DEMANDA (Ponta e Fora Ponta) extraída da tabela horizontal ----------
    demanda_tabela_pat = rf"""
        Demanda\s*             # Título da seção
        Ponta\s+Fora\s+Ponta   # Subtítulos
        ({NUMBER})\s+({NUMBER})
    """
    match = re.search(demanda_tabela_pat, texto, re.I | re.X)
    if match:
        demanda_ponta = _clean_num(match.group(1))
        demanda_fora = _clean_num(match.group(2))
        out.setdefault("demanda", {})["ponta_kw"] = demanda_ponta
        out.setdefault("demanda", {})["fora_ponta_kw"] = demanda_fora

    # ---------- DEMANDA REATIVA EXCEDENTE (DRE) ----------
    dre_pat = rf"""
        Dem\.?\s+Reat\.?\s+Excedente\s*    # Título da seção
        Ponta\s+Fora\s+Ponta\s*            # Subtítulos
        ({NUMBER})\s+({NUMBER})            # Valores numéricos
    """
    match = re.search(dre_pat, texto, re.I | re.X)
    if match:
        dre_ponta = _clean_num(match.group(1))
        dre_fora_ponta = _clean_num(match.group(2))
        out.setdefault("energia_reativa", {})["dre"] = {
            "ponta_kvarh": dre_ponta,
            "fora_ponta_kvarh": dre_fora_ponta
        }
        
    # ---------- DEMANDA (custos)  -----------------------------------
    # procura a primeira linha que contenha "Demanda" + 3 números
    for ln in texto.splitlines():
        if "Demanda" not in ln:
            continue
        # ignora Contratual, Não Utilizada, Ultrapassagem
        if re.search(r"\b(Contratual|Não|Nao|Ultrapassagem)\b", ln, re.I):
            continue
        nums = re.findall(NUMBER, ln)
        if len(nums) >= 3:
            qtd, tarifa_unit, valor = nums[:3]
            out.setdefault("demanda", {}).update({
                "fora_ponta_kw":   _clean_num(qtd),
                "tarifa_unitaria": _clean_num(tarifa_unit),
                "valor_total":     _clean_num(valor),
            })
            break   # achou, sai do laço

    # ---------- ENERGIA REATIVA ----------
    er = {
        "ponta_kvarh":      _clean_num(_find(r"Energia Reativa\s+Ponta.*?(" + NUMBER + ")\s+KVH", texto, re.I)),
        "fora_ponta_kvarh": _clean_num(_find(r"Energia Reativa\s+FPonta.*?(" + NUMBER + ")\s+KVH", texto, re.I)),
    }

    if all(er.values()):
        er["total_kvarh"] = round(er["ponta_kvarh"] + er["fora_ponta_kvarh"], 4)

    # excedentes
    exc = {
        "ponta_kwh":      _clean_num(_find(r"ERE\s+Ponta.*?(" + NUMBER + ")\s+KWH", texto, re.I)),
        "fora_ponta_kwh": _clean_num(_find(r"ERE\s+Fora\s+Ponta.*?(" + NUMBER + ")\s+KWH", texto, re.I)),
    }
    if any(v is not None for v in exc.values()):
        exc["total_kwh"] = round(sum(v or 0 for v in exc.values()), 4)
        er["excedente"] = {k: v for k, v in exc.items() if v is not None}

    out["energia_reativa"] = {k: v for k, v in er.items() if v not in (None, {}, [])}

    
    # ---------- IMPOSTOS ----------
    # logging.info("Extraindo informações sobre impostos...")
    
    impostos_dict = {}
    for valor, aliq, base, nome in _findall(rf"({NUMBER})\s+({NUMBER})\s+({NUMBER})\s+(PIS|COFINS)", texto, re.I):
        nome = nome.upper()
        if nome not in impostos_dict:
            impostos_dict[nome] = {
                "nome": nome,
                "aliquota": _clean_num(aliq),
                "base_calculo": _clean_num(base),
                "valor": _clean_num(valor)
            }

    # Captura valores de ICMS em tabelas
    icms_matches = _findall(
        rf"({NUMBER})\s+({NUMBER})\s+({NUMBER})\s+(\d{{1,2}},\d{{3}}|\d{{1,2}})(?:\s+)?(?:ICMS)?\s+({NUMBER})", texto, re.I
    )

    for base, _, _, aliq, valor in icms_matches:
        if "ICMS" not in impostos_dict:
            impostos_dict["ICMS"] = {
                "nome": "ICMS",
                "aliquota": _clean_num(aliq),
                "base_calculo": _clean_num(base),
                "valor": _clean_num(valor)
            }

    # Converte para lista se quiser manter a estrutura esperada
    out["impostos"] = list(impostos_dict.values())

    # ---------- TARIFAS ----------
    # logging.info("Extraindo informações sobre tarifas...")
    tarifas = []
    tarifa_pat = (r"(TUSD|TE)\s*-\s*Cons(?:\w+)?\s+Ativo\s+"
                  r"(Ponta|FPonta|Fora\s+Ponta)\s+kWh\s+"
                  rf"({NUMBER})\s+({NUMBER})\s+({NUMBER})")
    for desc, periodo, qtd, tarifa_unit, valor_tot in _findall(tarifa_pat, texto, re.I):
        tarifas.append({
            "descricao":      desc,
            "periodo":        periodo.replace("FPonta", "Fora Ponta").lower().replace(" ", "_"),
            "quantidade":     _clean_num(qtd),
            "tarifa_unitaria":_clean_num(tarifa_unit),
            "valor_total":    _clean_num(valor_tot),
        })
    if tarifas:
        out["tarifas"] = tarifas

    # ---------- VALORES TOTAIS ----------
    if (m := re.search(r"TOTAL\s+(" + NUMBER + ")\s+(" + NUMBER + ")", texto, re.I)):
        out["valores_totais"] = {
            "valor_total_fatura": _clean_num(m.group(1)),
            "subtotal_encargos":  _clean_num(m.group(2)),
        }

    # ---------- COMPONENTES EXTRAS (opcionais) ----------
    # logging.info("Extraindo informações sobre componentes extras...")
    extras = []

    # extra_pat = rf"""
    # (?P<descricao>
    #     Demanda\s+Não\s+Utilizada |
    #     Demanda\s+Ultrapassagem  |
    #     Tarifa\s+Postal |
    #     ERE(?:-|\s)Energia\s+Reativa\s+Excedente |
    #     Adicional\s+Bandeira\s+(?:Vermelha|Amarela|Verde)? |
    #     Contribuição\s+de\s+Ilum(?:\.|inação)?\s+Pública(?:\s+-\s+Lei\s+Municipal)?
    # )
    # \s+\w*\s+({NUMBER})\s+({NUMBER})\s+({NUMBER})(?:\s+({NUMBER}))?
    # """
    extra_pat = rf"""
        (?P<descricao>
            Demanda\s+Não\s+Utilizada |
            Demanda\s+Ultrapassagem  |
            Tarifa\s+Postal |
            ERE(?:-|\s)Energia\s+Reativa\s+Excedente |
            Adicional\s+Bandeira\s+(?:Vermelha|Amarela|Verde)\s*\d* |
            Contribuição\s+de\s+Ilum(?:\.|inação)?\s+Pública(?:\s+-\s+Lei\s+Municipal)?
        )
        \s+\w*\s+({NUMBER})\s+({NUMBER})\s+({NUMBER})\s+({NUMBER})?
    """

    for match in re.finditer(extra_pat, texto, re.I | re.X):
        nome, qtd, tarifa, valor, imposto = match.groups()
        # logging.info(f"Extração: {nome}")
        if nome.strip() == "Contribuição de Ilum. Pública - Lei Municipal":
            extras.append({
            "descricao": nome.strip(),
            "quantidade": _clean_num(qtd),
            "tarifa_unitaria": _clean_num(valor),
            "valor_total": _clean_num(tarifa),
            "valor_impostos": _clean_num(imposto) 
            })
        else:
            extras.append({
                "descricao": nome.strip(),
                "quantidade": _clean_num(qtd),
                "tarifa_unitaria": _clean_num(tarifa),
                "valor_total": _clean_num(valor),
                "valor_impostos": _clean_num(imposto) 
            })

    retencao_pat = rf"""
        (?P<descricao>
            Retenção\s+Demanda\s+Imposto\s+Renda |
            Retenção\s+Imposto\s+de\s+Renda
        )
        \s+\w*\s+({DECIMAL})\s+({DECIMAL})
    """
    for match in re.finditer(retencao_pat, texto, re.I | re.X):
        nome, valor, imposto = match.groups()
        extras.append({
            "descricao": nome.strip(),
            "valor_total": _clean_num(valor),
            "valor_impostos": _clean_num(imposto)
        })

    multa_pat = rf"""
        (?P<descricao>
            Juros\s+de\s+Mora\s+Ref[.:]?\s*\w* |
            Multa\s+Ref[.:]?\s*\w*
        )
        .*?                                  # ignora unidade e quantidade
        ({DECIMAL})\s+({DECIMAL})
    """
    for match in re.finditer(multa_pat, texto, re.I | re.X):
        nome, valor, multa = match.groups()
        extras.append({
            "descricao": nome.strip(),
            "valor_total": _clean_num(multa)
        })

    # if extras:
    #     out["componentes_extras"] = extras
    out["componentes_extras"] = extras

    logging.info(f"Extrações: {out}")
    return out
    # ---------- LIMPEZA ----------
    # return {k: v for k, v in out.items() if v not in (None, {}, [], "")}

# ╭────────────────────  UTIL / CLI  ───────────────────╮
def pdf_to_text(pdf: Path) -> str:
    reader = PdfReader(pdf)
    return "\n".join(p.extract_text() or "" for p in reader.pages)


def main() -> None:
    if len(sys.argv) < 2:
        logging.error("Uso: python edp_invoice_parser.py <fatura.pdf>", file=sys.stderr); sys.exit(1)
    pdf = Path(sys.argv[1])
    if not pdf.exists():
        logging.error(f"Arquivo não encontrado: {pdf}", file=sys.stderr); sys.exit(1)

    texto = pdf_to_text(pdf)
    dados = extrair_dados_completos_da_fatura_regex(texto)
    logging.info(json.dumps(dados, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
