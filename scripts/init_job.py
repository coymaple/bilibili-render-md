#!/usr/bin/env python3
"""Create the portable output layout for one Bilibili-to-Markdown job."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_component(value: str) -> str:
    value = SAFE.sub("-", value.strip()).strip("-.")
    if not value:
        raise ValueError("job component is empty after sanitization")
    return value


def resolve_job_id(workspace: Path, bvid: str | None, part: str | None, video_path: Path | None) -> tuple[str, str]:
    if bvid:
        job_id = f"{safe_component(bvid)}_P{safe_component(part)}" if part else f"{safe_component(bvid)}_FULL"
        return job_id, safe_component(bvid)
    if video_path:
        stem = video_path.stem
        job_id = f"{safe_component(stem)}_P{safe_component(part)}" if part else f"{safe_component(stem)}_FULL"
        return job_id, ""
    raise ValueError("either --bvid or --video-path is required")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--bvid")
    parser.add_argument("--part", help="Part number, for example 5")
    parser.add_argument("--video-path", type=Path)
    parser.add_argument("--title")
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()

    job_id, bvid = resolve_job_id(workspace, args.bvid, args.part, args.video_path)
    suffix = f"P{safe_component(args.part)}" if args.part else "FULL"
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
        "work/logs",
        "work/temp",
        "deliverables/docs",
        "deliverables/assets/cover",
        "deliverables/assets/figures",
        "deliverables/attachments",
    ]
    for relative in relative_dirs:
        (job_root / relative).mkdir(parents=True, exist_ok=True)

    video_dest: Path | None = None
    if args.video_path and args.video_path.is_file():
        media_dir = job_root / "source" / "media"
        ext = args.video_path.suffix
        video_dest = media_dir / f"{job_id}{ext}"
        shutil.copy2(args.video_path, video_dest)

    manifest = {
        "workspace": str(workspace),
        "job_root": str(job_root),
        "job_id": job_root.name,
        "bvid": bvid,
        "part": args.part,
        "title": args.title,
        "video_source": str(video_dest) if video_dest else None,
        "video_input": str(args.video_path) if args.video_path else None,
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
