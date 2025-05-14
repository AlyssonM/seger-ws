<#
.SYNOPSIS
  Valida extração de faturas EDP comparando Regex × LLM.

.PARAMETER ServerUrl
  URL completa do endpoint /dados-fatura/teste.

.PARAMETER PdfRoot
  Pasta (ou arquivo único) contendo as faturas PDF.

.PARAMETER Recursive
  Procura PDFs de forma recursiva (subpastas).

.EXAMPLE
  ./teste-faturas.ps1 -PdfRoot "D:\faturas_edp" -Recursive
#>

param (
  [string]$ServerUrl = "http://localhost:5000/api/seger/dados-fatura/teste",
  [string]$PdfRoot   = ".",
  [switch]$Recursive
)

function Get-PropCount($obj) {
  if ($null -eq $obj) { 0 }
  else                { ($obj | Get-Member -MemberType NoteProperty).Count }
}

$ErrorActionPreference = "Stop"
$files = @()

# — Arquivo único ou diretório —
if (Test-Path $PdfRoot -PathType Leaf) {
  $files = Get-Item $PdfRoot
} elseif (Test-Path $PdfRoot -PathType Container) {
  $files = Get-ChildItem -Path $PdfRoot -Filter *.pdf -File -Recurse:$Recursive
} else {
  Write-Error "PdfRoot não encontrado: $PdfRoot"
  exit 1
}

$results = @()

foreach ($file in $files) {
  $bodyJson = @{ pdf_path = $file.FullName } | ConvertTo-Json
  try {
    $resp = Invoke-RestMethod -Uri $ServerUrl -Method Post `
            -ContentType "application/json" -Body $bodyJson

    $status = $resp.status
    $row = [PSCustomObject]@{
      PDF                = $file.Name
      Status             = $status
      MissingInRegex     = Get-PropCount $resp.diff.missing_in_regex
      MissingInLLM       = Get-PropCount $resp.diff.missing_in_llm
      ValueDifferences   = Get-PropCount $resp.diff.different_values
    }
    $results += $row

    if ($status -ne "OK") {
      $diffPath = "$($file.FullName).diff.json"
      $resp.diff | ConvertTo-Json -Depth 20 | Out-File -Encoding UTF8 $diffPath
    }
  }
  catch {
    Write-Warning "Falha ao processar $($file.FullName): $_"
  }
}

# — Saída colorida —
foreach ($row in $results) {
  $color = if ($row.Status -eq "OK") { "Green" } else { "Red" }
  Write-Host ("{0,-40} {1}" -f $row.PDF, $row.Status) -ForegroundColor $color
}

# Tabela detalhada opcional
Write-Host "`nDetalhes:"
$results | Format-Table -AutoSize

# Resumo final
Write-Host "`nResumo:"
$results | Group-Object Status | Select-Object Name,Count | Format-Table -AutoSize
