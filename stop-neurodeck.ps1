Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Compatibility: keep this script ASCII-only so Windows PowerShell 5.1 can parse it without a UTF-8 BOM.
$projectRoot = $PSScriptRoot
$pidPath = Join-Path $projectRoot "data\neurodeck.pid"
$pythonPath = (Resolve-Path -LiteralPath (Join-Path $projectRoot ".venv\Scripts\python.exe")).Path

$taskkillPath = Join-Path $env:SystemRoot "System32\taskkill.exe"

if (Test-Path -LiteralPath $pidPath -PathType Leaf) {
    $processId = [int](Get-Content -LiteralPath $pidPath -Raw)
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        $isProjectPython = $process.Path -eq $pythonPath -or $process.ProcessName -eq "python"
        if ($isProjectPython) {
            & $taskkillPath /PID $processId /T /F 2>$null | Out-Null
            $process.WaitForExit(3000) | Out-Null
        }
    }
    Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
}

# Fallback: clean up any lingering process listening on 5188 or 11435
try {
    $connections = Get-NetTCPConnection -LocalPort 5188, 11435 -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        $p = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if ($p -and ($p.Path -eq $pythonPath -or $p.ProcessName -eq "python")) {
            & $taskkillPath /PID $p.Id /T /F 2>$null | Out-Null
        }
    }
}
catch {
}

Write-Host "NeuroDeck stopped."
