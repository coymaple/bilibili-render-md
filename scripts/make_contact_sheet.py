#!/usr/bin/env python3
"""Build a labeled contact sheet from extracted video frames."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path


FRAME_TIME = re.compile(r"frame_(\d{2})-(\d{2})-(\d{2})(?:-(\d{3}))?")


def format_seconds(value: float) -> str:
    seconds = round(value)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def load_timestamp_map(input_dir: Path) -> dict[str, float]:
    manifest = input_dir / "frames.json"
    if not manifest.is_file():
        return {}
    data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    return {
        Path(str(item["path"])).name: float(item["timestamp_seconds"])
        for item in data.get("frames", [])
        if item.get("path") and item.get("timestamp_seconds") is not None
    }


def frame_label(path: Path, index: int, timestamp_map: dict[str, float]) -> str:
    if path.name in timestamp_map:
        return format_seconds(timestamp_map[path.name])
    match = FRAME_TIME.search(path.stem)
    if match:
        return f"{match.group(1)}:{match.group(2)}:{match.group(3)}"
    return f"frame {index}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a contact sheet from frames")
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--cell-width", type=int, default=360)
    parser.add_argument("--cell-height", type=int, default=230)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.columns <= 0 or args.cell_width <= 0 or args.cell_height <= 30:
        raise ValueError("columns and cell dimensions must be positive")
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError as error:
        raise RuntimeError(
            "Pillow is required for contact sheets; install project requirements"
        ) from error

    job_root = args.job_root.expanduser().resolve()
    input_dir = (
        args.input_dir.expanduser().resolve()
        if args.input_dir
        else job_root / "work" / "frames" / "coarse"
    )
    output = (
        args.output.expanduser().resolve()
        if args.output
        else job_root / "work" / "contact-sheets" / "coarse.jpg"
    )
    if output.exists() and not args.force:
        raise FileExistsError(f"output exists; pass --force to replace it: {output}")

    frames = sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    if not frames:
        raise FileNotFoundError(f"no image frames found under {input_dir}")
    timestamp_map = load_timestamp_map(input_dir)

    label_height = 28
    rows = math.ceil(len(frames) / args.columns)
    sheet = Image.new(
        "RGB",
        (args.columns * args.cell_width, rows * args.cell_height),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(frames, start=1):
        with Image.open(path) as source:
            image = ImageOps.contain(
                source.convert("RGB"),
                (args.cell_width, args.cell_height - label_height),
            )
        column = (index - 1) % args.columns
        row = (index - 1) // args.columns
        x = column * args.cell_width + (args.cell_width - image.width) // 2
        y = row * args.cell_height
        sheet.paste(image, (x, y))
        draw.text(
            (column * args.cell_width + 8, y + args.cell_height - label_height + 6),
            frame_label(path, index, timestamp_map),
            fill="black",
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=88, optimize=True)
    print(
        json.dumps(
            {"frame_count": len(frames), "output": str(output)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
