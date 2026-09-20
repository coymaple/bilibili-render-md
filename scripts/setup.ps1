<#
.SYNOPSIS
    Prepare the local Whisper GPU transcription environment (optional; transcribe_faster.py auto-discovers CUDA DLLs).
    Load this file in  PowerShell 5.1 and call New-BilinoteTranscriptEnv,
    or run the individual steps below directly.

.DESCRIPTION
    Applies the environment traps this skill relies on:
      - A Python 3.13 interpreter is used because the shared wheels under
        output\_shared\python-packages are cp3.13 builds; pass its path via -Python.
      - The GPU build of ctranslate2 needs CUDA runtime DLLs (cublas64_12.dll
        etc.) that ship inside torch. The torch\lib directory is prepended to
        PATH so those DLLs resolve at runtime.
      - PYTHONPATH is pointed at the shared packages so the interpreter picks
        up yt-dlp / faster-whisper / ctranslate2 without a pip install.
      - In the examples below, <skill-dir> is where this skill is installed:
        the project path .opencode\skills\bilibili-render-md, or a global /
        independent checkout.
.EXAMPLE
    # Scenario A: Bilibili URL - init_job downloads the video first
    python scripts/init_job.py --bvid BVxxx --part 5
    & "<python>" "<skill-dir>\scripts\transcribe_faster.py" `
        ".\source\media\BVxxx_P5.mp4" --workspace "." --output-dir ".\work\transcript" `
        --model small.en --device cpu --language zh --force

    # Scenario B: Local video file - skip download
    python scripts/init_job.py --video-path "<path-to-video>" --title "My Video"
    & "<python>" "<skill-dir>\scripts\transcribe_faster.py" `
        ".\source\media\myvideo_FULL.mp4" --workspace "." --output-dir ".\work\transcript" `
        --model base --device cpu --language zh --force
#>

function New-BilinoteTranscriptEnv {
    param(
        [string]$Workspace = (Get-Location),
        [string]$Python = "",
        [string]$TorchLib = ""
    )

    $shared = Join-Path $Workspace "output\_shared\python-packages"
    if (-not (Test-Path -LiteralPath $shared)) {
        throw "shared packages not found: $shared"
    }
    if ([string]::IsNullOrWhiteSpace($Python)) {
        throw "Specify -Python with an interpreter that already has faster-whisper (see references/whisper.md)"
    }
    if (-not (Test-Path -LiteralPath $Python)) {
        throw "python interpreter not found: $Python"
    }

    # ctranslate2 GPU needs cublas64_12.dll etc. from torch\lib.
    if ([string]::IsNullOrWhiteSpace($TorchLib)) {
        Write-Warning "[setup] -TorchLib not set; point it to torch\lib if GPU transcription reports a missing cublas64_12.dll"
    } elseif (Test-Path -LiteralPath $TorchLib) {
        $env:PATH = $TorchLib + ";" + $env:PATH
        Write-Host "[setup] PATH += $TorchLib"
    } else {
        Write-Warning "[setup] torch\lib not found at $TorchLib - cuda transcription may fail"
    }

    $env:PYTHONPATH = $shared
    Write-Host "[setup] PYTHONPATH = $shared"
    Write-Host "[setup] python     = $Python"
    Write-Host '[setup] next: run transcribe_faster.py with the same interpreter returned above'

    return @{ Python = $Python }
}