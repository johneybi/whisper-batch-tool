$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$Version = "1.1.0"
$ZipPath = Join-Path $ProjectRoot "release\WhisperBatchTranscriber-$Version-Windows-x64.zip"

if (-not (Test-Path $ZipPath)) {
    throw "Release ZIP not found: $ZipPath"
}

$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("WhisperBatchTranscriber-verify-" + [Guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null

try {
    Expand-Archive -Path $ZipPath -DestinationPath $TempRoot -Force
    $Exe = Join-Path $TempRoot "WhisperBatchTranscriber.exe"
    if (-not (Test-Path $Exe)) {
        throw "Executable not found after extracting release ZIP."
    }

    $BundledFfmpeg = Get-ChildItem -Path $TempRoot -Recurse -Filter "ffmpeg*.exe" | Select-Object -First 1
    if (-not $BundledFfmpeg) {
        throw "Bundled ffmpeg executable was not found in the release ZIP."
    }

    $OldPath = $env:PATH
    try {
        $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem"
        $Process = Start-Process -FilePath $Exe -ArgumentList "--self-test" -Wait -PassThru -WindowStyle Hidden
        if ($Process.ExitCode -ne 0) {
            throw "Release self-test failed with exit code $($Process.ExitCode)."
        }
    } finally {
        $env:PATH = $OldPath
    }

    Write-Host "Release ZIP verified: $ZipPath"
    Write-Host "Bundled ffmpeg: $($BundledFfmpeg.FullName)"
} finally {
    if (Test-Path $TempRoot) {
        Remove-Item -LiteralPath $TempRoot -Recurse -Force
    }
}
