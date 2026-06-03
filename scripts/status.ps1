param(
    [Alias("host")]
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
$UrlFile = Join-Path $ProjectRoot "runtime\falcon-web.url"
$LogFile = Join-Path $ProjectRoot "runtime\falcon-web.log"

$Url = "http://${HostAddress}:$Port"
if (Test-Path $UrlFile) {
    $UrlText = (Get-Content $UrlFile -Raw).Trim()
    if ($UrlText) {
        $Url = $UrlText
    }
}

$ProcessIdFromFile = ""
$PidRunning = $false
if (Test-Path $PidFile) {
    $ProcessIdFromFile = (Get-Content $PidFile -Raw).Trim()
    if ($ProcessIdFromFile -match '^\d+$') {
        $PidRunning = [bool](Get-Process -Id ([int]$ProcessIdFromFile) -ErrorAction SilentlyContinue)
    }
}

$ListeningPids = @()
try {
    $ListeningPids = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
}
catch {
    $ListeningPids = @()
}

$HttpStatus = ""
try {
    $Response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
    $HttpStatus = [int]$Response.StatusCode
}
catch {
    if ($_.Exception.Response) {
        $HttpStatus = [int]$_.Exception.Response.StatusCode
    }
}

Write-Host "Falcon web status"
Write-Host "- URL: $Url"
Write-Host "- PID file: $PidFile"
if ($ProcessIdFromFile) {
    if ($PidRunning) {
        Write-Host "- PID: $ProcessIdFromFile running"
    }
    else {
        Write-Host "- PID: $ProcessIdFromFile not running"
    }
}
else {
    Write-Host "- PID: none"
}
if ($ListeningPids.Count -gt 0) {
    Write-Host "- Listening on port ${Port}: $($ListeningPids -join ' ')"
}
else {
    Write-Host "- Listening on port ${Port}: no"
}
if ($HttpStatus) {
    Write-Host "- HTTP: $HttpStatus"
}
else {
    Write-Host "- HTTP: no response"
}
Write-Host "- Log: $LogFile"

if ($HttpStatus -ge 200 -and $HttpStatus -lt 400) {
    exit 0
}
exit 1
