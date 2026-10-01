#!/usr/bin/env python3
"""Recall timestamped high-value segments from an SRT transcript.

This is a deterministic candidate generator. It preserves compact evidence
so an agent or human can perform the final semantic review without rereading
the complete transcript.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from slice_transcript import Entry, parse_srt, stamp


SIGNAL_PATTERNS: dict[str, tuple[float, re.Pattern[str]]] = {
    "importance": (
        1.6,
        re.compile(r"核心|关键|重点|最重要|本质|一定要|必须|注意|记住|critical|important|key point", re.I),
    ),
    "explanation": (
        1.3,
        re.compile(r"因为|所以|原因|意味着|也就是说|换句话说|原理|机制|为什么|because|therefore|which means|how it works", re.I),
    ),
    "practice": (
        1.1,
        re.compile(r"如何|怎么|实现|解决|配置|步骤|示例|例子|命令|代码|how to|implement|configure|example|command", re.I),
    ),
    "contrast": (
        0.9,
        re.compile(r"区别|相比|但是|而不是|优点|缺点|问题|错误|避免|versus|instead of|difference|problem|error|avoid", re.I),
    ),
    "conclusion": (
        1.0,
        re.compile(r"总结|结论|最终|归根结底|可以看出|takeaway|in summary|conclusion", re.I),
    ),
}

LOW_VALUE = re.compile(
    r"一键三连|点赞|投币|收藏|关注|订阅|广告|赞助|感谢观看|下期再见|"
    r"like and subscribe|sponsor|thanks for watching",
    re.I,
)
TOKEN = re.compile(
    r"\b[A-Za-z][A-Za-z0-9_.:/@+-]{2,}\b|"
    r"[\u4e00-\u9fff]{2,8}(?=[，。！？；：、\s]|$)"
)
TOKEN_STOP = {
    "because", "therefore", "example", "important", "actually", "basically",
    "这个", "那个", "我们", "你们", "然后", "就是", "所以", "因为", "现在",
    "可以", "进行", "一个", "这里", "里面", "什么", "这样", "如果", "但是",
}


@dataclass(frozen=True)
class Window:
    start_ms: int
    end_ms: int
    entries: tuple[Entry, ...]

    @property
    def duration_seconds(self) -> float:
        return max(0.0, (self.end_ms - self.start_ms) / 1000.0)

    @property
    def text(self) -> str:
        return " ".join(entry.text for entry in self.entries)


def parse_clock(value: str) -> int:
    parts = [int(part) for part in value.split(":")]
    if len(parts) != 3:
        raise ValueError(f"invalid timestamp: {value}")
    hours, minutes, seconds = parts
    return ((hours * 60 + minutes) * 60 + seconds) * 1000


def resolve_srt(job_root: Path, explicit: Path | None) -> Path:
    if explicit:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"SRT not found: {path}")
        return path

    transcript_dir = job_root / "work" / "transcript"
    matches = sorted(transcript_dir.glob("*.srt"))
    if not matches:
        raise FileNotFoundError(
            f"no SRT found under {transcript_dir}; pass --srt explicitly"
        )
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise ValueError(f"multiple SRT files found ({names}); pass --srt explicitly")
    return matches[0].resolve()


def build_windows(
    entries: list[Entry], window_seconds: float, stride_seconds: float, min_seconds: float
) -> list[Window]:
    window_ms = round(window_seconds * 1000)
    stride_ms = round(stride_seconds * 1000)
    min_ms = round(min_seconds * 1000)
    first_ms = entries[0].start_ms
    last_ms = entries[-1].end_ms
    cursor = first_ms
    seen: set[tuple[int, int]] = set()
    windows: list[Window] = []

    while cursor < last_ms:
        matching = tuple(
            entry
            for entry in entries
            if entry.end_ms > cursor and entry.start_ms < cursor + window_ms
        )
        if matching:
            key = (matching[0].start_ms, matching[-1].end_ms)
            duration = key[1] - key[0]
            if key not in seen and duration >= min_ms:
                seen.add(key)
                windows.append(Window(key[0], key[1], matching))
        cursor += stride_ms
    return windows


def load_inventory(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError(f"inventory must contain a JSON list: {path}")
    return data


def overlapping_inventory(
    window: Window, inventory: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    result = []
    for item in inventory:
        try:
            start_ms = parse_clock(str(item["start"]))
            end_ms = parse_clock(str(item["end"]))
        except (KeyError, TypeError, ValueError):
            continue
        if end_ms > window.start_ms and start_ms < window.end_ms:
            result.append(item)
    return result


def extract_keywords(text: str, inventory_items: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for item in inventory_items:
        values.extend(str(value) for value in item.get("terms", []) if value)
    values.extend(match.group() for match in TOKEN.finditer(text))
    counts = Counter(value for value in values if value.lower() not in TOKEN_STOP)
    return [value for value, _ in counts.most_common(8)]


def score_window(
    window: Window, inventory_items: list[dict[str, Any]]
) -> tuple[float, dict[str, Any]]:
    text = window.text
    compact_chars = len(re.sub(r"\s+", "", text))
    density = compact_chars / max(window.duration_seconds, 1.0)
    score = min(density / 5.0, 1.0) * 2.0
    signals: dict[str, Any] = {"chars_per_second": round(density, 2)}

    for name, (weight, pattern) in SIGNAL_PATTERNS.items():
        hits = len(pattern.findall(text))
        if hits:
            signals[name] = hits
            score += min(hits, 3) * weight

    inventory_points = sum(len(item.get("points", [])) for item in inventory_items)
    inventory_code = sum(
        len(item.get("commands", [])) + len(item.get("codes", []))
        for item in inventory_items
    )
    if inventory_points:
        signals["inventory_points"] = inventory_points
        score += min(inventory_points, 5) * 0.35
    if inventory_code:
        signals["code_or_commands"] = inventory_code
        score += min(inventory_code, 4) * 0.3

    low_value_hits = len(LOW_VALUE.findall(text))
    if low_value_hits:
        signals["low_value"] = low_value_hits
        score -= low_value_hits * 2.0

    return round(max(score, 0.0), 3), signals


def overlap_ratio(left: Window, right: Window) -> float:
    overlap = max(
        0, min(left.end_ms, right.end_ms) - max(left.start_ms, right.start_ms)
    )
    shorter = min(left.end_ms - left.start_ms, right.end_ms - right.start_ms)
    return overlap / shorter if shorter > 0 else 0.0


def select_candidates(
    scored: list[tuple[Window, float, dict[str, Any], list[str]]],
    count: int,
    max_overlap: float,
) -> list[tuple[Window, float, dict[str, Any], list[str], int]]:
    ranked = sorted(scored, key=lambda item: (-item[1], item[0].start_ms))
    selected: list[tuple[Window, float, dict[str, Any], list[str], int]] = []
    for rank, item in enumerate(ranked, start=1):
        window = item[0]
        if any(overlap_ratio(window, chosen[0]) > max_overlap for chosen in selected):
            continue
        selected.append((*item, rank))
        if len(selected) == count:
            break
    return sorted(selected, key=lambda item: item[0].start_ms)


def evidence_lines(window: Window, limit: int = 4) -> list[dict[str, str]]:
    weighted: list[tuple[int, Entry]] = []
    for entry in window.entries:
        hits = sum(
            len(pattern.findall(entry.text))
            for _, pattern in SIGNAL_PATTERNS.values()
        )
        weighted.append((hits, entry))
    chosen = sorted(weighted, key=lambda item: (-item[0], item[1].start_ms))[:limit]
    chosen.sort(key=lambda item: item[1].start_ms)
    return [
        {"time": stamp(entry.start_ms), "text": entry.text}
        for _, entry in chosen
    ]


def title_hint(window: Window, keywords: list[str]) -> str:
    if keywords:
        return " / ".join(keywords[:3])
    text = window.entries[0].text.strip()
    return text[:32] + ("…" if len(text) > 32 else "")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recall timestamped core-topic/high-value segment candidates from an SRT"
    )
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--srt", type=Path, default=None)
    parser.add_argument("--inventory", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--window-seconds", type=float, default=90.0)
    parser.add_argument("--stride-seconds", type=float, default=30.0)
    parser.add_argument("--min-seconds", type=float, default=30.0)
    parser.add_argument("--max-overlap", type=float, default=0.35)
    args = parser.parse_args()

    if args.count <= 0:
        raise ValueError("--count must be positive")
    if args.window_seconds <= 0 or args.stride_seconds <= 0 or args.min_seconds <= 0:
        raise ValueError("window, stride, and minimum durations must be positive")
    if args.min_seconds > args.window_seconds:
        raise ValueError("--min-seconds cannot exceed --window-seconds")
    if not 0 <= args.max_overlap < 1:
        raise ValueError("--max-overlap must be in [0, 1)")

    job_root = args.job_root.expanduser().resolve()
    srt = resolve_srt(job_root, args.srt)
    inventory_path = (
        args.inventory.expanduser().resolve()
        if args.inventory
        else job_root / "work" / "transcript" / "inventory.json"
    )
    output_path = (
        args.out.expanduser().resolve()
        if args.out
        else job_root / "work" / "hotspots" / "hotspot-candidates.json"
    )

    entries = parse_srt(srt)
    if not entries:
        raise ValueError(f"no SRT entries parsed from {srt}")
    inventory = load_inventory(inventory_path if inventory_path.is_file() else None)
    windows = build_windows(
        entries, args.window_seconds, args.stride_seconds, args.min_seconds
    )
    if not windows:
        raise ValueError(
            "transcript is shorter than the configured minimum hotspot duration"
        )

    scored = []
    for window in windows:
        items = overlapping_inventory(window, inventory)
        score, signals = score_window(window, items)
        keywords = extract_keywords(window.text, items)
        scored.append((window, score, signals, keywords))

    selected = select_candidates(
        scored, min(args.count, len(scored)), args.max_overlap
    )
    candidates = []
    for index, (window, score, signals, keywords, score_rank) in enumerate(
        selected, start=1
    ):
        candidates.append(
            {
                "id": f"candidate-{index:02d}",
                "score_rank": score_rank,
                "start": stamp(window.start_ms),
                "end": stamp(window.end_ms),
                "duration_seconds": round(window.duration_seconds, 3),
                "score": score,
                "title_hint": title_hint(window, keywords),
                "keywords": keywords,
                "signals": signals,
                "evidence": evidence_lines(window),
                "review_status": "candidate",
            }
        )

    result = {
        "schema_version": 1,
        "kind": "hotspot_candidates",
        "source_srt": str(srt),
        "inventory": str(inventory_path) if inventory else None,
        "review_required": True,
        "method": "deterministic sliding-window recall; semantic review required",
        "parameters": {
            "count": args.count,
            "window_seconds": args.window_seconds,
            "stride_seconds": args.stride_seconds,
            "min_seconds": args.min_seconds,
            "max_overlap": args.max_overlap,
        },
        "candidates": candidates,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"candidate_count": len(candidates), "output": str(output_path)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
