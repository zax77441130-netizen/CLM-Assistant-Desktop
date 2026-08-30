$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$RuntimeRoot = Join-Path $ProjectRoot "services\agent_runtime"
$VenvPython = Join-Path $ProjectRoot ".venv-win\Scripts\python.exe"
$FormalAppDataRoot = Join-Path $env:APPDATA "CLM Assistant Desktop"
$FormalDesktopWorkspace = "C:\Users\zong\Desktop\測試資料夾"
$RunId = [guid]::NewGuid().ToString("N")
$RuntimeDir = Join-Path $env:TEMP "clm-phase2-runtime-$RunId"
$LogDir = Join-Path $env:TEMP "clm-phase2-logs-$RunId"
$StateFile = Join-Path $RuntimeDir "runtime-state.json"
$PidFile = Join-Path $RuntimeDir "runtime.pid"
$Sandbox = Join-Path $env:TEMP "clm-phase2-workspace-$RunId"
$Token = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")

function Invoke-RuntimeJson {
  param([string]$Method, [string]$Path, [object]$Body = $null)
  $State = Get-Content $StateFile -Raw | ConvertFrom-Json
  $Uri = "http://127.0.0.1:$($State.port)$Path"
  $Headers = @{ "X-Desktop-Token" = $Token; "X-Request-ID" = [guid]::NewGuid().ToString("N") }
  if ($Body -eq $null) {
    return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $Headers -TimeoutSec 10
  }
  return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $Headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 10) -TimeoutSec 10
}

function Assert-True {
  param([bool]$Condition, [string]$Message)
  if (-not $Condition) { throw $Message }
}

function Assert-IsolatedPath {
  param([string]$Path, [string]$Name)
  $FullPath = [System.IO.Path]::GetFullPath($Path)
  $AppDataFull = [System.IO.Path]::GetFullPath($FormalAppDataRoot)
  Assert-True (-not $FullPath.StartsWith($AppDataFull, [System.StringComparison]::OrdinalIgnoreCase)) "$Name resolved into formal AppData."
  $DesktopWorkspaceFull = [System.IO.Path]::GetFullPath($FormalDesktopWorkspace)
  Assert-True (-not $FullPath.StartsWith($DesktopWorkspaceFull, [System.StringComparison]::OrdinalIgnoreCase)) "$Name resolved into formal desktop workspace."
}

if (-not (Test-Path $VenvPython)) {
  throw ".venv-win is missing. Run scripts\bootstrap_windows.ps1 first."
}

Assert-IsolatedPath $RuntimeDir "RuntimeDir"
Assert-IsolatedPath $LogDir "LogDir"
Assert-IsolatedPath $StateFile "StateFile"
Assert-IsolatedPath $Sandbox "Workspace"

New-Item -ItemType Directory -Force $RuntimeDir, $LogDir, $Sandbox | Out-Null
Remove-Item -Force $StateFile, $PidFile -ErrorAction SilentlyContinue

$Psi = [System.Diagnostics.ProcessStartInfo]::new()
$Psi.FileName = $VenvPython
$Psi.Arguments = "-m app.main"
$Psi.WorkingDirectory = $RuntimeRoot
$Psi.UseShellExecute = $false
$Psi.RedirectStandardOutput = $true
$Psi.RedirectStandardError = $true
$Psi.EnvironmentVariables["CLM_DESKTOP_TOKEN"] = $Token
$Psi.EnvironmentVariables["CLM_DATA_DIR"] = $RuntimeDir
$Psi.EnvironmentVariables["CLM_RESOURCE_DIR"] = $ProjectRoot
$Psi.EnvironmentVariables["CLM_RUNTIME_STATE_FILE"] = $StateFile
$Process = [System.Diagnostics.Process]::Start($Psi)
Set-Content -Path $PidFile -Value $Process.Id

