#!/usr/bin/env python3
"""Run and checkpoint the deterministic post-transcription workflow."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def resolve_srt(job_root: Path, explicit: Path | None) -> Path:
    if explicit:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"SRT not found: {path}")
        return path
    matches = sorted((job_root / "work" / "transcript").glob("*.srt"))
    if len(matches) != 1:
        raise ValueError(
            "expected exactly one SRT under work/transcript; pass --srt explicitly"
        )
    return matches[0].resolve()


def run_stage(
    name: str,
    command: list[str],
    state: dict[str, Any],
    state_path: Path,
) -> None:
    stage = {
        "status": "running",
        "started_at": now(),
        "command": command,
    }
    state["stages"][name] = stage
    save_state(state_path, state)
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stage["finished_at"] = now()
    stage["returncode"] = completed.returncode
    stage["stdout"] = completed.stdout.strip()
    stage["stderr"] = completed.stderr.strip()
    stage["status"] = "completed" if completed.returncode == 0 else "failed"
    save_state(state_path, state)
    if completed.returncode != 0:
        raise RuntimeError(
            f"stage {name} failed ({completed.returncode}): "
            f"{stage['stderr'] or stage['stdout']}"
        )


def mark_skipped(
    name: str, artifact: Path, state: dict[str, Any], state_path: Path
) -> None:
    state["stages"][name] = {
        "status": "skipped",
        "reason": "artifact already exists; pass --force to rebuild",
        "artifact": str(artifact),
        "finished_at": now(),
    }
    save_state(state_path, state)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run slice, inventory, optional hotspot, and validation stages"
    )
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--srt", type=Path, default=None)
    parser.add_argument("--chunk-minutes", type=float, default=8.0)
    parser.add_argument("--hotspots", action="store_true")
    parser.add_argument("--hotspot-count", type=int, default=8)
    parser.add_argument("--markdown", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.chunk_minutes <= 0 or args.hotspot_count <= 0:
        raise ValueError("chunk minutes and hotspot count must be positive")

    job_root = args.job_root.expanduser().resolve()
    if not job_root.is_dir():
        raise FileNotFoundError(f"job root not found: {job_root}")
    srt = resolve_srt(job_root, args.srt)
    state_path = job_root / "work" / "pipeline-state.json"
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    else:
        state = {"schema_version": 1, "stages": {}}
    state["job_root"] = str(job_root)
    state["source_srt"] = str(srt)
    state.setdefault("stages", {})

    chunks = job_root / "work" / "transcript" / "chunks"
    chunk_index = chunks / "index.json"
    if chunk_index.exists() and not args.force:
        mark_skipped("slice_transcript", chunk_index, state, state_path)
    else:
        if args.force and chunks.is_dir():
            for stale_chunk in chunks.glob("chunk_*.txt"):
                stale_chunk.unlink()
            if chunk_index.is_file():
                chunk_index.unlink()
        run_stage(
            "slice_transcript",
            [
                sys.executable,
                str(SCRIPT_DIR / "slice_transcript.py"),
                str(srt),
                "--output-dir",
                str(chunks),
                "--minutes",
                str(args.chunk_minutes),
            ],
            state,
            state_path,
        )

    inventory = job_root / "work" / "transcript" / "inventory.json"
    if inventory.exists() and not args.force:
        mark_skipped("build_inventory", inventory, state, state_path)
    else:
        run_stage(
            "build_inventory",
            [
                sys.executable,
                str(SCRIPT_DIR / "build_inventory.py"),
                "--job-root",
                str(job_root),
            ],
            state,
            state_path,
        )

    if args.hotspots:
        hotspot_candidates = (
            job_root / "work" / "hotspots" / "hotspot-candidates.json"
        )
        if hotspot_candidates.exists() and not args.force:
            mark_skipped(
                "extract_hotspots", hotspot_candidates, state, state_path
            )
        else:
            run_stage(
                "extract_hotspots",
                [
                    sys.executable,
                    str(SCRIPT_DIR / "extract_hotspots.py"),
                    "--job-root",
                    str(job_root),
                    "--srt",
                    str(srt),
                    "--count",
                    str(args.hotspot_count),
                ],
                state,
                state_path,
            )

    if args.markdown:
        markdown = args.markdown.expanduser().resolve()
        run_stage(
            "check_inventory_coverage",
            [
                sys.executable,
                str(SCRIPT_DIR / "check_inventory_coverage.py"),
                "--job-root",
                str(job_root),
                "--markdown",
                str(markdown),
            ],
            state,
            state_path,
        )
        validation_command = [
            sys.executable,
            str(SCRIPT_DIR / "validate_delivery.py"),
            "--job-root",
            str(job_root),
            "--markdown",
            str(markdown),
        ]
        if args.strict:
            validation_command.append("--strict")
        run_stage(
            "validate_delivery", validation_command, state, state_path
        )

    print(json.dumps({"ok": True, "state": str(state_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
