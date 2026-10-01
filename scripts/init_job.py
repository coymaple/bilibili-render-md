#!/usr/bin/env python3
"""Create the portable output layout for one Bilibili-to-Markdown job."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


SAFE = re.compile(r"[^A-Za-z0-9._-]+")
MEDIA_ID = re.compile(r"\((BV[0-9A-Za-z]+|[Aa]v(\d+)),\s*[Pp](\d+)\)")
AUDIO_SUFFIXES = (".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".opus")


def safe_component(value: str) -> str:
    value = SAFE.sub("-", value.strip()).strip("-.")
    if not value:
        raise ValueError("job component is empty after sanitization")
    return value


def parse_media_identity(path: Path) -> tuple[str, str | None]:
    match = MEDIA_ID.search(path.stem)
    if not match:
        return "", None
    if match.group(2):
        return f"Av{match.group(2)}", match.group(3)
    return match.group(1), match.group(3)


def find_sibling_audio(video_path: Path) -> Path | None:
    for suffix in AUDIO_SUFFIXES:
        candidate = video_path.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def resolve_job_id(
    bvid: str | None, part: str | None, video_path: Path | None
) -> tuple[str, str, str | None]:
    if bvid:
        job_id = f"{safe_component(bvid)}_P{safe_component(part)}" if part else f"{safe_component(bvid)}_FULL"
        return job_id, safe_component(bvid), part
    if video_path:
        media_id, media_part = parse_media_identity(video_path)
        if media_id:
            effective_part = part or media_part
            if effective_part:
                job_id = f"{safe_component(media_id)}_P{safe_component(effective_part)}"
            else:
                job_id = f"{safe_component(media_id)}_FULL"
            return job_id, media_id, effective_part
        stem = video_path.stem
        job_id = f"{safe_component(stem)}_P{safe_component(part)}" if part else f"{safe_component(stem)}_FULL"
        return job_id, "", part
    raise ValueError("either --bvid or --video-path is required")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--bvid")
    parser.add_argument("--part", help="Part number, for example 5")
    parser.add_argument("--video-path", type=Path)
    parser.add_argument("--audio-path", type=Path, help="Override the sibling audio auto-discovery")
    parser.add_argument("--title")
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()

    job_id, bvid, part = resolve_job_id(args.bvid, args.part, args.video_path)
    job_root = (workspace / "output" / job_id).resolve()

    expected_parent = (workspace / "output").resolve()
    if expected_parent != job_root.parent:
        raise ValueError("resolved job path escaped the workspace output directory")

    relative_dirs = [
        "source/metadata",
        "source/media",
        "work/transcript/chunks",
        "work/frames/coarse",
        "work/frames/targeted",
        "work/contact-sheets",
        "work/hotspots",
        "work/logs",
        "work/temp",
        "deliverables/docs",
        "deliverables/assets/cover",
        "deliverables/assets/figures",
        "deliverables/attachments",
    ]
    for relative in relative_dirs:
        (job_root / relative).mkdir(parents=True, exist_ok=True)

    media_dir = job_root / "source" / "media"

    video_dest: Path | None = None
    if args.video_path and args.video_path.is_file():
        video_dest = media_dir / f"{job_id}{args.video_path.suffix}"
        shutil.copy2(args.video_path, video_dest)

    audio_input: Path | None = None
    if args.audio_path:
        audio_input = args.audio_path.expanduser()
    elif args.video_path and args.video_path.is_file():
        audio_input = find_sibling_audio(args.video_path)

    audio_dest: Path | None = None
    if audio_input and audio_input.is_file():
        audio_dest = media_dir / f"{job_id}_audio{audio_input.suffix}"
        shutil.copy2(audio_input, audio_dest)

    manifest = {
        "workspace": str(workspace),
        "job_root": str(job_root),
        "job_id": job_root.name,
        "bvid": bvid,
        "part": part,
        "title": args.title,
        "video_source": str(video_dest) if video_dest else None,
        "video_input": str(args.video_path) if args.video_path else None,
        "audio_source": str(audio_dest) if audio_dest else None,
        "audio_input": str(audio_input) if audio_input else None,
        "directories": {name: str(job_root / name) for name in relative_dirs},
    }
    manifest_path = job_root / "work" / "job-layout.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
