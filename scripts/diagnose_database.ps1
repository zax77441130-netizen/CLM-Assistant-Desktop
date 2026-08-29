param(
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$RuntimeRoot = Join-Path $ProjectRoot "services\agent_runtime"
$VenvPython = Join-Path $ProjectRoot ".venv-win\Scripts\python.exe"
$RuntimeDir = Join-Path $env:APPDATA "CLM Assistant Desktop\runtime"

if (-not (Test-Path $VenvPython)) {
  throw ".venv-win is missing. Run scripts\bootstrap_windows.ps1 first."
}

Push-Location $RuntimeRoot
try {
  & $VenvPython -m app.db.maintenance --data-dir $RuntimeDir
  exit $LASTEXITCODE
}
finally {
  Pop-Location
}
