#!/usr/bin/env python3
"""Extract coarse or timestamp-targeted teaching frames with FFmpeg."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


TIME = re.compile(r"^(?:(\d+):)?([0-5]?\d):([0-5]?\d(?:\.\d+)?)$")


def parse_timestamp(value: str) -> float:
    value = value.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return float(value)
    match = TIME.fullmatch(value)
    if not match:
        raise ValueError(f"invalid timestamp: {value}")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def timestamp_name(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}-{minutes:02d}-{secs:02d}-{millis:03d}"


def run(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        raise RuntimeError(f"ffmpeg failed: {detail}") from error


def probe_duration(media: Path) -> float:
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe was not found on PATH")
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(media),
    ]
    try:
        completed = subprocess.run(
            command, check=True, capture_output=True, text=True
        )
        return float(completed.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        raise RuntimeError(f"ffprobe failed to read duration: {detail}") from error


def scale_filter(width: int) -> str:
    return f"scale='min({width},iw)':-2"


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract video frames with FFmpeg")
    parser.add_argument("media", type=Path)
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("coarse", "targeted"), required=True)
    parser.add_argument(
        "--timestamps",
        help="Comma-separated seconds or MM:SS/HH:MM:SS values for targeted mode",
    )
    parser.add_argument("--interval", type=float, default=120.0)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg was not found on PATH")
    if args.interval <= 0 or args.width <= 0:
        raise ValueError("--interval and --width must be positive")
    if args.mode == "targeted" and not args.timestamps:
        raise ValueError("--timestamps is required in targeted mode")

    media = args.media.expanduser().resolve()
    if not media.is_file():
        raise FileNotFoundError(f"media not found: {media}")
    job_root = args.job_root.expanduser().resolve()
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else job_root / "work" / "frames" / args.mode
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    overwrite = "-y" if args.force else "-n"
    outputs: list[dict[str, object]] = []

    if args.mode == "coarse":
        duration = probe_duration(media)
        timestamps = []
        current = 0.0
        while current < duration:
            timestamps.append(current)
            current += args.interval
    else:
        timestamps = sorted(
            set(parse_timestamp(value) for value in args.timestamps.split(","))
        )

    for seconds in timestamps:
        path = output_dir / f"frame_{timestamp_name(seconds)}.jpg"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            overwrite,
            "-ss",
            f"{seconds:.3f}",
            "-i",
            str(media),
            "-frames:v",
            "1",
            "-vf",
            scale_filter(args.width),
            "-q:v",
            "2",
            str(path),
        ]
        run(command)
        outputs.append({"path": str(path), "timestamp_seconds": round(seconds, 3)})

    manifest = {
        "media": str(media),
        "mode": args.mode,
        "interval_seconds": args.interval if args.mode == "coarse" else None,
        "frames": outputs,
    }
    manifest_path = output_dir / "frames.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"frame_count": len(outputs), "manifest": str(manifest_path)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
