$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$RuntimeRoot = Join-Path $ProjectRoot "services\agent_runtime"
$VenvPython = Join-Path $ProjectRoot ".venv-win\Scripts\python.exe"
$FormalAppDataRoot = Join-Path $env:APPDATA "CLM Assistant Desktop"
$FormalDb = Join-Path $FormalAppDataRoot "runtime\clm_assistant.sqlite3"
$FormalDesktopWorkspace = "C:\Users\zong\Desktop\測試資料夾"
$RunId = [guid]::NewGuid().ToString("N")
$RuntimeDir = Join-Path $env:TEMP "clm-phase4-runtime-$RunId"
$StateFile = Join-Path $RuntimeDir "runtime-state.json"
$PidFile = Join-Path $RuntimeDir "runtime.pid"
$WorkspaceRoot = Join-Path $env:TEMP "clm-phase4-workspace-$RunId"
$Token = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
$Process = $null

function U {
  param([string]$Escaped)
  return [regex]::Unescape($Escaped)
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

function Get-OptionalHash {
  param([string]$Path)
  if (Test-Path -LiteralPath $Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
  }
  return $null
}

function Invoke-RuntimeJson {
  param([string]$Method, [string]$Path, [object]$Body = $null)
  $State = Get-Content $StateFile -Raw | ConvertFrom-Json
  $Uri = "http://127.0.0.1:$($State.port)$Path"
  $Request = [System.Net.HttpWebRequest]::Create($Uri)
  $Request.Method = $Method.ToUpperInvariant()
  $Request.Timeout = 15000
  $Request.Headers.Add("X-Desktop-Token", $Token)
  $Request.Headers.Add("X-Request-ID", [guid]::NewGuid().ToString("N"))
  if ($Body -ne $null) {
    $JsonBody = $Body | ConvertTo-Json -Depth 16
    $Utf8Body = [System.Text.Encoding]::UTF8.GetBytes($JsonBody)
    $Request.ContentType = "application/json; charset=utf-8"
    $Request.ContentLength = $Utf8Body.Length
    $Stream = $Request.GetRequestStream()
    try {
      $Stream.Write($Utf8Body, 0, $Utf8Body.Length)
    }
    finally {
      $Stream.Dispose()
    }
  }
  try {
    $Response = $Request.GetResponse()
  }
  catch [System.Net.WebException] {
    $Response = $_.Exception.Response
    if ($Response -eq $null) { throw }
  }
  try {
    $Reader = [System.IO.StreamReader]::new($Response.GetResponseStream(), [System.Text.Encoding]::UTF8)
    $Text = $Reader.ReadToEnd()
    if ([int]$Response.StatusCode -ge 400) {
      throw "Runtime API returned HTTP $([int]$Response.StatusCode): $Text"
    }
    return $Text | ConvertFrom-Json
  }
  finally {
    if ($Reader) { $Reader.Dispose() }
    if ($Response) { $Response.Dispose() }
  }
}

function Start-IsolatedRuntime {
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
  $script:Process = [System.Diagnostics.Process]::Start($Psi)
  Set-Content -Path $PidFile -Value $script:Process.Id
  $Deadline = (Get-Date).AddSeconds(25)
  while ((Get-Date) -lt $Deadline -and -not (Test-Path -LiteralPath $StateFile)) {
    if ($script:Process.HasExited) {
      throw "Runtime exited before writing state. stderr: $($script:Process.StandardError.ReadToEnd())"
    }
    Start-Sleep -Milliseconds 250
  }
  Assert-True (Test-Path -LiteralPath $StateFile) "Runtime state file was not created."
  $StatePath = [System.IO.Path]::GetFullPath($StateFile)
  Assert-True (-not $StatePath.StartsWith([System.IO.Path]::GetFullPath($FormalAppDataRoot), [System.StringComparison]::OrdinalIgnoreCase)) "Runtime state resolved into formal AppData."
  $Health = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:$((Get-Content $StateFile -Raw | ConvertFrom-Json).port)/health" -TimeoutSec 10
  Assert-True ($Health.status -eq "ok") "Runtime health was not ok."
}

function Stop-IsolatedRuntime {
  if ($script:Process -and -not $script:Process.HasExited) {
    $script:Process.Kill()
    $script:Process.WaitForExit(5000) | Out-Null
  }
}

function Invoke-Assistant {
  param([string]$Message, [string]$WorkspaceId, [string]$IdempotencyKey = $null)
  $Body = @{ message = $Message; workspace_id = $WorkspaceId }
  if ($IdempotencyKey) { $Body.idempotency_key = $IdempotencyKey }
  return Invoke-RuntimeJson "Post" "/api/assistant/tasks" $Body
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
  throw ".venv-win is missing. Run scripts\bootstrap_windows.ps1 first."
}

Assert-IsolatedPath $RuntimeDir "RuntimeDir"
Assert-IsolatedPath $StateFile "StateFile"
Assert-IsolatedPath $WorkspaceRoot "Workspace"

$FormalHashBefore = Get-OptionalHash $FormalDb

New-Item -ItemType Directory -Force $RuntimeDir, $WorkspaceRoot | Out-Null
Set-Content -Path (Join-Path $WorkspaceRoot "example.txt") -Value "hello phase 4" -Encoding UTF8
Set-Content -Path (Join-Path $WorkspaceRoot "duplicate-a.txt") -Value "same-content" -Encoding UTF8
Set-Content -Path (Join-Path $WorkspaceRoot "duplicate-b.txt") -Value "same-content" -Encoding UTF8
Set-Content -Path (Join-Path $WorkspaceRoot "overwrite.txt") -Value "before" -Encoding UTF8

try {
  Start-IsolatedRuntime

  $DbPath = Join-Path $RuntimeDir "clm_assistant.sqlite3"
  Assert-True (-not ([System.IO.Path]::GetFullPath($DbPath).StartsWith([System.IO.Path]::GetFullPath($FormalAppDataRoot), [System.StringComparison]::OrdinalIgnoreCase))) "Smoke database resolved into formal AppData."

  $Workspace = Invoke-RuntimeJson "Post" "/api/workspaces" @{ root_path = $WorkspaceRoot; display_name = "Phase 4 Smoke" }
  Assert-True ($Workspace.id.Length -gt 0) "Workspace was not created."
  Assert-True ($Workspace.display_path -eq (Resolve-Path -LiteralPath $WorkspaceRoot).Path) "Workspace path returned by Runtime did not match requested root."

  $ReadOnly = Invoke-Assistant (U "\u5217\u51fa\u76ee\u524d\u5de5\u4f5c\u5340\u7684\u6a94\u6848\uff0c\u7136\u5f8c\u627e\u51fa\u91cd\u8907\u6a94\u6848") $Workspace.id
  Assert-True ($ReadOnly.state -eq "COMPLETED") "Multi-step read-only task did not complete."
  Assert-True ($ReadOnly.progress.Count -eq 2) "Multi-step read-only task did not report two steps."

  $BackupFolder = U "\u6587\u5b57\u5099\u4efd"
  $CopyMessage = (U "\u5efa\u7acb\u8cc7\u6599\u593e ") + $BackupFolder + (U " \u4e26\u8907\u88fd example.txt \u5230 ") + $BackupFolder + "/example.txt"
  $CopyTask = Invoke-Assistant $CopyMessage $Workspace.id
  Assert-True ($CopyTask.state -eq "COMPLETED") "Multi-step create/copy task did not complete."
  Assert-True (Test-Path -LiteralPath (Join-Path $WorkspaceRoot "文字備份")) "Backup folder was missing."
  Assert-True (Test-Path -LiteralPath (Join-Path $WorkspaceRoot "文字備份\example.txt")) "Copied file was missing."
  Assert-True ($CopyTask.technicalDetails.postcondition.verified -eq $true) "Copy postcondition was not verified."

  $UndoCopy = Invoke-RuntimeJson "Post" "/api/undo/$($CopyTask.undo_record_id)"
  Assert-True ($UndoCopy.state -eq "COMPLETED") "Undo for copied file did not complete."
  Assert-True (-not (Test-Path -LiteralPath (Join-Path $WorkspaceRoot "文字備份\example.txt"))) "Undo did not remove copied file."

  $Clarify = Invoke-Assistant (U "\u5e6b\u6211\u6574\u7406\u6a94\u6848") $Workspace.id
  Assert-True ($Clarify.state -eq "WAITING_CLARIFICATION") "Ambiguous task did not wait for clarification."
  $Clarified = Invoke-RuntimeJson "Post" "/api/assistant/tasks/$($Clarify.id)/clarification" @{ answer = (U "\u4f9d\u7167\u6a94\u6848\u985e\u578b\u6574\u7406") }
  Assert-True ($Clarified.events.Count -ge 1) "Clarification answer did not create a task event."

  $Cancel = Invoke-RuntimeJson "Post" "/api/assistant/tasks/$($Clarify.id)/cancel"
  Assert-True ($Cancel.state -eq "CANCELLED") "Cancellation did not cancel waiting task."

  $Overwrite = Invoke-Assistant (U "\u8986\u5beb overwrite.txt \u70ba after") $Workspace.id
  Assert-True ($Overwrite.state -eq "WAITING_APPROVAL") "Overwrite did not wait for approval."
  Stop-IsolatedRuntime
  Start-IsolatedRuntime
  $Recovered = Invoke-RuntimeJson "Get" "/api/task-center/tasks/$($Overwrite.id)"
  Assert-True ($Recovered.state -eq "WAITING_APPROVAL") "Waiting approval task did not survive runtime restart."
  $Approved = Invoke-RuntimeJson "Post" "/api/approvals/$($Overwrite.approval_id)/decision" @{ approve = $true }
  Assert-True ($Approved.state -eq "COMPLETED") "Approved overwrite did not complete after restart."
  Assert-True ((Get-Content -LiteralPath (Join-Path $WorkspaceRoot "overwrite.txt") -Raw).Trim() -eq "after") "Approved overwrite did not change file."

  $IdemKey = "phase4-" + [guid]::NewGuid().ToString("N")
  $First = Invoke-Assistant (U "\u5217\u51fa\u76ee\u524d\u5de5\u4f5c\u5340\u7684\u6a94\u6848") $Workspace.id $IdemKey
  $Second = Invoke-Assistant (U "\u5217\u51fa\u76ee\u524d\u5de5\u4f5c\u5340\u7684\u6a94\u6848") $Workspace.id $IdemKey
  Assert-True ($First.id -eq $Second.id) "Idempotency key created duplicate tasks."

  $OtherTaskId = [guid]::NewGuid().ToString()
  & $VenvPython -c "import sqlite3, sys, datetime, uuid; db=sys.argv[1]; ws=sys.argv[2]; task=sys.argv[3]; con=sqlite3.connect(db); con.execute('insert into tasks (id,title,state,workspace_id,created_at,updated_at) values (?,?,?,?,?,?)', (task,'lease-holder','RUNNING',ws,'2026-08-30 00:00:00','2026-08-30 00:00:00')); con.execute('insert into execution_leases (id,workspace_id,path_key,holder_task_id,status,expires_at,created_at) values (?,?,?,?,?,?,?)', (str(uuid.uuid4()),ws,'locked',task,'HELD',(datetime.datetime.now(datetime.UTC)+datetime.timedelta(minutes=5)).isoformat(),'2026-08-30 00:00:00')); con.commit()" $DbPath $Workspace.id $OtherTaskId
  $Locked = Invoke-Assistant (U "\u5efa\u7acb\u8cc7\u6599\u593e locked") $Workspace.id
  Assert-True ($Locked.state -eq "FAILED") "Path lock did not fail the conflicting task."
  Assert-True (-not (Test-Path -LiteralPath (Join-Path $WorkspaceRoot "locked"))) "Path lock conflict still created a folder."

  $Center = Invoke-RuntimeJson "Get" "/api/task-center/tasks"
  Assert-True ($Center.Count -ge 5) "Task Center list did not return persisted tasks."
  $Detail = Invoke-RuntimeJson "Get" "/api/task-center/tasks/$($CopyTask.id)"
  Assert-True ($Detail.steps.Count -eq 2) "Task Center detail did not include step timeline."
  Assert-True ($Detail.technicalDetails -ne $null) "Task Center detail did not include collapsed technical details."

  $FormalHashAfter = Get-OptionalHash $FormalDb
  Assert-True ($FormalHashBefore -eq $FormalHashAfter) "Formal AppData database changed during isolated smoke."

  Write-Host "Phase 4 smoke passed."
  Write-Host "Isolated runtime data: $RuntimeDir"
  Write-Host "Isolated workspace: $WorkspaceRoot"
  Write-Host "Workspace id: $($Workspace.id)"
  Write-Host "Multi-step read-only: COMPLETED"
  Write-Host "Multi-step create/copy: COMPLETED"
  Write-Host "Undo copied file: COMPLETED"
  Write-Host "Clarification: WAITING_CLARIFICATION and answered event persisted"
  Write-Host "Approval/restart/resume: WAITING_APPROVAL survived restart, approved write completed"
  Write-Host "Cancellation: CANCELLED"
  Write-Host "Idempotency: same task id returned"
  Write-Host "Path lock: conflicting write failed without side effect"
  Write-Host "Task Center API: list/detail OK"
  Write-Host "Formal AppData DB hash before: $FormalHashBefore"
  Write-Host "Formal AppData DB hash after:  $FormalHashAfter"
}
finally {
  Stop-IsolatedRuntime
  Remove-Item -Recurse -Force $WorkspaceRoot -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force $RuntimeDir -ErrorAction SilentlyContinue
}
