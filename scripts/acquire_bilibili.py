#!/usr/bin/env python3
"""Inspect or download one explicitly selected Bilibili video part with yt-dlp."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


BVID = re.compile(r"^BV[0-9A-Za-z]+$")


def source_url(value: str) -> str:
    value = value.strip()
    if BVID.fullmatch(value):
        return f"https://www.bilibili.com/video/{value}"
    if value.startswith(("https://www.bilibili.com/", "https://b23.tv/")):
        return value
    raise ValueError("source must be a BVID or a bilibili.com/b23.tv URL")


def ytdlp_base() -> list[str]:
    return [sys.executable, "-m", "yt_dlp"]


def run_ytdlp(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [*ytdlp_base(), *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "").strip()
        raise RuntimeError(f"yt-dlp failed: {detail}") from error


def compact_metadata(data: dict[str, Any]) -> dict[str, Any]:
    entries = data.get("entries") or []
    parts = [
        {
            "index": item.get("playlist_index") or index,
            "id": item.get("id"),
            "title": item.get("title"),
            "duration": item.get("duration"),
        }
        for index, item in enumerate(entries, start=1)
        if isinstance(item, dict)
    ]
    subtitle_names = set(data.get("subtitles", {})) | set(
        data.get("automatic_captions", {})
    )
    for item in entries:
        if isinstance(item, dict):
            subtitle_names.update(item.get("subtitles", {}))
            subtitle_names.update(item.get("automatic_captions", {}))
    formats = [
        {
            "format_id": item.get("format_id"),
            "ext": item.get("ext"),
            "resolution": item.get("resolution"),
            "height": item.get("height"),
            "fps": item.get("fps"),
            "vcodec": item.get("vcodec"),
            "acodec": item.get("acodec"),
            "filesize": item.get("filesize") or item.get("filesize_approx"),
        }
        for item in data.get("formats", [])
        if isinstance(item, dict)
    ]
    return {
        "id": data.get("id"),
        "bvid": data.get("bvid") or data.get("id"),
        "title": data.get("title"),
        "duration": data.get("duration"),
        "webpage_url": data.get("webpage_url") or data.get("original_url"),
        "thumbnail": data.get("thumbnail"),
        "subtitles": sorted(subtitle_names),
        "formats": formats,
        "parts": parts,
    }


def inspect(source: str, part: int | None) -> tuple[dict[str, Any], list[str]]:
    arguments = ["--dump-single-json", "--skip-download", "--no-warnings"]
    if part is not None:
        arguments.extend(["--playlist-items", str(part)])
    arguments.append(source)
    completed = run_ytdlp(arguments)
    return json.loads(completed.stdout), arguments


def download(
    source: str, part: int | None, media_dir: Path, force: bool
) -> tuple[list[str], str]:
    output_template = str(media_dir / "%(id)s_P%(playlist_index|1)s.%(ext)s")
    arguments = [
        "--format",
        "bestvideo*+bestaudio/best",
        "--merge-output-format",
        "mp4",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        "zh-Hans,zh-Hant,zh-CN,zh,en",
        "--convert-subs",
        "srt",
        "--print",
        "after_move:filepath",
        "--force-overwrites" if force else "--no-overwrites",
        "--output",
        output_template,
    ]
    if part is not None:
        arguments.extend(["--playlist-items", str(part)])
    arguments.append(source)
    completed = run_ytdlp(arguments)
    paths = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return arguments, paths[-1] if paths else ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect Bilibili metadata and optionally download an approved part"
    )
    parser.add_argument("source", help="BVID or Bilibili URL")
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--part", type=int)
    parser.add_argument("--download", action="store_true")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Explicitly authorize downloading all parts when used with --download",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.part is not None and args.part <= 0:
        raise ValueError("--part must be positive")
    if args.download and args.part is None and not args.full:
        raise ValueError("downloading requires --part or explicit --full authorization")
    if args.part is not None and args.full:
        raise ValueError("--part and --full are mutually exclusive")

    job_root = args.job_root.expanduser().resolve()
    metadata_dir = job_root / "source" / "metadata"
    media_dir = job_root / "source" / "media"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)
    source = source_url(args.source)

    raw, inspect_arguments = inspect(source, args.part)
    raw_path = metadata_dir / "yt-dlp.raw.json"
    compact_path = metadata_dir / "video.json"
    raw_path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    compact = compact_metadata(raw)
    compact_path.write_text(
        json.dumps(compact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    downloaded_path = None
    download_arguments = None
    if args.download:
        download_arguments, downloaded_path = download(
            source, args.part, media_dir, args.force
        )

    result = {
        "metadata": str(compact_path),
        "raw_metadata": str(raw_path),
        "inspect_command": inspect_arguments,
        "downloaded": downloaded_path,
        "download_command": download_arguments,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
