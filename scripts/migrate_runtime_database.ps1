param(
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$RuntimeRoot = Join-Path $ProjectRoot "services\agent_runtime"
$VenvPython = Join-Path $ProjectRoot ".venv-win\Scripts\python.exe"
$RuntimeDir = Join-Path $env:APPDATA "CLM Assistant Desktop\runtime"
$PidFiles = @(
  (Join-Path $ProjectRoot ".runtime\vite.pid"),
  (Join-Path $ProjectRoot ".runtime\electron.pid"),
  (Join-Path $RuntimeDir "runtime.pid")
)

function Assert-Stopped {
  foreach ($PidFile in $PidFiles) {
    if (-not (Test-Path $PidFile)) { continue }
    $PidValue = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $PidValue) { continue }
    $Process = Get-Process -Id ([int]$PidValue) -ErrorAction SilentlyContinue
    if ($Process) {
      throw "Tracked process is still running: $($Process.ProcessName) PID $($Process.Id). Stop Runtime before migration."
    }
  }
}

if (-not (Test-Path $VenvPython)) {
  throw ".venv-win is missing. Run scripts\bootstrap_windows.ps1 first."
}

Assert-Stopped
Push-Location $RuntimeRoot
try {
  if ($WhatIf) {
    & $VenvPython -m app.db.maintenance --data-dir $RuntimeDir
  }
  else {
    & $VenvPython -m app.db.maintenance --data-dir $RuntimeDir --migrate
  }
  exit $LASTEXITCODE
}
finally {
  Pop-Location
}
