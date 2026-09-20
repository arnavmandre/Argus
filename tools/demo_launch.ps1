# Argus AI local demo launcher - API + Kit streaming + Next.js dashboard.
# Usage:
#   .\tools\demo_launch.ps1
#   .\tools\demo_launch.ps1 -Force          # free ports 8000/3000/49100 first
#   .\Start-Argus.bat                       # double-click from Explorer
param(
    [switch]$Force,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

function Get-ArgusRoot {
    param([string]$ScriptRoot)
    return (Resolve-Path (Join-Path $ScriptRoot "..")).Path
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

function Stop-KitProcesses {
    Get-Process -Name kit -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host ("  Stopping Kit PID {0}" -f $_.Id)
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        try { & taskkill.exe /F /PID $_.Id 2>$null | Out-Null } catch { }
    }
}

function Stop-EverythingForDemo {
    Write-Host "Force: stopping Kit and listeners on 8000 / 3000 / 3001 / 49100 / 47998..."
    Stop-KitProcesses
    foreach ($port in 8000, 3000, 3001, 49100, 47998) {
        Stop-ListenersOnPort -Port $port
    }
    # Second pass: Kit sometimes leaves the signaling port stuck for a moment.
    Start-Sleep -Seconds 2
    Stop-KitProcesses
    Stop-ListenersOnPort -Port 49100
    Write-Host ""
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

function Wait-TcpPort {
    param(
        [string]$HostName = "127.0.0.1",
        [int]$Port,
        [int]$MaxSeconds = 120
    )
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $iar = $client.BeginConnect($HostName, $Port, $null, $null)
            $ok = $iar.AsyncWaitHandle.WaitOne(1000, $false)
            if ($ok -and $client.Connected) {
                $client.EndConnect($iar)
                $client.Close()
                return $true
            }
            $client.Close()
        } catch {
            # keep waiting
        }
        Start-Sleep -Seconds 2
    }
    return $false
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

function Resolve-DashboardUrl {
    param([int]$PreferPort = 3000)
    foreach ($port in @($PreferPort, 3001, 3002)) {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($conns) {
            return "http://127.0.0.1:$port"
        }
    }
    return "http://127.0.0.1:$PreferPort"
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ArgusRoot = Get-ArgusRoot -ScriptRoot $ScriptRoot
$LogDir = Join-Path $ScriptRoot "demo_logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ApiLog = Join-Path $LogDir ("api-{0}.log" -f $Stamp)
$FrontendLog = Join-Path $LogDir ("frontend-{0}.log" -f $Stamp)
$KitLog = Join-Path $LogDir ("kit-{0}.log" -f $Stamp)
$KitBat = "C:\Users\arnav\omniverse\kit-app-template\launch_urbantwin_streaming.bat"
$KitRoot = "C:\Users\arnav\omniverse\kit-app-template"

$ApiScript = Join-Path $LogDir ("start-api-{0}.ps1" -f $Stamp)
$FrontendScript = Join-Path $LogDir ("start-frontend-{0}.ps1" -f $Stamp)
$KitScript = Join-Path $LogDir ("start-kit-{0}.ps1" -f $Stamp)

Write-Host "Argus AI - demo launch"
Write-Host ("  Argus root: {0}" -f $ArgusRoot)
Write-Host ("  Logs:       {0}" -f $LogDir)
Write-Host ""
Write-Host "NOTE: Omniverse Kit streaming starts with --no-window."
Write-Host "      You will NOT see a normal Omniverse editor. Look for a console"
Write-Host "      titled 'Argus AI Kit Streaming' and a Live viewport in Chrome/Edge."
Write-Host ""

if (-not (Test-Path -LiteralPath (Join-Path $ArgusRoot "api\server.py"))) {
    throw "api\server.py not found under $ArgusRoot - run this from the Argus repo."
}

$FrontendDir = Join-Path $ArgusRoot "frontend"
if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir "package.json"))) {
    throw "frontend\package.json not found under $ArgusRoot."
}

if ($Force) {
    Stop-EverythingForDemo
} else {
    # Soft check: warn if Kit/signaling already running (common cause of
    # "Failed to start the primary stream server" / NVST_R_INTERNAL_ERROR).
    $existingKit = Get-Process -Name kit -ErrorAction SilentlyContinue
    $sigBusy = Get-NetTCPConnection -LocalPort 49100 -State Listen -ErrorAction SilentlyContinue
    if ($existingKit -or $sigBusy) {
        Write-Warning "Kit or port 49100 is already in use."
        Write-Warning "That usually breaks WebRTC with: Failed to start the primary stream server."
        Write-Warning "Re-run with: Start-Argus.bat -Force"
        Write-Host ""
    }
}

