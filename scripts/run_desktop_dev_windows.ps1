param(
    [switch]$Install,
    [switch]$Preview
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DesktopDir = Join-Path $ProjectRoot "desktop"

if (-not (Test-Path (Join-Path $DesktopDir "package.json"))) {
    throw "Desktop package.json was not found at $DesktopDir."
}

$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
}

if (-not $npmCommand) {
    throw "npm was not found. Install Node.js first, then try again."
}

Set-Location $DesktopDir

Write-Host "Project: $ProjectRoot"
Write-Host "Desktop: $DesktopDir"
Write-Host "npm:     $($npmCommand.Source)"

$pythonCandidates = @(
    $(if ($env:WHISPER_CUDA_PYTHON) { $env:WHISPER_CUDA_PYTHON } else { "C:\whisper\torch-env\Scripts\python.exe" }),
    (Join-Path $ProjectRoot ".release-venv\Scripts\python.exe"),
    (Join-Path $ProjectRoot "venv\Scripts\python.exe")
)

foreach ($candidate in $pythonCandidates) {
    if (Test-Path $candidate) {
        $env:WHISPER_PYTHON = (Resolve-Path $candidate).Path
        break
    }
}

if ($env:WHISPER_PYTHON) {
    Write-Host "Python:  $env:WHISPER_PYTHON"
} else {
    Write-Host "Python:  default python on PATH"
}

if ($Install -or -not (Test-Path (Join-Path $DesktopDir "node_modules"))) {
    Write-Host "Installing desktop dependencies..."
    & $npmCommand.Source install
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

if ($Preview) {
    Write-Host "Starting built desktop preview..."
    Write-Host "Preview runs in a browser only. Electron-only features such as file dialogs, drag file paths, and transcription IPC are unavailable."
    & $npmCommand.Source run preview
} else {
    Write-Host "Starting Electron desktop dev app..."
    & $npmCommand.Source run dev
}

exit $LASTEXITCODE
