param(
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Compatibility: keep this script ASCII-only so Windows PowerShell 5.1 can parse it without a UTF-8 BOM.
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$backendPath = Join-Path $projectRoot "backend"
$frontendIndex = Join-Path $projectRoot "frontend\dist\index.html"
$dataPath = Join-Path $projectRoot "data"
$logPath = Join-Path $dataPath "logs"
$pidPath = Join-Path $dataPath "neurodeck.pid"
$dashboardUrl = "http://127.0.0.1:5188"
$healthUrl = "$dashboardUrl/api/health"
$ollamaProxyUrl = "http://127.0.0.1:11435"
$ollamaProxyHealthUrl = "$ollamaProxyUrl/_neurodeck/health"

function Test-NeuroDeckHealth {
    try {
        $result = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1
        return $result.status -eq "ok"
    }
    catch {
        return $false
    }
}

function Test-OllamaProxyHealth {
    try {
        $result = Invoke-RestMethod -Uri $ollamaProxyHealthUrl -TimeoutSec 1
        return $result.status -eq "ok"
    }
    catch {
        return $false
    }
}

function Test-NeuroDeckReady {
    return (Test-NeuroDeckHealth) -and (Test-OllamaProxyHealth)
}

if (Test-NeuroDeckReady) {
    Write-Host "NeuroDeck is already running: $dashboardUrl"
    Write-Host "Ollama proxy is already running: $ollamaProxyUrl -> http://127.0.0.1:11434"
    if (-not $NoBrowser) {
        try {
            Start-Process -FilePath $dashboardUrl
        }
        catch {
            Write-Warning "Dashboard is running, but the browser could not be opened automatically: $dashboardUrl"
        }
    }
    exit 0
}

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Project virtual environment was not found: $pythonPath"
}
if (-not (Test-Path -LiteralPath $frontendIndex -PathType Leaf)) {
    throw "Frontend production build is missing. Run npm run build in frontend first."
}

New-Item -ItemType Directory -Path $logPath -Force | Out-Null
$stdoutPath = Join-Path $logPath "neurodeck.stdout.log"
$stderrPath = Join-Path $logPath "neurodeck.stderr.log"

# Safety: never take over an unknown process referenced by a stale or reused PID.
if (Test-Path -LiteralPath $pidPath -PathType Leaf) {
    $existingId = [int](Get-Content -LiteralPath $pidPath -Raw)
    $existingProcess = Get-Process -Id $existingId -ErrorAction SilentlyContinue
    if ($existingProcess) {
        throw "NeuroDeck PID $existingId exists but health check failed. Run stop-neurodeck.cmd first."
    }
    Remove-Item -LiteralPath $pidPath -Force
}

$arguments = @(
    "-m", "uvicorn", "app.main:app",
    "--host", "127.0.0.1",
    "--port", "5188"
)
$processArguments = @{
    FilePath = $pythonPath
    ArgumentList = $arguments
    WorkingDirectory = $backendPath
    WindowStyle = "Hidden"
    RedirectStandardOutput = $stdoutPath
    RedirectStandardError = $stderrPath
    PassThru = $true
}

# Compatibility: some Windows environments expose PATH and Path simultaneously.
# Retry with a clean system environment only when Start-Process rejects that duplicate.
try {
    $process = Start-Process @processArguments
}
catch [System.ArgumentException] {
    # Some PowerShell 5.1 hosts cannot build Start-Process's environment map
    # when PATH exists with multiple casings. The .NET launcher avoids that map;
    # logs are unavailable only in this compatibility path.
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $pythonPath
    $startInfo.Arguments = $arguments -join " "
    $startInfo.WorkingDirectory = $backendPath
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $process = [System.Diagnostics.Process]::Start($startInfo)
}
Set-Content -LiteralPath $pidPath -Value $process.Id -Encoding ascii

# Wait up to 10 seconds; on failure, stop only the process created above and preserve its logs.
$ready = $false
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 250
    if (Test-NeuroDeckReady) {
        $ready = $true
        break
    }
    if ($process.HasExited) {
        break
    }
}

if (-not $ready) {
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
    Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    throw "NeuroDeck failed to start. See $stderrPath"
}

Write-Host "NeuroDeck started: $dashboardUrl"
Write-Host "Ollama proxy started: $ollamaProxyUrl -> http://127.0.0.1:11434"
Write-Host "To stop it, double-click stop-neurodeck.cmd"
if (-not $NoBrowser) {
    try {
        Start-Process -FilePath $dashboardUrl
    }
    catch {
        Write-Warning "Dashboard is running, but the browser could not be opened automatically: $dashboardUrl"
    }
}
