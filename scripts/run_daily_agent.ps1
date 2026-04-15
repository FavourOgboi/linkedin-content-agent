[CmdletBinding()]
param(
    [string]$Day,
    [string]$Topic,
    [switch]$SkipEmail
)

$ErrorActionPreference = "Stop"

function Resolve-PythonInvocation {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $candidates = @(
        @{
            Executable = Join-Path $RepoRoot ".venv\Scripts\python.exe"
            Prefix = @()
        },
        @{
            Executable = Join-Path $RepoRoot "venv\Scripts\python.exe"
            Prefix = @()
        }
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate.Executable) {
            return $candidate
        }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{
            Executable = $py.Source
            Prefix = @("-3")
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{
            Executable = $python.Source
            Prefix = @()
        }
    }

    throw "No Python executable was found. Install Python 3.11+ or create a local .venv first."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$logDir = Join-Path $repoRoot "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logPath = Join-Path $logDir "$timestamp-task-run.log"
$python = Resolve-PythonInvocation -RepoRoot $repoRoot

$arguments = @()
$arguments += $python.Prefix
$arguments += "-m", "linkedin_content_agent.cli", "run"
if ($Day) {
    $arguments += "--day", $Day
}
if ($Topic) {
    $arguments += "--topic", $Topic
}
if ($SkipEmail) {
    $arguments += "--skip-email"
}

$originalPythonPath = $env:PYTHONPATH
if ([string]::IsNullOrWhiteSpace($originalPythonPath)) {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
} else {
    $env:PYTHONPATH = "{0};{1}" -f (Join-Path $repoRoot "src"), $originalPythonPath
}

Push-Location $repoRoot
try {
    @(
        "LinkedIn Content Agent daily run"
        "Started: $(Get-Date -Format s)"
        "Repo root: $repoRoot"
        "Python: $($python.Executable)"
        "Arguments: $($arguments -join ' ')"
        "Log file: $logPath"
        ""
    ) | Tee-Object -FilePath $logPath -Append

    & $python.Executable @arguments 2>&1 | Tee-Object -FilePath $logPath -Append
    $exitCode = if ($null -ne $LASTEXITCODE) { $LASTEXITCODE } else { 0 }

    @(
        ""
        "Finished: $(Get-Date -Format s)"
        "Exit code: $exitCode"
    ) | Tee-Object -FilePath $logPath -Append

    exit $exitCode
}
finally {
    Pop-Location
    $env:PYTHONPATH = $originalPythonPath
}
