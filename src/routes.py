# seger/routes.py
from flask import Blueprint, request, jsonify, send_file
from src.scraper import baixar_faturas_por_instalacao
from src.parser  import extrair_dados_completos_da_fatura
from src.utils.dict_diff import dict_diff, has_diff

bp = Blueprint("seger", __name__, url_prefix="/api/seger")

@bp.route("/faturas", methods=["POST"])
def faturas():
    data = request.get_json(force=True)
    instalacoes = data.get("instalacoes")
    inicio      = data.get("data_inicio")
    fim         = data.get("data_fim")
    mode        = data.get("mode", True)
    # validação mínima
    if not isinstance(instalacoes, list) or not inicio or not fim:
        return jsonify({"error": "instalacoes (lista), data_inicio e data_fim são obrigatórios"}), 400

    # dispara o scraper e retorna os paths
    try:
        paths = baixar_faturas_por_instalacao(instalacoes, inicio, fim, mode)
        return jsonify({"pdfs": paths})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/faturas/<path:pdf_path>", methods=["GET"])
def download(pdf_path):
    # envia o PDF como anexo
    return send_file(pdf_path, mimetype="application/pdf", as_attachment=True)

@bp.route("/dados-fatura", methods=["POST"])
def dados_fatura():
    data     = request.get_json(force=True)
    pdf_path = data.get("pdf_path", "")
    via_regex  = data.get("via_regex", True)
    if not pdf_path:
        return jsonify({"error": "pdf_path é obrigatório"}), 400

    try:
        dados = extrair_dados_completos_da_fatura(pdf_path, via_regex=via_regex)
        return jsonify(dados)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route("/dados-fatura/teste", methods=["POST"])
def dados_fatura_teste():
    """
    Corpo esperado:
    {
      "pdf_path": "<caminho/arquivo.pdf>"
    }
    """
    data     = request.get_json(force=True)
    pdf_path = data.get("pdf_path", "")
    if not pdf_path:
        return jsonify({"error": "pdf_path é obrigatório"}), 400

    try:
        # 1) Extrai via regex e via LLM
        dados_regex = extrair_dados_completos_da_fatura(pdf_path, via_regex=True)
        dados_llm   = extrair_dados_completos_da_fatura(pdf_path, via_regex=False)
        
        # 2) Calcula diferenças
        diff = dict_diff(dados_regex, dados_llm)

        return jsonify({
            "status": "OK" if not has_diff(diff) else "DIVERGENCIAS",
            "diff":  diff,
            "regex": dados_regex,
            "llm":   dados_llm,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500