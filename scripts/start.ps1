$ErrorActionPreference = "Stop"
$BootstrapArgs = @($args)

function Test-FalconPython {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [string[]]$CommandArgs = @()
    )

    try {
        $versionOutput = & $Command @($CommandArgs + @("--version")) 2>&1
        return ($LASTEXITCODE -eq 0 -and (($versionOutput -join "`n") -match "Python 3\."))
    }
    catch {
        return $false
    }
}

function Resolve-FalconPython {
    $candidates = @()

    if ($env:FALCON_PYTHON) {
        $candidates += [pscustomobject]@{ Command = $env:FALCON_PYTHON; Args = @() }
    }

    $candidates += [pscustomobject]@{ Command = "py"; Args = @("-3") }
    $candidates += [pscustomobject]@{ Command = "python"; Args = @() }
    $candidates += [pscustomobject]@{ Command = "python3"; Args = @() }

    $codexPython = Join-Path $HOME ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $codexPython) {
        $candidates += [pscustomobject]@{ Command = $codexPython; Args = @() }
    }

    foreach ($candidate in $candidates) {
        if (Test-FalconPython -Command $candidate.Command -CommandArgs $candidate.Args) {
            return $candidate
        }
    }

    throw "Falcon startup needs Python 3.9 or newer. Install Python, make py/python available on PATH, or set FALCON_PYTHON to a python.exe path."
}

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot
$Python = Resolve-FalconPython
& $Python.Command @($Python.Args + @("scripts\falcon_bootstrap.py") + $BootstrapArgs)
