param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8765,
    [string]$PidFile = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot
if (-not $PidFile) {
    $PidFile = Join-Path $ProjectRoot "runtime\falcon-web.pid"
}

function Stop-FalconPid {
    param([int]$ProcessId)

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $process) {
        return $false
    }
    Write-Host "Stopping Falcon web process $ProcessId"
    Stop-Process -Id $ProcessId -ErrorAction SilentlyContinue
    try {
        Wait-Process -Id $ProcessId -Timeout 6 -ErrorAction Stop
    }
    catch {
        $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "Falcon web process $ProcessId did not exit; forcing stop"
            Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    return $true
}

$Stopped = $false
if (Test-Path $PidFile) {
    $PidText = (Get-Content $PidFile -Raw).Trim()
    if ($PidText -match '^\d+$') {
        $Stopped = Stop-FalconPid -ProcessId ([int]$PidText)
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

$connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
foreach ($connection in $connections) {
    $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
    if (-not $process) {
        continue
    }
    $commandLine = ""
    try {
        $commandLine = (Get-CimInstance Win32_Process -Filter "ProcessId=$($process.Id)").CommandLine
    }
    catch {
        $commandLine = ""
    }
    if (($commandLine -match "falcon") -and ($commandLine -match "web")) {
        if (Stop-FalconPid -ProcessId $process.Id) {
            $Stopped = $true
        }
    }
}

if ($Stopped) {
    Write-Host "Falcon web stopped."
}
else {
    Write-Host "No Falcon web process found on ${HostAddress}:$Port"
}
