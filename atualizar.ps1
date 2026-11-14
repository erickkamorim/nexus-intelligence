# NEXUS Forecast · Atualiza o código desta pasta com a versão mais recente da
# branch "main" do GitHub, sem precisar de Git instalado.
#
# Uso (na pasta do projeto):
#   powershell -ExecutionPolicy Bypass -File .\atualizar.ps1
#
# Preserva o que é local: .venv, data\ e logs\ não vêm do GitHub e não são tocados.
# Os arquivos temporários são apagados no final.

$ErrorActionPreference = "Stop"
$destino = $PSScriptRoot
$zip = Join-Path $env:TEMP "nexus-forecast.zip"
$extraido = Join-Path $env:TEMP "nexus-forecast-extraido"

try {
    Write-Host "Baixando a versao mais recente (branch main)..."
    Invoke-WebRequest "https://github.com/erickkamorim/nexus-intelligence/archive/refs/heads/main.zip" -OutFile $zip -UseBasicParsing
    if (Test-Path $extraido) { Remove-Item $extraido -Recurse -Force }
    Expand-Archive $zip $extraido -Force
    $origem = Get-ChildItem $extraido -Directory | Select-Object -First 1
    Copy-Item (Join-Path $origem.FullName "*") $destino -Recurse -Force
    Write-Host "Atualizado: $destino"
}
finally {
    Remove-Item $zip, $extraido -Recurse -Force -ErrorAction SilentlyContinue
}
