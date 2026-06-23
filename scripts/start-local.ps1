# Windows local runtime script .
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvDir = Join-Path $repoRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$pidFile = Join-Path $repoRoot ".monitor-local.pid"
$stdoutLogFile = Join-Path $repoRoot "monitor-local.stdout.log"
$stderrLogFile = Join-Path $repoRoot "monitor-local.stderr.log"
$dbFile = Join-Path $repoRoot "monitor.sqlite3"
$dotenvPath = Join-Path $repoRoot ".env"
$requirementsPath = Join-Path $repoRoot "requirements.txt"
$requirementsStamp = Join-Path $venvDir ".requirements-installed"
$runtimeDir = Join-Path $repoRoot "runtime"
$updateStatusPath = Join-Path $runtimeDir "update-status.json"

function Require-Command($name, $installHint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "$name is required. $installHint"
    }
}

Require-Command "python" "Install Python 3.13 or newer and make sure python is on PATH."

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment..."
    python -m venv $venvDir
}

$env:VIRTUAL_ENV = $venvDir
$env:PATH = (Join-Path $venvDir "Scripts") + ";" + $env:PATH

$installDependencies = -not (Test-Path $requirementsStamp)
if (-not $installDependencies) {
    $installDependencies = (Get-Item $requirementsPath).LastWriteTimeUtc -gt (Get-Item $requirementsStamp).LastWriteTimeUtc
}

if ($installDependencies) {
    Write-Host "Installing Python dependencies..."
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed."
    }
    New-Item -ItemType File -Path $requirementsStamp -Force | Out-Null
}

if (-not (Test-Path (Join-Path $repoRoot "static\index.html"))) {
    throw "static\index.html is missing. Use a release checkout or run npm install and npm run build before starting locally."
}

if (-not (Test-Path $dotenvPath)) {
    Copy-Item (Join-Path $repoRoot ".env.example") $dotenvPath
}

Get-Content $dotenvPath | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) {
        return
    }
    $pair = $line -split "=", 2
    if ($pair.Count -ne 2) {
        return
    }
    $name = $pair[0].Trim()
    $value = $pair[1].Trim()
    [Environment]::SetEnvironmentVariable($name, $value, "Process")
}

if (Test-Path $pidFile) {
    $existingPid = (Get-Content $pidFile | Select-Object -First 1).Trim()
    if ($existingPid) {
        $existingProcess = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($existingProcess) {
            Write-Host "Monitor is already running at http://127.0.0.1:18787 (PID $existingPid)."
            exit 0
        }
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

$defaultCodexHome = Join-Path $env:USERPROFILE ".codex"
$codexHostHome = [Environment]::GetEnvironmentVariable("CODEX_HOST_HOME", "Process")
$codexHome = [Environment]::GetEnvironmentVariable("CODEX_HOME", "Process")
if (-not $codexHome -or $codexHome -eq "/codex") {
    $env:CODEX_HOME = if ($codexHostHome) { $codexHostHome } else { $defaultCodexHome }
}

$env:TIMEZONE = if ($env:TIMEZONE) { $env:TIMEZONE } else { "UTC" }
$env:MONITOR_DB = $dbFile
$env:UPDATE_STATUS_PATH = $updateStatusPath
if (-not $env:VALKEY_URL -or $env:VALKEY_URL -match "://valkey(:|/)") {
    $env:VALKEY_URL = "redis://127.0.0.1:6379/0"
}

$startInfo = @{
    FilePath = $venvPython
    ArgumentList = @(
        "-m", "uvicorn",
        "monitor_service:app",
        "--host", "127.0.0.1",
        "--port", "18787"
    )
    WorkingDirectory = $repoRoot
    WindowStyle = "Hidden"
    RedirectStandardOutput = $stdoutLogFile
    RedirectStandardError = $stderrLogFile
    PassThru = $true
}

$process = Start-Process @startInfo
Set-Content -Path $pidFile -Value $process.Id

$healthy = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:18787/healthz" -TimeoutSec 2
        if ($response.ok -eq $true) {
            $healthy = $true
            break
        }
    } catch {
    }
}

if (-not $healthy) {
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    throw "Monitor did not become healthy. See $stdoutLogFile and $stderrLogFile."
}

Write-Host "Codex Self-Hosted Web Monitor is running at http://127.0.0.1:18787"
Write-Host "PID: $($process.Id)"
Write-Host "Logs: $stdoutLogFile and $stderrLogFile"
