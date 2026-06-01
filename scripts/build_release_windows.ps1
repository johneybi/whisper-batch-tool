$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$Version = "1.1.3"
$VenvDir = if ($env:WHISPER_RELEASE_VENV) { $env:WHISPER_RELEASE_VENV } else { ".release-venv" }
$TorchFlavor = if ($env:WHISPER_RELEASE_TORCH) { $env:WHISPER_RELEASE_TORCH } else { "cpu" }
$ReleaseDir = Join-Path $ProjectRoot "release"
$DistApp = Join-Path $ProjectRoot "dist\WhisperBatchTranscriber"
$ZipPath = Join-Path $ReleaseDir "WhisperBatchTranscriber-$Version-Windows-x64.zip"

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

if ($env:WHISPER_CLEAN_RELEASE_VENV -eq "1" -and (Test-Path $VenvDir)) {
    Remove-Item -LiteralPath $VenvDir -Recurse -Force
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPyinstaller = Join-Path $VenvDir "Scripts\pyinstaller.exe"

if (-not (Test-Path $VenvPython)) {
    $Python = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($Python) {
        & $Python.Source -3.11 -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) {
            & $Python.Source -3 -m venv $VenvDir
        }
    } else {
        python -m venv $VenvDir
    }
}

& $VenvPython -m pip install --upgrade pip

if ($TorchFlavor -eq "cuda") {
    & $VenvPython -m pip install torch --index-url https://download.pytorch.org/whl/cu126
} else {
    & $VenvPython -m pip install torch --index-url https://download.pytorch.org/whl/cpu
}

& $VenvPython -m pip install -r requirements.txt pyinstaller
& $VenvPyinstaller --clean --noconfirm WhisperBatchTranscriber.spec

if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $DistApp "*") -DestinationPath $ZipPath

$Iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
$IsccPath = if ($Iscc) { $Iscc.Source } else { $null }

if (-not $IsccPath) {
    $DefaultIsccPaths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($Candidate in $DefaultIsccPaths) {
        if ($Candidate -and (Test-Path $Candidate)) {
            $IsccPath = $Candidate
            break
        }
    }
}

if ($IsccPath) {
    & $IsccPath "packaging\windows_installer.iss"
} else {
    Write-Host "Inno Setup not found. ZIP package was created; installer EXE was skipped."
    Write-Host "Install Inno Setup from https://jrsoftware.org/isinfo.php to build the setup EXE."
}

Write-Host "Release files are in: $ReleaseDir"
