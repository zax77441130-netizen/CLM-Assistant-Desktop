$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$RuntimeRoot = Join-Path $ProjectRoot "services\agent_runtime"
$VenvPython = Join-Path $ProjectRoot ".venv-win\Scripts\python.exe"
$FormalAppDataRoot = Join-Path $env:APPDATA "CLM Assistant Desktop"
$FormalDesktopWorkspace = "C:\Users\zong\Desktop\測試資料夾"
$RunId = [guid]::NewGuid().ToString("N")
$RuntimeDir = Join-Path $env:TEMP "clm-phase3-runtime-$RunId"
$StateFile = Join-Path $RuntimeDir "runtime-state.json"
$PidFile = Join-Path $RuntimeDir "runtime.pid"
$Sandbox = Join-Path $env:TEMP "clm-phase3-workspace-$RunId"
$Token = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")

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
    $JsonBody = $Body | ConvertTo-Json -Depth 12
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

function Invoke-Assistant {
  param([string]$Message, [string]$WorkspaceId)
  return Invoke-RuntimeJson "Post" "/api/assistant/tasks" @{ message = $Message; workspace_id = $WorkspaceId }
}

function U {
  param([string]$Escaped)
  return [regex]::Unescape($Escaped)
}

if (-not (Test-Path $VenvPython)) {
  throw ".venv-win is missing. Run scripts\bootstrap_windows.ps1 first."
}

Assert-IsolatedPath $RuntimeDir "RuntimeDir"
Assert-IsolatedPath $StateFile "StateFile"
Assert-IsolatedPath $Sandbox "Workspace"

New-Item -ItemType Directory -Force $RuntimeDir, $Sandbox | Out-Null
Remove-Item -Force $StateFile, $PidFile -ErrorAction SilentlyContinue

