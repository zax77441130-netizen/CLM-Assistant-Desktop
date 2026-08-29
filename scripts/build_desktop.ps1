$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
  throw "npm.cmd was not found."
}

Push-Location $ProjectRoot
try {
  npm.cmd run build
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  npm.cmd run build:desktop --workspace "@clm/desktop"
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
  Pop-Location
}