try {
  $Deadline = (Get-Date).AddSeconds(20)
  while ((Get-Date) -lt $Deadline -and -not (Test-Path $StateFile)) {
    if ($Process.HasExited) {
      throw "Runtime exited before writing state. stderr: $($Process.StandardError.ReadToEnd())"
    }
    Start-Sleep -Milliseconds 250
  }
  Assert-True (Test-Path $StateFile) "Runtime state file was not created."

  $Health = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:$((Get-Content $StateFile -Raw | ConvertFrom-Json).port)/health" -TimeoutSec 10
  Assert-True ($Health.status -eq "ok") "Runtime health was not ok."

  $Workspace = Invoke-RuntimeJson "Post" "/api/workspaces" @{ root_path = $Sandbox }
  Assert-True ($Workspace.id.Length -gt 0) "Workspace was not created."

  $CreateDir = Invoke-RuntimeJson "Post" "/api/tasks/structured" @{ task_type = "CREATE_DIRECTORY"; workspace_id = $Workspace.id; path = "created" }
  Assert-True ($CreateDir.state -eq "COMPLETED") "Create directory task did not complete."
  Assert-True (Test-Path (Join-Path $Sandbox "created")) "Directory side effect was not created."
  Assert-True ($CreateDir.undo_record_id.Length -gt 0) "Create directory task did not return undo record."

  $UndoDir = Invoke-RuntimeJson "Post" "/api/undo/$($CreateDir.undo_record_id)"
  Assert-True ($UndoDir.state -eq "COMPLETED") "Undo directory task did not complete."
  Assert-True (-not (Test-Path (Join-Path $Sandbox "created"))) "Undo did not restore directory state."

  $Target = Join-Path $Sandbox "overwrite.txt"
  Set-Content -Path $Target -Value "before" -Encoding UTF8
  $Pending = Invoke-RuntimeJson "Post" "/api/tasks/structured" @{ task_type = "OVERWRITE_TEXT"; workspace_id = $Workspace.id; path = "overwrite.txt"; content = "after" }
  Assert-True ($Pending.state -eq "WAITING_APPROVAL") "Overwrite did not require approval."
  Assert-True ((Get-Content $Target -Raw).Trim() -eq "before") "Overwrite changed file before approval."

  $Rejected = Invoke-RuntimeJson "Post" "/api/approvals/$($Pending.approval_id)/decision" @{ approve = $false }
  Assert-True ($Rejected.state -eq "BLOCKED") "Rejected approval did not block task."
  Assert-True ((Get-Content $Target -Raw).Trim() -eq "before") "Rejected approval changed file."

  $PendingApprove = Invoke-RuntimeJson "Post" "/api/tasks/structured" @{ task_type = "OVERWRITE_TEXT"; workspace_id = $Workspace.id; path = "overwrite.txt"; content = "after" }
  $Approved = Invoke-RuntimeJson "Post" "/api/approvals/$($PendingApprove.approval_id)/decision" @{ approve = $true }
  Assert-True ($Approved.state -eq "COMPLETED") "Approved overwrite did not complete."
  Assert-True ((Get-Content $Target -Raw).Trim() -eq "after") "Approved overwrite did not change file."

  $UndoOverwrite = Invoke-RuntimeJson "Post" "/api/undo/$($Approved.undo_record_id)"
  Assert-True ($UndoOverwrite.state -eq "COMPLETED") "Overwrite undo did not complete."
  Assert-True ((Get-Content $Target -Raw).Trim() -eq "before") "Overwrite undo did not restore file."

  $DbPath = Join-Path $RuntimeDir "clm_assistant.sqlite3"
  $Counts = & $VenvPython -c "import sqlite3, sys; db=sys.argv[1]; con=sqlite3.connect(db); print(con.execute('select count(*) from tasks').fetchone()[0]); print(con.execute('select count(*) from audit_events').fetchone()[0]); print(con.execute('select count(*) from undo_records').fetchone()[0])" $DbPath
  Assert-True ([int]$Counts[0] -ge 5) "Task persistence count was too low."
  Assert-True ([int]$Counts[1] -ge 5) "Audit events were not persisted."
  Assert-True ([int]$Counts[2] -ge 2) "Undo records were not persisted."

  Write-Host "Phase 2 smoke passed."
  Write-Host "Workspace grant: $($Workspace.id)"
  Write-Host "Directory side effect: created and undone"
  Write-Host "Overwrite approval: reject preserved file, approve changed file, undo restored file"
  Write-Host "Persisted counts: tasks=$($Counts[0]) audit_events=$($Counts[1]) undo_records=$($Counts[2])"
}
finally {
  if ($Process -and -not $Process.HasExited) {
    $Process.Kill()
    $Process.WaitForExit(5000) | Out-Null
  }
  Remove-Item -Recurse -Force $Sandbox -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force $RuntimeDir, $LogDir -ErrorAction SilentlyContinue
}
