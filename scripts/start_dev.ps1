$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$DesktopRoot = Join-Path $ProjectRoot "apps\desktop"
$PidDir = Join-Path $ProjectRoot ".runtime"
$VitePidFile = Join-Path $PidDir "vite.pid"
$ElectronPidFile = Join-Path $PidDir "electron.pid"

if (-not (Test-Path $PidDir)) {
  New-Item -ItemType Directory -Path $PidDir | Out-Null
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  throw "Node.js was not found."
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
  throw "npm.cmd was not found."
}

Push-Location $ProjectRoot
try {
  $env:CLM_PROJECT_ROOT = $ProjectRoot
  npm.cmd run build
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  $Vite = Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev", "--workspace", "@clm/desktop") -WorkingDirectory $ProjectRoot -PassThru
  Set-Content -Path $VitePidFile -Value $Vite.Id
  Start-Sleep -Seconds 3
  $Electron = Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "electron", "--workspace", "@clm/desktop") -WorkingDirectory $ProjectRoot -PassThru
  Set-Content -Path $ElectronPidFile -Value $Electron.Id
  Write-Host "Vite PID: $($Vite.Id)"
  Write-Host "Electron PID: $($Electron.Id)"
}
finally {
  Pop-Location
}
