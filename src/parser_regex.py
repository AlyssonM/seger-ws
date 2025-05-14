"""
edp_invoice_parser.py  –  (rev. 2025-05-13)
-------------------------------------------

$ python edp_invoice_parser.py fatura_EDP_fev_2025.pdf
"""

from __future__ import annotations

import json, re, sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PyPDF2 import PdfReader


# ╭─────────────────────────  HELPERS  ─────────────────────────╮
# ▼ número:  1.234.567,89 | 1234567,89 | 1234567
# NUMBER = r"\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?"
# ▼ número: 1.234.567,89 | 1234567,89 | 1234567 | 0.59
NUMBER = (
    r"\d{1,3}(?:\.\d{3})*(?:[.,]\d+)?|"  # 1.234.567,89  | 1.234.567
    r"\d+[.,]\d+|\d+"                    # 1234567,89     | 1234567
)

DECIMAL = NUMBER                                            # alias p/ clareza


def _clean_num(n: str | None) -> float | None:
    if not n:
        return None
    n = n.replace(".", "").replace(",", ".")
    try:
        return float(n)
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


# ╭────────────────────  NÚCLEO DE EXTRAÇÃO  ───────────────────╮
def extrair_dados_completos_da_fatura_regex(texto: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    # ---------- IDENTIFICAÇÃO ----------
    out["identificacao"] = {
        "numero_instalacao": _find(r"COD\. IDENT\.\s*(\d+)", texto),
        "numero_cliente":    _find(r"\b(0*\d{7,})\s*PAG", texto),   # ← fix
        "grupo_tarifario":   _find(r"\b(A[0-9])\b", texto),
        "classe":            _find(r"(PODER PUBLICO\s*-\s*[A-ZÁ-Ú ]+)", texto),
    }

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
        out["identificacao"]["mes_referencia"] = f"{mes_map[nome]}/{ano}"

    out["identificacao"] = {k: v for k, v in out["identificacao"].items() if v}

    # ---------- LEITURAS ----------
    out["leituras"] = {}
    if (m := re.search(r"Roteiro de leitura:.*?:\s*([0-3]\d/\d{2}/\d{4})\s*a\s*([0-3]\d/\d{2}/\d{4})", texto)):
        out["leituras"]["leitura_inicio"], out["leituras"]["leitura_fim"] = m.groups()

    # def _cap(label: str) -> Tuple[int, int]:
    #     if (m := re.search(rf"{label}.*?\s({NUMBER})\s+({NUMBER})", texto)):
    #         ant, atu = (int(x.replace(".", "")) for x in m.groups())
    #         return ant, atu
    #     return 0, 0

    # def _cap(label: str) -> tuple[int, int]:
    #     # captura só os dois 1º-s inteiros depois da label
    #     pat = rf"{label}.*?\s({NUMBER})\s+({NUMBER})"
    #     if m := re.search(pat, texto):
    #         ant, atu = m.groups()[:2]
    #         return int(ant.replace('.', '')), int(atu.replace('.', ''))
    #     return 0, 0


    # ant_p, atu_p = _cap("Energia Ativa Ponta")
    # ant_f, atu_f = _cap("Energia Ativa Fora Ponta")
    # if ant_p + ant_f:
    #     out["leituras"]["leitura_anterior_kwh"] = float(ant_p + ant_f)
    # if atu_p + atu_f:
    #     out["leituras"]["leitura_atual_kwh"] = float(atu_p + atu_f)

    out["leituras"] = {k: v for k, v in out["leituras"].items() if v}

    # ---------- CONSUMO ATIVO ----------
    out["consumo_ativo"] = {
        "ponta_kwh":      _clean_num(_find(r"Consumo\s+Ativo\s+Ponta\s+(" + NUMBER + ")", texto, re.I)),
        "fora_ponta_kwh": _clean_num(_find(r"Consumo\s+Ativo\s+Fora\s+Ponta\s+(" + NUMBER + ")", texto, re.I)),
    }
    if all(out["consumo_ativo"].values()):
        out["consumo_ativo"]["total_kwh"] = round(sum(out["consumo_ativo"].values()), 4)
    out["consumo_ativo"] = {k: v for k, v in out["consumo_ativo"].items() if v is not None}

    # ---------- DEMANDA ----------
    dm = {}
    for tag, regex in {
        "ponta":      r"Demanda Máx\s+Ponta.*?(" + NUMBER + ")\s+KW",
        "fora_ponta": r"Demanda Máx\s+FPonta.*?(" + NUMBER + ")\s+KW"
    }.items():
        if (val := _clean_num(_find(regex, texto, re.I))):
            dm.setdefault("maxima", []).append({"periodo": tag, "valor_kw": val})

    dm["contratada_kw"] = _clean_num(_find(r"Demanda Contratada.*?(" + NUMBER + ")\s+KW", texto, re.I))

    for tag, regex in {
        "ponta":      r"DMCR\s+Ponta.*?(" + NUMBER + ")\s+KW",
        "fora_ponta": r"DMCR\s+Fora\s+Ponta.*?(" + NUMBER + ")\s+KW",
    }.items():
        if (val := _clean_num(_find(regex, texto, re.I))):
            dm.setdefault("dmcr", []).append({"periodo": tag, "valor_kw": val})

    out["demanda"] = {k: v for k, v in dm.items() if v not in (None, [], {})}

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
    impostos = []
    for valor, aliq, base, nome in _findall(
            rf"({NUMBER})\s+({NUMBER})\s+({NUMBER})\s+(PIS|COFINS|ICMS)",
            texto, re.I
    ):
        impostos.append({
            "nome":          nome,
            "base_calculo":  _clean_num(base),
            "aliquota":      _clean_num(aliq),
            "valor":         _clean_num(valor),
        })
    if impostos:
        out["impostos"] = impostos


    # ---------- TARIFAS ----------
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
    extras = []
    extra_pat = rf"""(
        Demanda\s+Não\s+Utilizada |
        Demanda\s+Ultrapassagem  |
        Tarifa\s+Postal |
        ERE(?:-|\s)Energia\s+Reativa\s+Excedente
    )\s+\w*\s+({NUMBER})\s+({NUMBER})\s+({NUMBER})"""

    for nome, qtd, tarifa, valor in _findall(extra_pat, texto, re.I | re.X):
        extras.append({
            "descricao": nome.strip(),
            "quantidade": _clean_num(qtd),
            "tarifa_unitaria": _clean_num(tarifa),
            "valor_total": _clean_num(valor),
        })
    if extras:
        out["componentes_extras"] = extras

    # ---------- LIMPEZA ----------
    return {k: v for k, v in out.items() if v not in (None, {}, [], "")}


# ╭────────────────────  UTIL / CLI  ───────────────────╮
def pdf_to_text(pdf: Path) -> str:
    reader = PdfReader(pdf)
    return "\n".join(p.extract_text() or "" for p in reader.pages)


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python edp_invoice_parser.py <fatura.pdf>", file=sys.stderr); sys.exit(1)
    pdf = Path(sys.argv[1])
    if not pdf.exists():
        print(f"Arquivo não encontrado: {pdf}", file=sys.stderr); sys.exit(1)

    texto = pdf_to_text(pdf)
    dados = extrair_dados_completos_da_fatura_regex(texto)
    print(json.dumps(dados, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
