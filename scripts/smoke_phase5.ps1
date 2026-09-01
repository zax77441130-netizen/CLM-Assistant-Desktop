$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$RuntimeRoot = Join-Path $ProjectRoot "services\agent_runtime"
$VenvPython = Join-Path $ProjectRoot ".venv-win\Scripts\python.exe"
$FormalAppDataRoot = Join-Path $env:APPDATA "CLM Assistant Desktop"
$FormalDb = Join-Path $FormalAppDataRoot "runtime\clm_assistant.sqlite3"
$FormalDesktopWorkspace = "C:\Users\zong\Desktop\測試資料夾"
$RunId = [guid]::NewGuid().ToString("N")
$RuntimeDir = Join-Path $env:TEMP "clm-phase5-runtime-$RunId"
$StateFile = Join-Path $RuntimeDir "runtime-state.json"
$WorkspaceRoot = Join-Path $env:TEMP "clm-phase5-workspace-$RunId"
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

function Invoke-Structured {
  param([hashtable]$Body)
  return Invoke-RuntimeJson "Post" "/api/tasks/structured" $Body
}

function Approve {
  param([string]$ApprovalId)
  return Invoke-RuntimeJson "Post" "/api/approvals/$ApprovalId/decision" @{ approve = $true }
}

function Start-IsolatedRuntime {
  Remove-Item -Force $StateFile -ErrorAction SilentlyContinue
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
  $Psi.EnvironmentVariables["CLM_HOST_TEST_MODE"] = "1"
  $Psi.EnvironmentVariables["CLM_TEST_CLIPBOARD_TEXT"] = "OPENAI_TOKEN=phase5-secret"
  $script:Process = [System.Diagnostics.Process]::Start($Psi)
  $Deadline = (Get-Date).AddSeconds(25)
  while ((Get-Date) -lt $Deadline -and -not (Test-Path -LiteralPath $StateFile)) {
    if ($script:Process.HasExited) {
      throw "Runtime exited before writing state. stderr: $($script:Process.StandardError.ReadToEnd())"
    }
    Start-Sleep -Milliseconds 250
  }
  Assert-True (Test-Path -LiteralPath $StateFile) "Runtime state file was not created."
  $Health = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:$((Get-Content $StateFile -Raw | ConvertFrom-Json).port)/health" -TimeoutSec 10
  Assert-True ($Health.status -eq "ok") "Runtime health was not ok."
}

function Stop-IsolatedRuntime {
  if ($script:Process -and -not $script:Process.HasExited) {
    $script:Process.Kill()
    $script:Process.WaitForExit(5000) | Out-Null
  }
}

if (-not (Test-Path $VenvPython)) {
  throw ".venv-win is missing. Run scripts\bootstrap_windows.ps1 first."
}

Assert-IsolatedPath $RuntimeDir "RuntimeDir"
Assert-IsolatedPath $StateFile "StateFile"
Assert-IsolatedPath $WorkspaceRoot "Workspace"

$FormalHashBefore = Get-OptionalHash $FormalDb

New-Item -ItemType Directory -Force $RuntimeDir, $WorkspaceRoot | Out-Null
Set-Content -Path (Join-Path $WorkspaceRoot "small.txt") -Value "small" -Encoding UTF8
Set-Content -Path (Join-Path $WorkspaceRoot "move.txt") -Value "move" -Encoding UTF8
Set-Content -Path (Join-Path $WorkspaceRoot "rename.txt") -Value "rename" -Encoding UTF8
Set-Content -Path (Join-Path $WorkspaceRoot "recover.txt") -Value "recover" -Encoding UTF8
Set-Content -Path (Join-Path $WorkspaceRoot "example.pdf") -Value "%PDF-1.4 test" -Encoding ASCII
[System.IO.File]::WriteAllBytes((Join-Path $WorkspaceRoot "large.bin"), (New-Object byte[] 2048))

