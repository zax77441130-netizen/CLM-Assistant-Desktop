$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$PidDir = Join-Path $ProjectRoot ".runtime"
$PidFiles = @(
  (Join-Path $PidDir "electron.pid"),
  (Join-Path $PidDir "vite.pid"),
  (Join-Path $env:APPDATA "CLM Assistant Desktop\runtime\runtime.pid"),
  (Join-Path $env:APPDATA "Electron\runtime\runtime.pid")
)

foreach ($PidFile in $PidFiles) {
  if (-not (Test-Path $PidFile)) {
    continue
  }

  $TrackedPid = [int](Get-Content -Path $PidFile -Raw)
  $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $TrackedPid" -ErrorAction SilentlyContinue
  if (-not $ProcessInfo) {
    Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
    continue
  }

  $CommandLine = [string]$ProcessInfo.CommandLine
  $IsProjectProcess = $CommandLine.Contains($ProjectRoot) -or $CommandLine.Contains("CLM Assistant Desktop")
  if (-not $IsProjectProcess) {
    throw "Refusing to stop PID $TrackedPid because it does not match this project."
  }

  Stop-Process -Id $TrackedPid -ErrorAction SilentlyContinue
  Remove-Item -Force $PidFile -ErrorAction SilentlyContinue
}

Write-Host "Stopped tracked CLM Assistant Desktop development processes."