$apiLines = @(
    ("Set-Location -LiteralPath '{0}'" -f $ArgusRoot)
    '$Host.UI.RawUI.WindowTitle = ''Argus AI API (:8000)'''
    ("python -m api --host 127.0.0.1 --port 8000 2>&1 | Tee-Object -FilePath '{0}'" -f $ApiLog)
)
$apiLines | Set-Content -LiteralPath $ApiScript -Encoding ASCII

Start-DemoWindow -Title "Python API (:8000)" -ScriptPath $ApiScript

if (Test-Path -LiteralPath $KitBat) {
    # Keep a visible console (/k style via -NoExit). Old Start-Process cmd /c
    # flashed closed, so Kit looked like it never started even when it did.
    $kitLines = @(
        ("Set-Location -LiteralPath '{0}'" -f $KitRoot)
        '$Host.UI.RawUI.WindowTitle = ''Argus AI Kit Streaming (headless)'''
        'Write-Host "Starting launch_urbantwin_streaming.bat ..."'
        'Write-Host "This is headless (--no-window). No Omniverse editor UI will appear."'
        'Write-Host "Wait until this window shows Kit ready / livestream, then check the dashboard Live chip."'
        'Write-Host ""'
        ("cmd.exe /c `"launch_urbantwin_streaming.bat`" 2>&1 | Tee-Object -FilePath '{0}'" -f $KitLog)
        'Write-Host ""'
        'Write-Host "Kit process exited. If the stream never came online, scroll up or open:"'
        ("Write-Host '  {0}'" -f $KitLog)
    )
    $kitLines | Set-Content -LiteralPath $KitScript -Encoding ASCII
    Start-DemoWindow -Title "Kit streaming" -ScriptPath $KitScript
    Write-Host "Started Kit streaming in a visible console (headless render)."
} else {
    Write-Warning ("Kit launcher not found at {0} - start Kit manually for stream online." -f $KitBat)
}

$feLines = @(
    ("Set-Location -LiteralPath '{0}'" -f $FrontendDir)
    '$env:URBANTWIN_API_BASE = ''http://127.0.0.1:8000'''
    '$Host.UI.RawUI.WindowTitle = ''Argus AI Dashboard'''
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

Write-Host "Waiting for Kit signaling on port 49100 (up to 120s)..."
if (Wait-TcpPort -Port 49100 -MaxSeconds 120) {
    Write-Host "  Kit signaling port is open."
} else {
    Write-Warning "Kit signaling port 49100 never opened."
    Write-Warning ("Check the 'Argus AI Kit Streaming' window and {0}" -f $KitLog)
    Write-Warning "You can still use the dashboard; the viewport will stay offline until Kit is up."
}

Write-Host "Waiting for stream config..."
$stream = Wait-HttpJson -Url "http://127.0.0.1:8000/api/stream/config" -MaxSeconds 30
if ($stream) {
    Write-Host ("  stream status: {0}" -f $stream.status)
} else {
    Write-Warning "Stream config not reachable yet."
}

Write-Host "Waiting for dashboard (up to 60s)..."
$dashboard = $null
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    $dashboard = Resolve-DashboardUrl
    try {
        $null = Invoke-WebRequest -Uri $dashboard -UseBasicParsing -TimeoutSec 3
        break
    } catch {
        Start-Sleep -Seconds 2
        $dashboard = $null
    }
}
if (-not $dashboard) {
    $dashboard = "http://127.0.0.1:3000"
    Write-Warning ("Dashboard not responding yet - open {0} when npm finishes." -f $dashboard)
}

Write-Host ""
Write-Host "Ready URLs:"
Write-Host ("  Dashboard:  {0}" -f $dashboard)
Write-Host "  API health: http://127.0.0.1:8000/api/health"
Write-Host "  Stream cfg: http://127.0.0.1:8000/api/stream/config"
Write-Host "  Kit signal: tcp://127.0.0.1:49100 (headless streaming host)"
Write-Host ""
Write-Host "Omniverse tip: there is no editor window. Use Chrome/Edge; wait for viewport = Live."
Write-Host "Smoke test:  python tools\demo_smoke.py"
Write-Host "Runbook:     docs\DEMO_RUNBOOK.md"
Write-Host ("API log:     {0}" -f $ApiLog)
Write-Host ("Kit log:     {0}" -f $KitLog)
Write-Host ("Frontend log: {0}" -f $FrontendLog)

if (-not $NoBrowser) {
    try {
        Start-Process $dashboard | Out-Null
        Write-Host ""
        Write-Host ("Opened browser: {0}" -f $dashboard)
        Write-Host "Use Chrome or Edge for the Omniverse stream."
    } catch {
        Write-Warning "Could not open a browser automatically."
    }
}