try {
  Start-IsolatedRuntime

  $Workspace = Invoke-RuntimeJson "Post" "/api/workspaces" @{ root_path = $WorkspaceRoot; display_name = "Phase 5 Smoke" }
  Assert-True ($Workspace.id.Length -gt 0) "Workspace was not created."

  $Large = Invoke-Structured @{ task_type = "FIND_LARGE_FILES"; workspace_id = $Workspace.id; path = "."; min_size_bytes = 1024 }
  Assert-True ($Large.state -eq "COMPLETED") "Large file search did not complete."
  Assert-True ($Large.observation.files[0].path -eq "large.bin") "Large file search did not find large.bin."

  $Copy = Invoke-Structured @{ task_type = "BATCH_COPY"; workspace_id = $Workspace.id; items = @(@{ source = "small.txt"; destination = "copies\small.txt" }) }
  Assert-True ($Copy.state -eq "COMPLETED") "Batch copy did not complete."
  Assert-True (Test-Path -LiteralPath (Join-Path $WorkspaceRoot "copies\small.txt")) "Batch copy destination missing."
  Assert-True ($Copy.observation.manifest_hash.Length -gt 0) "Batch copy did not expose manifest hash."

  $Move = Invoke-Structured @{ task_type = "BATCH_MOVE"; workspace_id = $Workspace.id; items = @(@{ source = "move.txt"; destination = "moved\move.txt" }) }
  Assert-True ($Move.state -eq "COMPLETED") "Batch move did not complete."
  Assert-True (-not (Test-Path -LiteralPath (Join-Path $WorkspaceRoot "move.txt"))) "Batch move source still exists."

  $Rename = Invoke-Structured @{ task_type = "BATCH_RENAME"; workspace_id = $Workspace.id; items = @(@{ source = "rename.txt"; destination = "renamed.txt" }) }
  Assert-True ($Rename.state -eq "COMPLETED") "Batch rename did not complete."
  Assert-True (Test-Path -LiteralPath (Join-Path $WorkspaceRoot "renamed.txt")) "Batch rename destination missing."

  $Zip = Invoke-Structured @{ task_type = "CREATE_ZIP"; workspace_id = $Workspace.id; path = "reports.zip"; items = @(@{ source = "small.txt" }, @{ source = "copies" }) }
  Assert-True ($Zip.state -eq "COMPLETED") "ZIP creation did not complete."
  Assert-True (Test-Path -LiteralPath (Join-Path $WorkspaceRoot "reports.zip")) "ZIP archive missing."

  $ExtractPending = Invoke-Structured @{ task_type = "EXTRACT_ZIP"; workspace_id = $Workspace.id; path = "reports.zip"; destination = "reports" }
  Assert-True ($ExtractPending.state -eq "WAITING_APPROVAL") "ZIP extract did not wait for approval."
  $Extract = Approve $ExtractPending.approval_id
  Assert-True ($Extract.state -eq "COMPLETED") "ZIP extract did not complete after approval."
  Assert-True (Test-Path -LiteralPath (Join-Path $WorkspaceRoot "reports\small.txt")) "Extracted file missing."

  & $VenvPython -c "import sys, zipfile; z=zipfile.ZipFile(sys.argv[1], 'w'); z.writestr('../escape.txt', 'bad'); z.close()" (Join-Path $WorkspaceRoot "bad.zip")
  $BadPending = Invoke-Structured @{ task_type = "EXTRACT_ZIP"; workspace_id = $Workspace.id; path = "bad.zip"; destination = "bad" }
  $Bad = Approve $BadPending.approval_id
  Assert-True ($Bad.state -eq "BLOCKED") "Malicious ZIP was not blocked."
  Assert-True (-not (Test-Path -LiteralPath (Join-Path (Split-Path $WorkspaceRoot -Parent) "escape.txt"))) "ZIP slip created escaped file."

  $RecoveryPending = Invoke-Structured @{ task_type = "MOVE_TO_RECOVERY_BIN"; workspace_id = $Workspace.id; path = "recover.txt"; recovery_item_id = "phase5-recover" }
  Assert-True ($RecoveryPending.state -eq "WAITING_APPROVAL") "Recovery move did not wait for approval."
  $Recovered = Approve $RecoveryPending.approval_id
  Assert-True ($Recovered.state -eq "COMPLETED") "Recovery move did not complete."
  Assert-True (-not (Test-Path -LiteralPath (Join-Path $WorkspaceRoot "recover.txt"))) "Recovery source still exists."
  $Restored = Invoke-Structured @{ task_type = "RESTORE_FROM_RECOVERY_BIN"; workspace_id = $Workspace.id; path = "recover.txt"; recovery_item_id = "phase5-recover" }
  Assert-True ($Restored.state -eq "COMPLETED") "Recovery restore did not complete."

  $OpenFile = Invoke-Structured @{ task_type = "OPEN_WORKSPACE_FILE"; workspace_id = $Workspace.id; path = "example.pdf" }
  Assert-True ($OpenFile.state -eq "COMPLETED") "Open workspace file did not use test adapter."
  Set-Content -Path (Join-Path $WorkspaceRoot "blocked.ps1") -Value "Write-Host blocked" -Encoding UTF8
  $BlockedOpen = Invoke-Structured @{ task_type = "OPEN_WORKSPACE_FILE"; workspace_id = $Workspace.id; path = "blocked.ps1" }
  Assert-True ($BlockedOpen.state -eq "BLOCKED") "Executable/script open was not blocked."

  $ClipboardWrite = Invoke-Structured @{ task_type = "CLIPBOARD_WRITE_TEXT"; text = "phase5 clipboard" }
  Assert-True ($ClipboardWrite.state -eq "COMPLETED") "Clipboard write did not complete."
  Assert-True ($ClipboardWrite.observation.characters -eq 16) "Clipboard write echoed unexpected metadata."
  $ClipboardReadPending = Invoke-Structured @{ task_type = "CLIPBOARD_READ_TEXT" }
  Assert-True ($ClipboardReadPending.state -eq "WAITING_APPROVAL") "Clipboard read did not wait for approval."
  $ClipboardRead = Approve $ClipboardReadPending.approval_id
  Assert-True ($ClipboardRead.state -eq "COMPLETED") "Clipboard read did not complete after approval."
  Assert-True (-not (($ClipboardRead | ConvertTo-Json -Depth 12) -match "phase5-secret")) "Clipboard secret was persisted or echoed."

  $CopyDetail = Invoke-RuntimeJson "Get" "/api/tasks/$($Copy.id)"
  Assert-True ($CopyDetail.undo_record_id.Length -gt 0) "Batch copy did not expose item undo through task detail."
  $Undo = Invoke-RuntimeJson "Post" "/api/undo/$($CopyDetail.undo_record_id)"
  Assert-True ($Undo.state -eq "COMPLETED") "Undo did not complete for batch copy item."
  Assert-True (-not (Test-Path -LiteralPath (Join-Path $WorkspaceRoot "copies\small.txt"))) "Undo did not remove copied file."

  $FormalHashAfter = Get-OptionalHash $FormalDb
  Assert-True ($FormalHashBefore -eq $FormalHashAfter) "Formal AppData database changed during isolated smoke."

  Write-Host "Phase 5 smoke passed."
  Write-Host "Isolated runtime data: $RuntimeDir"
  Write-Host "Isolated workspace: $WorkspaceRoot"
  Write-Host "Large files: COMPLETED"
  Write-Host "Batch copy/move/rename: COMPLETED"
  Write-Host "ZIP create/extract/malicious reject: COMPLETED"
  Write-Host "Recovery Bin move/restore: COMPLETED"
  Write-Host "Open file and clipboard used test adapters"
  Write-Host "Undo: COMPLETED"
  Write-Host "Human acceptance: DEFERRED_BY_USER - consolidated human acceptance will be performed after feature completion"
  Write-Host "Formal AppData DB hash before: $FormalHashBefore"
  Write-Host "Formal AppData DB hash after:  $FormalHashAfter"
}
finally {
  Stop-IsolatedRuntime
  Remove-Item -Recurse -Force $WorkspaceRoot -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force $RuntimeDir -ErrorAction SilentlyContinue
}
