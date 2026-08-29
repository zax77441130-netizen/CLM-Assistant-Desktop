$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$RuntimeRoot = Join-Path $ProjectRoot "services\agent_runtime"
$VenvPython = Join-Path $ProjectRoot ".venv-win\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
  throw ".venv-win is missing. Run scripts\bootstrap_windows.ps1 first."
}

Push-Location $RuntimeRoot
try {
  & $VenvPython -m PyInstaller --name agent-runtime --onefile --clean --noconfirm app\main.py
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
  Pop-Location
}
