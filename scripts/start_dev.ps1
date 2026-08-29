$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$DesktopRoot = Join-Path $ProjectRoot "apps\desktop"
$PidDir = Join-Path $ProjectRoot ".runtime"
$LogDir = Join-Path $PidDir "logs"
$VitePidFile = Join-Path $PidDir "vite.pid"
$ElectronPidFile = Join-Path $PidDir "electron.pid"
$ViteLog = Join-Path $LogDir "vite.log"
$ElectronLog = Join-Path $LogDir "electron.log"
$PreloadLog = Join-Path $LogDir "preload.log"
$RendererLog = Join-Path $LogDir "renderer.log"
$RuntimeApiLog = Join-Path $LogDir "runtime-api.log"
$ViteErrLog = Join-Path $LogDir "vite.err.log"
$ElectronErrLog = Join-Path $LogDir "electron.err.log"
$MainFile = Join-Path $DesktopRoot "dist\main\main.js"
$PreloadFile = Join-Path $DesktopRoot "dist\preload\preload.cjs"
$RendererIndex = Join-Path $DesktopRoot "dist\renderer\index.html"
$ViteEntry = Join-Path $ProjectRoot "node_modules\vite\bin\vite.js"
$ElectronExe = Join-Path $ProjectRoot "node_modules\electron\dist\electron.exe"
$RendererUrl = "http://127.0.0.1:5173"
$RuntimeState = Join-Path $env:APPDATA "CLM Assistant Desktop\runtime\runtime-state.json"

function Show-LogTail {
  param([string[]]$Paths)
  foreach ($Path in $Paths) {
    if (Test-Path $Path) {
      Write-Host "---- $Path ----"
      Get-Content $Path -Tail 120 -ErrorAction SilentlyContinue
    }
  }
}

if (-not (Test-Path $PidDir)) {
  New-Item -ItemType Directory -Path $PidDir | Out-Null
}

if (-not (Test-Path $LogDir)) {
  New-Item -ItemType Directory -Path $LogDir | Out-Null
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  throw "Node.js was not found."
}

if (-not (Test-Path $ViteEntry)) {
  throw "Local Vite entry was not found: $ViteEntry"
}

if (-not (Test-Path $ElectronExe)) {
  throw "Local Electron executable was not found: $ElectronExe"
}

Push-Location $ProjectRoot
try {
  $env:CLM_PROJECT_ROOT = $ProjectRoot
  npm.cmd run build
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

  $Missing = @($MainFile, $PreloadFile, $RendererIndex) | Where-Object { -not (Test-Path $_) }
  if ($Missing.Count -gt 0) {
    Write-Error ("Build output is missing required files:`n" + ($Missing -join "`n"))
    exit 1
  }

  Remove-Item -Force $ViteLog, $ViteErrLog, $ElectronLog, $ElectronErrLog, $PreloadLog, $RendererLog, $RuntimeApiLog, $RuntimeState -ErrorAction SilentlyContinue
  $Vite = Start-Process -FilePath "node" -ArgumentList @($ViteEntry, "--host", "127.0.0.1", "--port", "5173") -WorkingDirectory $DesktopRoot -RedirectStandardOutput $ViteLog -RedirectStandardError $ViteErrLog -PassThru
  Set-Content -Path $VitePidFile -Value $Vite.Id

  $Deadline = (Get-Date).AddSeconds(20)
  do {
    if ($Vite.HasExited) {
      Show-LogTail @($ViteLog, $ViteErrLog)
      throw "Vite exited before becoming ready."
    }
    try {
      Invoke-WebRequest -Uri $RendererUrl -UseBasicParsing -TimeoutSec 2 | Out-Null
      $ViteReady = $true
    }
    catch {
      Start-Sleep -Milliseconds 500
      $ViteReady = $false
    }
  } until ($ViteReady -or (Get-Date) -gt $Deadline)

  if (-not $ViteReady) {
    Show-LogTail @($ViteLog, $ViteErrLog)
    throw "Vite did not become ready at $RendererUrl."
  }

  $env:VITE_DEV_SERVER_URL = $RendererUrl
  $Electron = Start-Process -FilePath $ElectronExe -ArgumentList @($MainFile) -WorkingDirectory $ProjectRoot -RedirectStandardOutput $ElectronLog -RedirectStandardError $ElectronErrLog -PassThru
  Set-Content -Path $ElectronPidFile -Value $Electron.Id

  Start-Sleep -Seconds 5
  if ($Electron.HasExited) {
    Show-LogTail @($ElectronLog, $ElectronErrLog)
    exit 1
  }

  $RuntimeDeadline = (Get-Date).AddSeconds(20)
  while ((Get-Date) -lt $RuntimeDeadline -and -not (Test-Path $RuntimeState)) {
    if ($Electron.HasExited) {
      Show-LogTail @($ElectronLog, $ElectronErrLog)
      throw "Electron exited before Agent Runtime became ready."
    }
    Start-Sleep -Milliseconds 500
  }

  if (-not (Test-Path $RuntimeState)) {
    Show-LogTail @($ElectronLog, $ElectronErrLog)
    throw "Agent Runtime did not become ready. Missing state file: $RuntimeState"
  }

  Write-Host "Vite PID: $($Vite.Id)"
  Write-Host "Electron PID: $($Electron.Id)"
  Write-Host "Renderer URL: $RendererUrl"
  Write-Host "Runtime State: $RuntimeState"
}
finally {
  Remove-Item Env:\VITE_DEV_SERVER_URL -ErrorAction SilentlyContinue
  Remove-Item Env:\CLM_PROJECT_ROOT -ErrorAction SilentlyContinue
  Pop-Location
}
