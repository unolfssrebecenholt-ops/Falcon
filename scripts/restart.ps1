$ErrorActionPreference = "Stop"
$RestartArgs = @($args)

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

& (Join-Path $PSScriptRoot "stop.ps1")
& (Join-Path $PSScriptRoot "start.ps1") @("--skip-install") @($RestartArgs)
