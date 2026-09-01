$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$RuntimeRoot = Join-Path $ProjectRoot "services\agent_runtime"
$VenvPython = Join-Path $ProjectRoot ".venv-win\Scripts\python.exe"
$FormalAppDataRoot = Join-Path $env:APPDATA "CLM Assistant Desktop"
$FormalDb = Join-Path $FormalAppDataRoot "runtime\clm_assistant.sqlite3"
$FormalDesktopWorkspace = "C:\Users\zong\Desktop\CLM-Formal-Smoke-Workspace"
$RunId = [guid]::NewGuid().ToString("N")
$RuntimeDir = Join-Path $env:TEMP "clm-phase6-runtime-$RunId"
$ArtifactDir = Join-Path $env:TEMP "clm-phase6-artifacts-$RunId"
$StateFile = Join-Path $RuntimeDir "runtime-state.json"
$Token = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
$Process = $null

function Assert-True {
  param([bool]$Condition, [string]$Message)
  if (-not $Condition) { throw $Message }
}

function U {
  param([string]$Escaped)
  return [regex]::Unescape($Escaped)
}

function Assert-IsolatedPath {
  param([string]$Path, [string]$Name)
  $FullPath = [System.IO.Path]::GetFullPath($Path)
  $AppDataFull = [System.IO.Path]::GetFullPath($FormalAppDataRoot)
  $WorkspaceFull = [System.IO.Path]::GetFullPath($FormalDesktopWorkspace)
  Assert-True (-not $FullPath.StartsWith($AppDataFull, [System.StringComparison]::OrdinalIgnoreCase)) "$Name resolved into formal AppData."
  Assert-True (-not $FullPath.StartsWith($WorkspaceFull, [System.StringComparison]::OrdinalIgnoreCase)) "$Name resolved into formal desktop workspace."
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
    try { $Stream.Write($Utf8Body, 0, $Utf8Body.Length) }
    finally { $Stream.Dispose() }
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
  $Psi.EnvironmentVariables["CLM_DESKTOP_AUTOMATION_ADAPTER"] = "fake"
  $Psi.EnvironmentVariables["CLM_SCREEN_ARTIFACT_DIR"] = $ArtifactDir
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

if (-not (Test-Path -LiteralPath $VenvPython)) {
  throw ".venv-win is missing. Run scripts\bootstrap_windows.ps1 first."
}
Assert-True (Test-Path -LiteralPath (Join-Path $ProjectRoot "scripts\fixtures\phase6_uia_fixture.ps1")) "Phase 6 UIA fixture script is missing."

Assert-IsolatedPath $RuntimeDir "RuntimeDir"
Assert-IsolatedPath $ArtifactDir "ArtifactDir"
Assert-IsolatedPath $StateFile "StateFile"

$FormalHashBefore = Get-OptionalHash $FormalDb
New-Item -ItemType Directory -Force $RuntimeDir, $ArtifactDir | Out-Null

try {
  Push-Location $RuntimeRoot
  try {
    $env:CLM_UIA_NONINTERACTIVE = "1"
    & $VenvPython -c "from app.core.desktop_tools import WindowsUIAutomationAdapter; import sys;`ntry:`n WindowsUIAutomationAdapter(); raise SystemExit('adapter did not defer')`nexcept ValueError as exc:`n assert str(exc) == 'UIA_LIVE_DEFERRED_NONINTERACTIVE_SESSION'"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Remove-Item Env:\CLM_UIA_NONINTERACTIVE -ErrorAction SilentlyContinue
    & $VenvPython -c "from app.core.desktop_tools import adapter_from_environment, WindowsUIAutomationAdapter; a=adapter_from_environment(); assert isinstance(a, WindowsUIAutomationAdapter)"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
  finally {
    Remove-Item Env:\CLM_UIA_NONINTERACTIVE -ErrorAction SilentlyContinue
    Pop-Location
  }

  Start-IsolatedRuntime

  $Listed = Invoke-Structured @{ task_type = "DESKTOP_LIST_WINDOWS"; app = "notepad" }
  Assert-True ($Listed.state -eq "COMPLETED") "Desktop list windows did not complete."
  Assert-True ($Listed.observation.count -eq 1) "Fake fixture window was not listed."
  $Target = $Listed.observation.windows[0]
  Assert-True ($Target.windowSessionId.Length -gt 0) "Window session id missing."
  Assert-True ($Target.targetFingerprint.Length -gt 0) "Window fingerprint missing."

  $Waited = Invoke-Structured @{ task_type = "DESKTOP_WAIT_FOR_WINDOW"; app = "notepad"; timeout_seconds = 2 }
  Assert-True ($Waited.state -eq "COMPLETED") "Desktop wait did not complete."

  $Activated = Invoke-Structured @{ task_type = "DESKTOP_ACTIVATE_WINDOW"; window = $Target }
  Assert-True ($Activated.state -eq "COMPLETED") "Desktop activation did not complete."

  $Maximized = Invoke-Structured @{ task_type = "DESKTOP_SET_WINDOW_STATE"; window = $Target; window_state = "maximize" }
  Assert-True ($Maximized.state -eq "COMPLETED") "Maximize did not complete."
  Assert-True ($Maximized.observation.state -eq "maximize") "Maximize postcondition failed."

  $Restored = Invoke-Structured @{ task_type = "DESKTOP_SET_WINDOW_STATE"; window = $Target; window_state = "restore" }
  Assert-True ($Restored.state -eq "COMPLETED") "Restore did not complete."
  Assert-True ($Restored.observation.state -eq "restore") "Restore postcondition failed."

  $Controls = Invoke-Structured @{ task_type = "DESKTOP_INSPECT_CONTROLS"; window = $Target }
  Assert-True ($Controls.state -eq "COMPLETED") "Inspect controls did not complete."
  Assert-True ($Controls.observation.count -ge 3) "Fixture controls missing."

  $TextPending = Invoke-Structured @{ task_type = "DESKTOP_SET_CONTROL_TEXT"; window = $Target; control = @{ name = (U "\u5167\u5bb9"); controlType = "Edit" }; text = "phase6 text" }
  Assert-True ($TextPending.state -eq "WAITING_APPROVAL") "Set text did not wait for approval."
  $TextSet = Approve $TextPending.approval_id
  Assert-True ($TextSet.state -eq "COMPLETED") "Set text did not complete after approval."

  $PasswordPending = Invoke-Structured @{ task_type = "DESKTOP_SET_CONTROL_TEXT"; window = $Target; control = @{ name = (U "\u5bc6\u78bc"); controlType = "Edit" }; text = "secret" }
  Assert-True ($PasswordPending.state -eq "WAITING_APPROVAL") "Password write did not enter approval first."
  $PasswordRejected = Approve $PasswordPending.approval_id
  Assert-True ($PasswordRejected.state -eq "BLOCKED") "Password control was not rejected."

  $InvokePending = Invoke-Structured @{ task_type = "DESKTOP_INVOKE_CONTROL"; window = $Target; control = @{ name = (U "\u57f7\u884c"); controlType = "Button" } }
  Assert-True ($InvokePending.state -eq "WAITING_APPROVAL") "Invoke did not wait for approval."
  $Invoked = Approve $InvokePending.approval_id
  Assert-True ($Invoked.state -eq "COMPLETED") "Invoke did not complete after approval."

  $CapturePending = Invoke-Structured @{ task_type = "DESKTOP_CAPTURE_WINDOW"; window = $Target }
  Assert-True ($CapturePending.state -eq "WAITING_APPROVAL") "Capture did not wait for approval."
  $Captured = Approve $CapturePending.approval_id
  Assert-True ($Captured.state -eq "COMPLETED") "Capture did not complete after approval."
  Assert-True ($Captured.observation.artifactId.Length -gt 0) "Capture artifact id missing."
  Assert-True (-not (($Captured | ConvertTo-Json -Depth 10) -match [regex]::Escape($ArtifactDir))) "Capture leaked raw artifact path."

  $ClosePending = Invoke-Structured @{ task_type = "DESKTOP_CLOSE_WINDOW"; window = $Target }
  Assert-True ($ClosePending.state -eq "WAITING_APPROVAL") "Close did not wait for approval."
  $Closed = Approve $ClosePending.approval_id
  Assert-True ($Closed.state -eq "COMPLETED") "Close did not complete after approval."

  $FormalHashAfter = Get-OptionalHash $FormalDb
  Assert-True ($FormalHashBefore -eq $FormalHashAfter) "Formal AppData database changed during isolated smoke."

  Write-Host "Phase 6 smoke passed."
  Write-Host "Production adapter composition: PASS"
  Write-Host "Desktop adapter contract fixture: PASS"
  Write-Host "Window identity binding: PASS"
  Write-Host "Activate/maximize/restore postconditions: PASS"
  Write-Host "Inspect/set text/invoke/capture/close approval flow: PASS"
  Write-Host "Password control rejection: PASS"
  Write-Host "Screenshot artifact isolation: PASS"
  Write-Host "UIA_LIVE=DEFERRED_BY_USER_NONINTERACTIVE_SESSION"
  Write-Host "Human acceptance: DEFERRED_BY_USER - consolidated human acceptance will be performed after feature completion"
  Write-Host "Formal AppData DB hash before: $FormalHashBefore"
  Write-Host "Formal AppData DB hash after:  $FormalHashAfter"
}
finally {
  Stop-IsolatedRuntime
  Remove-Item -Recurse -Force $ArtifactDir -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force $RuntimeDir -ErrorAction SilentlyContinue
}