Set-Content -Path (Join-Path $Sandbox "example.txt") -Value "hello phase 3" -Encoding UTF8
Set-Content -Path (Join-Path $Sandbox "duplicate-a.txt") -Value "same-content" -Encoding UTF8
Set-Content -Path (Join-Path $Sandbox "duplicate-b.txt") -Value "same-content" -Encoding UTF8
Set-Content -Path (Join-Path $Sandbox "overwrite.txt") -Value "before" -Encoding UTF8

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
  $Deadline = (Get-Date).AddSeconds(25)
  while ((Get-Date) -lt $Deadline -and -not (Test-Path $StateFile)) {
    if ($Process.HasExited) {
      throw "Runtime exited before writing state. stderr: $($Process.StandardError.ReadToEnd())"
    }
    Start-Sleep -Milliseconds 250
  }
  Assert-True (Test-Path $StateFile) "Runtime state file was not created."

  $Health = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:$((Get-Content $StateFile -Raw | ConvertFrom-Json).port)/health" -TimeoutSec 10
  Assert-True ($Health.status -eq "ok") "Runtime health was not ok."

  $Workspace = Invoke-RuntimeJson "Post" "/api/workspaces" @{ root_path = $Sandbox; display_name = "Phase 3 Smoke" }
  Assert-True ($Workspace.id.Length -gt 0) "Workspace was not created."

  $Provider = Invoke-RuntimeJson "Get" "/api/provider/settings"
  Assert-True ($Provider.mode -eq "local") "Provider did not default to local command mode."
  $ProviderJson = $Provider | ConvertTo-Json -Depth 10
  Assert-True (-not ($ProviderJson -match "api_key|sk-")) "Provider settings leaked key material."

  $List = Invoke-Assistant (U "\u5217\u51fa\u76ee\u524d\u5de5\u4f5c\u5340\u7684\u6a94\u6848") $Workspace.id
  Assert-True ($List.state -eq "COMPLETED") "List directory did not complete."
  Assert-True ($List.resultText -match (U "\u5df2\u627e\u5230")) "List directory did not present Chinese result text."
  Assert-True ($List.resultText -match "example.txt") "List directory result did not include example.txt."
  Assert-True ([string]::IsNullOrEmpty($List.observationPreview)) "List directory duplicated the result in observation preview."

  $Read = Invoke-Assistant (U "\u8b80\u53d6 example.txt") $Workspace.id
  Assert-True ($Read.state -eq "COMPLETED") "Read text did not complete."
  Assert-True ($Read.resultText -match (U "\u5df2\u8b80\u53d6 example.txt")) "Read text did not present Chinese result text."
  Assert-True ($Read.observationPreview -match "hello phase 3") "Read preview did not include file content."

  $Duplicates = Invoke-Assistant (U "\u627e\u51fa\u91cd\u8907\u6a94\u6848") $Workspace.id
  Assert-True ($Duplicates.state -eq "COMPLETED") "Find duplicates did not complete."
  Assert-True ($Duplicates.observationPreview -match "duplicate-a.txt") "Duplicate preview did not include duplicate-a.txt."
  Assert-True ($Duplicates.observationPreview -match "duplicate-b.txt") "Duplicate preview did not include duplicate-b.txt."

  $CreatedFolder = U "\u6e2c\u8a66\u5efa\u7acb"
  $CreateDir = Invoke-Assistant ((U "\u5efa\u7acb\u8cc7\u6599\u593e ") + $CreatedFolder) $Workspace.id
  Assert-True ($CreateDir.state -eq "COMPLETED") "Create directory did not complete."
  Assert-True (Test-Path (Join-Path $Sandbox $CreatedFolder)) "Created folder was missing."
  Assert-True ($CreateDir.undo_record_id.Length -gt 0) "Create directory did not expose undo record."

  $Undo = Invoke-RuntimeJson "Post" "/api/undo/$($CreateDir.undo_record_id)"
  Assert-True ($Undo.state -eq "COMPLETED") "Undo did not complete."
  Assert-True (-not (Test-Path (Join-Path $Sandbox $CreatedFolder))) "Undo did not remove created folder."

  $Overwrite = Invoke-Assistant (U "\u8986\u5beb overwrite.txt \u70ba after") $Workspace.id
  Assert-True ($Overwrite.state -eq "WAITING_APPROVAL") "Overwrite did not wait for approval."
  Assert-True ((Get-Content (Join-Path $Sandbox "overwrite.txt") -Raw).Trim() -eq "before") "Overwrite changed file before approval."
  Assert-True ($Overwrite.approval_id.Length -gt 0) "Overwrite did not return approval id."

  $Rejected = Invoke-RuntimeJson "Post" "/api/approvals/$($Overwrite.approval_id)/decision" @{ approve = $false }
  Assert-True ($Rejected.state -eq "BLOCKED") "Rejected approval did not block task."
  Assert-True ((Get-Content (Join-Path $Sandbox "overwrite.txt") -Raw).Trim() -eq "before") "Rejected approval changed file."

  $Clarify = Invoke-Assistant (U "\u5e6b\u6211\u6574\u7406\u4e00\u4e0b") $Workspace.id
  Assert-True ($Clarify.state -eq "WAITING_CLARIFICATION") "Ambiguous request did not wait for clarification."
  Assert-True ($Clarify.resultText -match (U "\u8acb\u88dc\u5145")) "Clarification message was not user-facing Chinese."

  $Cancelled = Invoke-RuntimeJson "Post" "/api/assistant/tasks/$($Clarify.id)/cancel"
  Assert-True ($Cancelled.state -eq "CANCELLED") "Cancellation did not cancel waiting task."

  $AppSource = [System.IO.File]::ReadAllText((Join-Path $ProjectRoot "apps\desktop\src\renderer\App.tsx"), [System.Text.Encoding]::UTF8)
  $AssistantSource = $AppSource.Substring(0, $AppSource.IndexOf("function SettingsPage"))
  Assert-True (-not ($AssistantSource -match "\b(LIST_DIRECTORY|READ_TEXT|relative path|IPC|token|port|SQLAlchemy|sqlite3)\b")) "Assistant home exposes implementation details."
  Assert-True ($AssistantSource -match (U "\u67e5\u770b\u6280\u8853\u8a73\u7d30\u8cc7\u6599")) "Assistant home is missing collapsed technical details."

  Write-Host "Phase 3 smoke passed."
  Write-Host "Provider: local command mode"
  Write-Host "Natural language tasks: list/read/duplicates/create/undo/approval/clarification/cancel"
  Write-Host "UI static check: assistant home hides tool IDs and raw implementation details"
}
finally {
  if ($Process -and -not $Process.HasExited) {
    $Process.Kill()
    $Process.WaitForExit(5000) | Out-Null
  }
  Remove-Item -Recurse -Force $Sandbox -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force $RuntimeDir -ErrorAction SilentlyContinue
}
