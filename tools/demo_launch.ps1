# UrbanTwin judge demo launcher - API + Kit streaming + Next.js frontend.
# Usage: .\tools\demo_launch.ps1 [-Force]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Get-ArgusRoot {
    param([string]$ScriptRoot)
    $parent = (Resolve-Path (Join-Path $ScriptRoot "..")).Path
    $worktree = Join-Path $parent ".worktrees\phase13-streaming-kit"
    $worktreeApi = Join-Path $worktree "api\server.py"
    if ((Test-Path -LiteralPath $worktreeApi) -and ($parent -notmatch "\\\.worktrees\\phase13-streaming-kit$")) {
        return (Resolve-Path $worktree).Path
    }
    return $parent
}

function Stop-ListenersOnPort {
    param([int]$Port)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $procId = $c.OwningProcess
        if ($procId -and $procId -ne 0) {
            Write-Host ("  Stopping PID {0} listening on port {1}" -f $procId, $Port)
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Wait-HttpJson {
    param(
        [string]$Url,
        [int]$MaxSeconds = 90
    )
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            return Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 5
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $null
}

function Start-DemoWindow {
    param(
        [string]$Title,
        [string]$ScriptPath
    )
    $argList = "-NoExit -ExecutionPolicy Bypass -File `"$ScriptPath`""
    Start-Process -FilePath "powershell.exe" -ArgumentList $argList | Out-Null
    Write-Host ("Started: {0}" -f $Title)
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ArgusRoot = Get-ArgusRoot -ScriptRoot $ScriptRoot
$LogDir = Join-Path $ScriptRoot "demo_logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ApiLog = Join-Path $LogDir ("api-{0}.log" -f $Stamp)
$FrontendLog = Join-Path $LogDir ("frontend-{0}.log" -f $Stamp)
$KitBat = "C:\Users\arnav\omniverse\kit-app-template\launch_urbantwin_streaming.bat"

$ApiScript = Join-Path $LogDir ("start-api-{0}.ps1" -f $Stamp)
$FrontendScript = Join-Path $LogDir ("start-frontend-{0}.ps1" -f $Stamp)

Write-Host "UrbanTwin demo launch"
Write-Host ("  Argus root: {0}" -f $ArgusRoot)
Write-Host ("  Logs:       {0}" -f $LogDir)
Write-Host ""

if ($Force) {
    Write-Host "Force: stopping listeners on ports 8000 and 3000 (if any)..."
    Stop-ListenersOnPort -Port 8000
    Stop-ListenersOnPort -Port 3000
    Write-Host ""
}

$apiLines = @(
    ("Set-Location -LiteralPath '{0}'" -f $ArgusRoot)
    '$Host.UI.RawUI.WindowTitle = ''UrbanTwin API (:8000)'''
    ("python -m api --host 127.0.0.1 --port 8000 2>&1 | Tee-Object -FilePath '{0}'" -f $ApiLog)
)
$apiLines | Set-Content -LiteralPath $ApiScript -Encoding ASCII

Start-DemoWindow -Title "Python API (:8000)" -ScriptPath $ApiScript

if (Test-Path -LiteralPath $KitBat) {
    Start-Process -FilePath "cmd.exe" -ArgumentList ("/c `"{0}`"" -f $KitBat) | Out-Null
    Write-Host "Started Kit streaming via launch_urbantwin_streaming.bat."
} else {
    Write-Warning ("Kit launcher not found at {0} - start Kit manually for stream online." -f $KitBat)
}

$FrontendDir = Join-Path $ArgusRoot "frontend"
$feLines = @(
    ("Set-Location -LiteralPath '{0}'" -f $FrontendDir)
    '$env:URBANTWIN_API_BASE = ''http://127.0.0.1:8000'''
    '$Host.UI.RawUI.WindowTitle = ''UrbanTwin Frontend'''
    ("npm run dev 2>&1 | Tee-Object -FilePath '{0}'" -f $FrontendLog)
)
$feLines | Set-Content -LiteralPath $FrontendScript -Encoding ASCII

Start-DemoWindow -Title "Next.js frontend" -ScriptPath $FrontendScript
Write-Host ""

Write-Host "Waiting for API health (up to 90s)..."
$health = Wait-HttpJson -Url "http://127.0.0.1:8000/api/health" -MaxSeconds 90
if (-not $health) {
    Write-Warning ("API health did not respond in time. Check {0}" -f $ApiLog)
} else {
    Write-Host ("  mode: {0}, omniverse_stream: {1}" -f $health.mode, $health.omniverse_stream)
}

Write-Host "Waiting for stream config..."
$stream = Wait-HttpJson -Url "http://127.0.0.1:8000/api/stream/config" -MaxSeconds 30
if ($stream) {
    Write-Host ("  stream status: {0}" -f $stream.status)
} else {
    Write-Warning "Stream config not reachable yet."
}

Write-Host ""
Write-Host "Ready URLs:"
Write-Host "  Dashboard:  http://127.0.0.1:3000  (or http://127.0.0.1:3001 if 3000 was busy)"
Write-Host "  API health: http://127.0.0.1:8000/api/health"
Write-Host "  Stream cfg: http://127.0.0.1:8000/api/stream/config"
Write-Host "  Kit signal: tcp://127.0.0.1:49100 (when streaming host is up)"
Write-Host ""
Write-Host "Smoke test:  python tools\demo_smoke.py"
Write-Host "Runbook:     docs\DEMO_RUNBOOK.md"
Write-Host ("API log:     {0}" -f $ApiLog)
Write-Host ("Frontend log: {0}" -f $FrontendLog)
