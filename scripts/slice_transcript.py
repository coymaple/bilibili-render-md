#!/usr/bin/env python3
"""Split an SRT into bounded timestamped text chunks and a compact index."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


TIMING = re.compile(
    r"(?P<sh>\d{2}):(?P<sm>\d{2}):(?P<ss>\d{2})[,.](?P<sms>\d{3})\s+-->\s+"
    r"(?P<eh>\d{2}):(?P<em>\d{2}):(?P<es>\d{2})[,.](?P<ems>\d{3})"
)


@dataclass
class Entry:
    start_ms: int
    end_ms: int
    text: str


def to_ms(hours: str, minutes: str, seconds: str, millis: str) -> int:
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


def stamp(milliseconds: int) -> str:
    seconds = milliseconds // 1000
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def parse_srt(path: Path) -> list[Entry]:
    blocks = re.split(r"\r?\n\s*\r?\n", path.read_text(encoding="utf-8-sig").strip())
    entries: list[Entry] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        match = TIMING.fullmatch(lines[timing_index])
        if not match:
            continue
        groups = match.groupdict()
        start = to_ms(groups["sh"], groups["sm"], groups["ss"], groups["sms"])
        end = to_ms(groups["eh"], groups["em"], groups["es"], groups["ems"])
        text = " ".join(lines[timing_index + 1 :]).strip()
        if text:
            entries.append(Entry(start, end, text))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("srt", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--minutes", type=float, default=8.0)
    args = parser.parse_args()

    if args.minutes <= 0:
        raise ValueError("--minutes must be positive")

    srt = args.srt.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    entries = parse_srt(srt)
    if not entries:
        raise ValueError(f"no SRT entries parsed from {srt}")

    window_ms = round(args.minutes * 60_000)
    buckets: dict[int, list[Entry]] = {}
    for entry in entries:
        buckets.setdefault(entry.start_ms // window_ms, []).append(entry)

    index = []
    for number, bucket_id in enumerate(sorted(buckets), start=1):
        chunk_entries = buckets[bucket_id]
        start_ms = chunk_entries[0].start_ms
        end_ms = chunk_entries[-1].end_ms
        filename = f"chunk_{number:03d}_{stamp(start_ms).replace(':', '-')}_{stamp(end_ms).replace(':', '-')}.txt"
        chunk_path = output_dir / filename
        lines = [
            f"[{stamp(entry.start_ms)}--{stamp(entry.end_ms)}] {entry.text}"
            for entry in chunk_entries
        ]
        chunk_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        index.append(
            {
                "chunk": number,
                "start": stamp(start_ms),
                "end": stamp(end_ms),
                "entries": len(chunk_entries),
                "path": filename,
            }
        )

    index_path = output_dir / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "source": str(srt),
                "window_minutes": args.minutes,
                "entry_count": len(entries),
                "chunks": index,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"entry_count": len(entries), "chunk_count": len(index), "index": str(index_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

