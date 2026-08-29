$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$RuntimeRoot = Join-Path $ProjectRoot "services\agent_runtime"
$VenvPython = Join-Path $ProjectRoot ".venv-win\Scripts\python.exe"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
  throw "Python launcher 'py' was not found."
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  throw "Node.js was not found."
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
  throw "npm.cmd was not found."
}

if (-not (Test-Path $VenvPython)) {
  py -3.12 -m venv (Join-Path $ProjectRoot ".venv-win")
}

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPython -m pip install -e "$RuntimeRoot[dev]"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location $ProjectRoot
try {
  npm.cmd install
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
  Pop-Location
}
