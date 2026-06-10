$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$Version = "1.1.3"
$VenvDir = if ($env:WHISPER_RELEASE_VENV) { $env:WHISPER_RELEASE_VENV } else { ".release-venv" }
$TorchFlavor = if ($env:WHISPER_RELEASE_TORCH) { $env:WHISPER_RELEASE_TORCH.ToLowerInvariant() } else { "cpu" }
if ($TorchFlavor -notin @("cpu", "cuda")) {
    throw "Unsupported WHISPER_RELEASE_TORCH value: $TorchFlavor. Use 'cpu' or 'cuda'."
}
$PackageSuffix = if ($TorchFlavor -eq "cuda") { "-CUDA" } else { "" }
$ReleaseDir = Join-Path $ProjectRoot "release"
$DistApp = Join-Path $ProjectRoot "dist\WhisperBatchTranscriber"
$ZipPath = Join-Path $ReleaseDir "WhisperBatchTranscriber-$Version-Windows$PackageSuffix-x64.zip"

Write-Warning "This builds the legacy Tk/PyInstaller app. The official product target is the Electron app under desktop/."
Write-Warning "Do not attach these artifacts to a new official GitHub Release unless it is explicitly marked as legacy."

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

$ExistingTorchFlavor = & $VenvPython -c "import torch; print('cuda' if torch.version.cuda else 'cpu')" 2>$null
if ($LASTEXITCODE -ne 0) {
    $ExistingTorchFlavor = "missing"
}

if ($ExistingTorchFlavor -ne $TorchFlavor) {
    Write-Host "Installing PyTorch flavor: $TorchFlavor (current: $ExistingTorchFlavor)"
    if ($TorchFlavor -eq "cuda") {
        & $VenvPython -m pip install --upgrade --force-reinstall torch --index-url https://download.pytorch.org/whl/cu126
    } else {
        & $VenvPython -m pip install --upgrade --force-reinstall torch --index-url https://download.pytorch.org/whl/cpu
    }
} else {
    Write-Host "PyTorch flavor already matches: $TorchFlavor"
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
    if ($TorchFlavor -eq "cuda") {
        $DefaultSetup = Join-Path $ReleaseDir "WhisperBatchTranscriber-$Version-Windows-Setup.exe"
        $CudaSetup = Join-Path $ReleaseDir "WhisperBatchTranscriber-$Version-Windows-CUDA-Setup.exe"
        if (Test-Path $CudaSetup) {
            Remove-Item -LiteralPath $CudaSetup -Force
        }
        if (Test-Path $DefaultSetup) {
            Move-Item -LiteralPath $DefaultSetup -Destination $CudaSetup
        }
    }
} else {
    Write-Host "Inno Setup not found. ZIP package was created; installer EXE was skipped."
    Write-Host "Install Inno Setup from https://jrsoftware.org/isinfo.php to build the setup EXE."
}

Write-Host "Release files are in: $ReleaseDir"
