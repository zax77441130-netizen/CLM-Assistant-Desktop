$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$PidDir = Join-Path $ProjectRoot ".runtime"
$PidFiles = @(
  (Join-Path $PidDir "vite.pid"),
  (Join-Path $PidDir "electron.pid"),
  (Join-Path $PidDir "smoke\runtime.pid"),
  (Join-Path $PidDir "sidecar-smoke\runtime.pid"),
  (Join-Path $env:APPDATA "CLM Assistant Desktop\runtime\runtime.pid"),
  (Join-Path $env:APPDATA "Electron\runtime\runtime.pid")
)

$Alive = @()
foreach ($PidFile in $PidFiles) {
  if (Test-Path $PidFile) {
    $ProcessId = [int](Get-Content -Path $PidFile -Raw)
    $Process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($Process) {
      $Alive += [PSCustomObject]@{ PID = $Process.Id; Name = $Process.ProcessName; Source = $PidFile }
    }
  }
}

if ($Alive.Count -gt 0) {
  $Alive | Format-Table -AutoSize
  throw "Tracked processes are still running. Stop them manually or through the application quit flow."
}

Write-Host "No tracked runtime processes remain."
