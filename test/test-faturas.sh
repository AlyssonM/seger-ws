#!/usr/bin/env bash
# test-faturas.sh  –  Validate EDP invoice extraction (Regex × LLM)
#
# Usage examples
#   ./test-faturas.sh -d ./faturas_edp
#   ./test-faturas.sh -d ./faturas_edp -r              # recurse
#   ./test-faturas.sh -f ./faturas_edp/fatura.pdf      # single file
#   ./test-faturas.sh -u http://127.0.0.1:5000/api/seger/dados-fatura/teste …

set -euo pipefail

# ───── CONFIG DEFAULTS ─────────────────────────────────────────────
SERVER_URL="http://localhost:5000/api/seger/dados-fatura/teste"
PDF_ROOT="."
RECURSIVE=false
SINGLE_FILE=""

# ───── HELPER: ANSI colors ────────────────────────────────────────
GREEN="$(printf '\033[32m')"
RED="$(printf '\033[31m')"
RESET="$(printf '\033[0m')"

# ───── Parse CLI options ──────────────────────────────────────────
usage() {
  cat <<EOF
Validate Regex vs LLM extraction for EDP invoices.

Options:
  -u URL     Endpoint URL  (default: $SERVER_URL)
  -d DIR     Directory containing PDFs
  -r         Recurse into sub-directories
  -f FILE    Single PDF file
  -h         Show this help
EOF
  exit 1
}

while getopts "u:d:f:rh" opt; do
  case "$opt" in
    u) SERVER_URL="$OPTARG" ;;
    d) PDF_ROOT="$OPTARG" ;;
    f) SINGLE_FILE="$OPTARG" ;;
    r) RECURSIVE=true ;;
    h|*) usage ;;
  esac
done

# ───── Collect PDF list ───────────────────────────────────────────
declare -a pdfs
if [[ -n $SINGLE_FILE ]]; then
  [[ -f $SINGLE_FILE ]] || { echo "File not found: $SINGLE_FILE" >&2; exit 1; }
  pdfs+=("$SINGLE_FILE")
else
  shopt -s nullglob
  if $RECURSIVE; then
    while IFS= read -r -d '' f; do pdfs+=("$f"); done < \
      <(find "$PDF_ROOT" -type f -iname '*.pdf' -print0)
  else
    pdfs=("$PDF_ROOT"/*.pdf)
  fi
  shopt -u nullglob
fi

[[ ${#pdfs[@]} -eq 0 ]] && { echo "No PDF files found."; exit 0; }

# ───── Loop over files ────────────────────────────────────────────
printf '%-45s %6s %6s %6s %s\n' "PDF" "MissR" "MissL" "Diff" "STATUS"
for pdf in "${pdfs[@]}"; do
  payload=$(jq -n --arg p "$pdf" '{pdf_path:$p}')
  resp=$(curl -sS -X POST -H "Content-Type: application/json" \
               -d "$payload" "$SERVER_URL")

  # Handle errors returned by server
  if [[ $(jq -r 'has("error")' <<<"$resp") == "true" ]]; then
    echo -e "${RED}ERROR${RESET} for $(basename "$pdf"): $(jq -r '.error' <<<"$resp")" >&2
    continue
  fi

  status=$(jq -r '.status' <<<"$resp")
  missR=$(jq '.diff.missing_in_regex   | length' <<<"$resp")
  missL=$(jq '.diff.missing_in_llm     | length' <<<"$resp")
  diffV=$(jq '.diff.different_values   | length' <<<"$resp")

  color=$([[ $status == "OK" ]] && echo "$GREEN" || echo "$RED")
  printf '%-45s %6d %6d %6d %s%s%s\n' \
         "$(basename "$pdf")" "$missR" "$missL" "$diffV" "$color" "$status" "$RESET"

  # Save diff if divergences exist
  if [[ $status != "OK" ]]; then
    diff_file="${pdf}.diff.json"
    jq '.diff' <<<"$resp" > "$diff_file"
  fi
done

# ── Summary ──────────────────────────────────────────────────────
total=${#pdfs[@]}
ok=$(grep -c " OK$" < <(printf '%s\n' "${pdfs[@]}" | sed 's/.*/OK/'))
div=$(( total - ok ))
echo
echo "Total: $total  |  OK: $ok  |  Divergences: $div"
[[ $div -gt 0 ]] && echo "See *.diff.json files for details."
