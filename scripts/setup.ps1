<#
.SYNOPSIS
    Prepare the local Whisper GPU transcription environment for this workspace (optional; transcribe_faster.py auto-discovers CUDA DLLs).
    Load this file in  PowerShell 5.1 and call New-BilinoteTranscriptEnv,
    or run the individual steps below directly.

.DESCRIPTION
    Applies the traps discovered while bootstrapping this workspace:
      - Python 3.13 interpreter (C:\Python313\python.exe) is used because the
        shared wheels under output\_shared\python-packages are cp3.13 builds.
      - The GPU build of ctranslate2 needs CUDA runtime DLLs (cublas64_12.dll
        etc.) that ship inside torch. The torch\lib directory is prepended to
        PATH so those DLLs resolve at runtime.
      - PYTHONPATH is pointed at the shared packages so the interpreter picks
        up yt-dlp / faster-whisper / ctranslate2 without a pip install.
      - In the examples below, <skill-dir> is where this skill is installed:
        the project path .opencode\skills\bilibili-render-md, or a global /
        independent checkout.
.EXAMPLE
    # Scenario A: Bilibili URL — init_job downloads the video first
    python scripts/init_job.py --bvid BVxxx --part 5
    & "C:\Python313\python.exe" "<skill-dir>\scripts\transcribe_faster.py" `
        ".\source\media\BVxxx_P5.mp4" --workspace "." --output-dir ".\work\transcript" `
        --model small.en --device cpu --language zh --force

    # Scenario B: Local video file — skip download
    python scripts/init_job.py --video-path "C:\videos\myvideo.mp4" --title "My Video"
    & "C:\Python313\python.exe" "<skill-dir>\scripts\transcribe_faster.py" `
        ".\source\media\myvideo_FULL.mp4" --workspace "." --output-dir ".\work\transcript" `
        --model base --device cpu --language zh --force
#>

function New-BilinoteTranscriptEnv {
    param(
        [string]$Workspace = (Get-Location),
        [string]$Python = "C:\Python313\python.exe",
        [string]$TorchLib = "$env:USERPROFILE\miniconda3\envs\video-doc\Lib\site-packages\torch\lib"
    )

    $shared = Join-Path $Workspace "output\_shared\python-packages"
    if (-not (Test-Path -LiteralPath $shared)) {
        throw "shared packages not found: $shared"
    }
    if (-not (Test-Path -LiteralPath $Python)) {
        throw "python3.13 interpreter not found: $Python"
    }

    # ctranslate2 GPU needs cublas64_12.dll etc. from torch\lib.
    if (Test-Path -LiteralPath $TorchLib) {
        $env:PATH = $TorchLib + ";" + $env:PATH
        Write-Host "[setup] PATH += $TorchLib"
    } else {
        Write-Warning "[setup] torch\lib not found at $TorchLib — cuda transcription may fail"
    }

    $env:PYTHONPATH = $shared
    Write-Host "[setup] PYTHONPATH = $shared"
    Write-Host "[setup] python     = $Python"
    Write-Host '[setup] next: run transcribe_faster.py with the same interpreter returned above'

    return @{ Python = $Python }
}