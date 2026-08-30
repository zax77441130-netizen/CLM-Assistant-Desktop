$ErrorActionPreference = "Stop"

$ProjectRoot = "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
$RuntimeRoot = Join-Path $ProjectRoot "services\agent_runtime"
$VenvPython = Join-Path $ProjectRoot ".venv-win\Scripts\python.exe"
$FormalAppDataRoot = Join-Path $env:APPDATA "CLM Assistant Desktop"
$FormalDesktopWorkspace = "C:\Users\zong\Desktop\測試資料夾"
$RunId = [guid]::NewGuid().ToString("N")
$RuntimeDir = Join-Path $env:TEMP "clm-phase3-write-runtime-$RunId"
$StateFile = Join-Path $RuntimeDir "runtime-state.json"
$PidFile = Join-Path $RuntimeDir "runtime.pid"
$WorkspaceRoot = Join-Path $env:TEMP "clm-phase3-write-workspace-$RunId"
$FolderName = "phase3-write-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 8)
$ExpectedPath = Join-Path $WorkspaceRoot $FolderName
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

if (-not (Test-Path $VenvPython)) {
  throw ".venv-win is missing. Run scripts\bootstrap_windows.ps1 first."
}

Assert-IsolatedPath $RuntimeDir "RuntimeDir"
Assert-IsolatedPath $StateFile "StateFile"
Assert-IsolatedPath $WorkspaceRoot "Workspace"
Assert-IsolatedPath $ExpectedPath "TargetPath"

New-Item -ItemType Directory -Force $RuntimeDir, $WorkspaceRoot | Out-Null
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

  $Workspace = Invoke-RuntimeJson "Post" "/api/workspaces" @{ root_path = $WorkspaceRoot; display_name = "Phase 3 Write Smoke" }
  Assert-True ($Workspace.id.Length -gt 0) "Workspace was not created."
  Assert-True ($Workspace.display_path -eq (Resolve-Path -LiteralPath $WorkspaceRoot).Path) "Workspace path returned by Runtime did not match requested root."
  Assert-True (-not (Test-Path -LiteralPath $ExpectedPath)) "Unique target folder already existed before task."

  $CreateMessage = (U "\u5efa\u7acb\u8cc7\u6599\u593e ") + $FolderName
  $Created = Invoke-RuntimeJson "Post" "/api/assistant/tasks" @{ message = $CreateMessage; workspace_id = $Workspace.id }
  $ExistsAfterCreate = Test-Path -LiteralPath $ExpectedPath
  Assert-True ($Created.state -eq "COMPLETED") "Create folder task did not complete."
  Assert-True ($ExistsAfterCreate) "Windows Test-Path did not find the created folder."
  Assert-True ((Get-Item -LiteralPath $ExpectedPath).PSIsContainer) "Created target is not a directory."
  Assert-True ($Created.resultText -match $FolderName) "Create folder result did not name the created folder."
  Assert-True ($Created.technicalDetails.postcondition.verified -eq $true) "Create folder observation did not contain verified postcondition."
  Assert-True ($Created.undo_record_id.Length -gt 0) "Create folder did not return undo record."

  $Undo = Invoke-RuntimeJson "Post" "/api/undo/$($Created.undo_record_id)"
  $ExistsAfterUndo = Test-Path -LiteralPath $ExpectedPath
  Assert-True ($Undo.state -eq "COMPLETED") "Undo did not complete."
  Assert-True (-not $ExistsAfterUndo) "Windows Test-Path still found the folder after Undo."

  Write-Host "Phase 3 write smoke passed."
  Write-Host "Workspace id: $($Workspace.id)"
  Write-Host "Workspace path: $WorkspaceRoot"
  Write-Host "Target path: $ExpectedPath"
  Write-Host "Test-Path after create: $ExistsAfterCreate"
  Write-Host "Test-Path after undo: $ExistsAfterUndo"
}
finally {
  if ($Process -and -not $Process.HasExited) {
    $Process.Kill()
    $Process.WaitForExit(5000) | Out-Null
  }
  Remove-Item -Recurse -Force $WorkspaceRoot -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force $RuntimeDir -ErrorAction SilentlyContinue
}
