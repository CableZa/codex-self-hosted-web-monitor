# Windows local runtime script .
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $repoRoot ".monitor-local.pid"

if (-not (Test-Path $pidFile)) {
    Write-Host "Monitor is not running."
    exit 0
}

$pidValue = (Get-Content $pidFile | Select-Object -First 1).Trim()
if (-not $pidValue) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host "Monitor is not running."
    exit 0
}

$process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
if ($process) {
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $pidValue" -ErrorAction SilentlyContinue
    if ($processInfo -and $processInfo.CommandLine -like "*monitor_service:app*") {
        Stop-Process -Id $pidValue -Force
        Write-Host "Stopped monitor process $pidValue."
    } else {
        Write-Host "PID $pidValue is not the local monitor. Removing stale PID file."
    }
} else {
    Write-Host "Monitor process $pidValue was not running."
}

Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
