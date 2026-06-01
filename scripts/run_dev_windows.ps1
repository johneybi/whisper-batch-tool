param(
    [string]$Python = "",
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$candidates = @()
if ($Python) {
    $candidates += $Python
}
$candidates += @(
    (Join-Path $ProjectRoot ".release-venv\Scripts\python.exe"),
    (Join-Path $ProjectRoot "venv\Scripts\python.exe"),
    "C:\whisper\torch-env\Scripts\python.exe",
    "python"
)

$pythonExe = $null
foreach ($candidate in $candidates) {
    if ($candidate -eq "python") {
        $resolved = Get-Command python -ErrorAction SilentlyContinue
        if ($resolved) {
            $pythonExe = $resolved.Source
            break
        }
    } elseif (Test-Path $candidate) {
        $pythonExe = (Resolve-Path $candidate).Path
        break
    }
}

if (-not $pythonExe) {
    throw "Python was not found. Run install_gui.bat first, or pass -Python C:\path\to\python.exe."
}

$logDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir ("dev-run-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

Write-Host "Project: $ProjectRoot"
Write-Host "Python:  $pythonExe"
Write-Host "Log:     $logPath"

$quotedPython = '"' + $pythonExe.Replace('"', '\"') + '"'

if ($SelfTest) {
    $cmdLine = "$quotedPython `".\whisper_gui.py`" --self-test > `"$logPath`" 2>&1"
    & cmd.exe /d /c $cmdLine
} else {
    # Run through cmd so native stderr is merged before PowerShell sees it.
    # Windows PowerShell otherwise wraps harmless stderr output as NativeCommandError.
    $cmdLine = "$quotedPython `".\whisper_gui.py`" 2>&1"
    & cmd.exe /d /c $cmdLine | Tee-Object -FilePath $logPath
}

exit $LASTEXITCODE
