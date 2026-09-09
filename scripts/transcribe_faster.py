#!/usr/bin/env python3
"""Transcribe media with a shared local faster-whisper model."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def ensure_cuda_path(workspace: Path) -> None:
    if os.name != "nt":
        return
    try:
        import torch
    except ImportError:
        return
    torch_lib = Path(torch.__file__).parent / "lib"
    if not torch_lib.is_dir():
        return
    torch_path = str(torch_lib)
    current_path = os.environ.get("PATH", "")
    if torch_path not in current_path.split(os.pathsep):
        os.environ["PATH"] = torch_path + os.pathsep + current_path


def timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, nargs="?", default=None)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--stem", default="transcript")
    parser.add_argument("--model", default="small")
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--language")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--list-models", action="store_true", help="List available local models and exit")
    args = parser.parse_args()

    if args.list_models:
        workspace = args.workspace.expanduser().resolve()
        manifest_path = workspace / "output" / "_models" / "manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            models = manifest.get("models", {})
            for name, info in sorted(models.items()):
                print(f"  {name}: {info['path']} ({info.get('type', '?')})")
        else:
            print("  No manifest.json found. Checking raw directories...")
            models_dir = workspace / "output" / "_models"
            if models_dir.is_dir():
                for d in sorted(models_dir.iterdir()):
                    if d.is_dir() and d.name.startswith("faster-whisper-"):
                        model_name = d.name.replace("faster-whisper-", "")
                        print(f"  {model_name}: {d}")
        return 0

    if args.input is None or args.output_dir is None:
        parser.error("--input and --output-dir are required unless --list-models is used")

    workspace = args.workspace.expanduser().resolve()
    package_roots: list[Path] = []
    configured_packages = os.environ.get("BILIBILI_RENDER_MD_PYTHONPATH")
    if configured_packages:
        package_roots.append(Path(configured_packages).expanduser().resolve())
    package_roots.append(workspace / "output" / "_shared" / "python-packages")
    for package_root in reversed(package_roots):
        if package_root.is_dir():
            sys.path.insert(0, str(package_root))

    ensure_cuda_path(workspace)

    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise SystemExit(
            "faster-whisper is not installed in the active Python environment or "
            "the configured shared package directory"
        ) from error

    media_path = args.input.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not media_path.is_file():
        raise FileNotFoundError(f"input media not found: {media_path}")

    model_roots: list[Path] = []
    configured_root = os.environ.get("FASTER_WHISPER_MODEL_ROOT")
    if configured_root:
        model_roots.append(Path(configured_root).expanduser().resolve())
    model_roots.append(workspace / "output" / "_models")

    if args.model_path:
        model_source: str | Path = args.model_path.expanduser().resolve()
    else:
        candidates = [root / f"faster-whisper-{args.model}" for root in model_roots]
        model_source = next((path for path in candidates if path.is_dir()), args.model)

    if isinstance(model_source, Path) and not model_source.is_dir():
        raise FileNotFoundError(f"local model directory not found: {model_source}")
    if isinstance(model_source, str) and not args.allow_download:
        expected = ", ".join(str(path) for path in candidates)
        raise FileNotFoundError(
            f"local model not found; checked {expected}; pass --model-path, set "
            "FASTER_WHISPER_MODEL_ROOT, or explicitly allow download"
        )

    srt_path = output_dir / f"{args.stem}.srt"
    metadata_path = output_dir / f"{args.stem}.meta.json"
    if not args.force and (srt_path.exists() or metadata_path.exists()):
        raise FileExistsError("output exists; pass --force to replace it")

    cache_root = workspace / "output" / "_models" / "_cache"
    ensure_cuda_path(workspace)
    model = WhisperModel(
        str(model_source),
        device=args.device,
        compute_type=args.compute_type,
        cpu_threads=max(1, (os.cpu_count() or 4) - 2),
        num_workers=1,
        download_root=str(cache_root) if args.allow_download else None,
    )
    segments, info = model.transcribe(
        str(media_path),
        language=args.language,
        beam_size=args.beam_size,
        vad_filter=True,
        initial_prompt=args.prompt,
        condition_on_previous_text=True,
    )

    count = 0
    with srt_path.open("w", encoding="utf-8") as output:
        for count, segment in enumerate(segments, start=1):
            text = segment.text.strip()
            output.write(
                f"{count}\n{timestamp(segment.start)} --> {timestamp(segment.end)}\n{text}\n\n"
            )

    metadata = {
        "input": str(media_path),
        "model": str(model_source),
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "segments": count,
        "srt": str(srt_path),
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
