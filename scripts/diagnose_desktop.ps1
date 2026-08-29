$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$DesktopRoot = Join-Path $ProjectRoot "apps\desktop"
$RuntimeState = Join-Path $env:APPDATA "CLM Assistant Desktop\runtime\runtime-state.json"
$LogDir = Join-Path $ProjectRoot ".runtime\logs"
$Files = @{
  Main = Join-Path $DesktopRoot "dist\main\main.js"
  Preload = Join-Path $DesktopRoot "dist\preload\preload.cjs"
  Renderer = Join-Path $DesktopRoot "dist\renderer\index.html"
}

function Show-Check {
  param([string]$Name, [bool]$Ok, [string]$Detail = "")
  $Status = if ($Ok) { "OK" } else { "FAIL" }
  Write-Host "$Name`: $Status $Detail"
  if (-not $Ok) { $script:Failed = $true }
}

function Show-LogTail {
  param([string]$Name)
  $Path = Join-Path $LogDir "$Name.log"
  if (Test-Path $Path) {
    Write-Host "---- $Name.log ----"
    Get-Content $Path -Tail 40 | ForEach-Object { $_ -replace "(token|secret|password|api[_-]?key|authorization|cookie)", "[redacted-key]" }
  }
}

$Failed = $false
foreach ($Item in $Files.GetEnumerator()) {
  Show-Check $Item.Key (Test-Path $Item.Value) $Item.Value
}

if (Test-Path $Files.Preload) {
  $PreloadContent = Get-Content $Files.Preload -Raw
  Show-Check "Preload is CommonJS bundle" ($PreloadContent -match 'require\("electron"\)' -and $PreloadContent -notmatch "^import ")
  Show-Check "Preload does not import main process module" ($PreloadContent -notmatch "../main/ipc")
  Show-Check "Preload exposes bridge" ($PreloadContent -match "exposeInMainWorld")
}

$ElectronPidFile = Join-Path $ProjectRoot ".runtime\electron.pid"
if (Test-Path $ElectronPidFile) {
  $ElectronPid = [int](Get-Content $ElectronPidFile -Raw)
  $ElectronProcess = Get-Process -Id $ElectronPid -ErrorAction SilentlyContinue
  Show-Check "Electron PID" ($null -ne $ElectronProcess) "pid=$ElectronPid"
}
else {
  Show-Check "Electron PID" $false "missing .runtime\electron.pid"
}

try {
  Invoke-WebRequest -Uri "http://127.0.0.1:5173" -UseBasicParsing -TimeoutSec 2 | Out-Null
  Show-Check "Vite health" $true "http://127.0.0.1:5173"
}
catch {
  Show-Check "Vite health" $false "not reachable"
}

if (Test-Path $RuntimeState) {
  $State = Get-Content $RuntimeState -Raw | ConvertFrom-Json
  Show-Check "Runtime state" ($State.host -eq "127.0.0.1" -and $State.tokenExposedToRenderer -eq $false) "pid=$($State.pid) port=$($State.port)"
  try {
    $Health = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:$($State.port)/health" -TimeoutSec 2
    Show-Check "Runtime health" ($Health.status -eq "ok")
  }
  catch {
    Show-Check "Runtime health" $false "not reachable"
  }
}
else {
  Show-Check "Runtime state" $false "missing runtime-state.json"
}

$PreloadLog = Join-Path $LogDir "preload.log"
if (Test-Path $PreloadLog) {
  $Ready = Select-String -Path $PreloadLog -Pattern "bridge-ready" -Quiet
  Show-Check "Bridge ready signal" $Ready
}
else {
  Show-Check "Bridge ready signal" $false "preload.log missing"
}

$RuntimeApiLog = Join-Path $LogDir "runtime-api.log"
if (Test-Path $RuntimeApiLog) {
  $RecentApiFailure = Get-Content $RuntimeApiLog -Tail 80 | Select-String -Pattern "http-5\d\d|fetch-error" -Quiet
  Show-Check "Runtime API recent errors" (-not $RecentApiFailure)
}

Show-LogTail "electron"
Show-LogTail "preload"
Show-LogTail "renderer"
Show-LogTail "runtime-api"

if ($Failed) {
  exit 1
}

Write-Host "Desktop diagnostics passed."
