$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$RuntimeRoot = Join-Path $ProjectRoot "services\agent_runtime"
$VenvPython = Join-Path $ProjectRoot ".venv-win\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
  throw ".venv-win is missing. Run scripts\bootstrap_windows.ps1 first."
}

Push-Location $RuntimeRoot
try {
  & $VenvPython -m pytest tests -q
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  & $VenvPython -m ruff check app tests
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  & $VenvPython -m mypy app
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
  Pop-Location
}

Push-Location $ProjectRoot
try {
  npm.cmd run typecheck
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  npm.cmd run test
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  npm.cmd run build
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
  Pop-Location
}
