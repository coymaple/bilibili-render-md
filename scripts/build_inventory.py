#!/usr/bin/env python3
"""Build a mechanical content inventory from sliced transcript chunks.

For each chunk this script records:
  - time range and density (chars/min, "sparse" below --density-threshold)
  - terms       : code identifiers / library names mentioned >= 2 times
  - commands    : package/version-control command lines mentioned
  - codes       : code-shaped lines (imports, definitions, assignments)
  - visual_cues : sentences that imply on-screen content not in the speech
  - transition_cues : spoken sentences that hint at a course-chapter switch
  - points / chapter : reserved for the model to fill while drafting (empty
    here); the model labels each chunk's course chapter from transition cues
    plus screen signals, marking boundary chunks with chapter_boundary.

The model is expected to read every chunk once, enrich `points`, then write
each chapter against this inventory so nothing in the transcript is skipped.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
PACKAGE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-:.@][A-Za-z0-9]+)+")
STAMP_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})--(\d{2}:\d{2}:\d{2})\]")

STOP_WORDS = {
    "is", "it", "this", "that", "the", "and", "or", "for", "with", "from",
    "you", "your", "are", "was", "were", "have", "has", "had", "will", "can",
    "could", "would", "should", "not", "but", "all", "any", "here", "there",
    "then", "than", "too", "very", "just", "what", "which", "when", "where",
    "why", "how", "who", "whom", "them", "they", "we", "our", "us", "me", "him",
    "her", "into", "about", "only", "more", "most", "some", "such", "each",
    "both", "few", "own", "same", "okay", "yeah", "going", "gonna", "want",
    "need", "know", "thing", "stuff", "like", "really", "actually", "basically",
    "let", "get", "got", "say", "says", "said", "make", "made", "use", "used",
    "using", "file", "files", "folder", "directory",
    "run", "running", "click", "type", "write", "open", "close", "show", "see",
}

COMMAND_PATTERNS = [
    re.compile(r"\b(?:pip3?|conda|apt(?:-get)?|brew|cargo|go)\s+install\b", re.IGNORECASE),
    re.compile(r"\b(?:npm|yarn|pnpm|bun|cnpm)\s+(?:install|add|remove|update)\b", re.IGNORECASE),
    re.compile(r"\b(?:npm|yarn|pnpm|npx|bun)\s+(?:run|create|init|start)\b", re.IGNORECASE),
    re.compile(r"\b(?:git)\s+(?:clone|init|add|commit|push|pull|checkout|branch)\b", re.IGNORECASE),
    re.compile(r"\b(?:docker)\s+(?:build|run|compose|push|pull)\b", re.IGNORECASE),
    re.compile(r"\b(?:make|cmake|gradle|mvn|dotnet)\s+(?:install|build|run|test)\b", re.IGNORECASE),
    re.compile(r"^\s*(?:sudo\s+)?(?:mkdir|rm|cp|mv|cd|touch|curl|wget|chmod|chown)\s", re.IGNORECASE),
]

CODE_PATTERNS = [
    re.compile(r"\bimport\s+", ),
    re.compile(r"\bfrom\s+['\"\w.@/=-]+\s+import\b"),
    re.compile(r"\b(?:const|let|var)\s+\w+\s*="),
    re.compile(r"\b(?:function|class|def|interface|type|enum|async)\s+\w+"),
    re.compile(r"\bexport\s+(?:default\s+)?(?:function|class|const|async)"),
    re.compile(r"\breturn\s+\w+\s*;?"),
    re.compile(r"=>"),
]

VISUAL_PATTERNS = [
    re.compile(r"(看到|注意|界面|画面|显示|弹窗|点击|打开|右侧|左侧|顶部|底部|大家看|屏幕上|浏览器中)", ),
    re.compile(r"(you can see|look at|notice|here we|on the screen|the ui|the window|open the browser)", re.IGNORECASE),
]

TRANSITION_PATTERNS = [
    re.compile(r"(接下来|下面进入|现在进入|现在开始|下一部分|下一章节|这部分|这个部分|我们开始|进入第.部分|第.{1,4}(?:章|部分|节|讲))", ),
    re.compile(r"(next\s+(?:section|chapter|part)|move(?:ing)?\s+on\s+to|let'?s\s+move|now\s+let'?s|now\s+(?:we'?re|we'?ll|welcome|let'?s)|\bin\s+this\s+(?:chapter|section|part)\b|part\s+\d+|chapter\s+\d+)", re.IGNORECASE),
]

MAX_TERMS = 20
MAX_COMMANDS = 15
MAX_CODES = 15
MAX_VISUAL_CUES = 8
MAX_TRANSITION_CUES = 6


def to_minutes(stamp_str: str) -> float:
    hours, minutes, seconds = (int(p) for p in stamp_str.split(":"))
    return hours * 60 + minutes + seconds / 60.0


def strip_stamp(line: str) -> str:
    return STAMP_RE.sub("", line, count=1).strip()


def extract_terms(text: str) -> list[str]:
    freq: dict[str, int] = {}
    for match in PACKAGE.finditer(text):
        word = match.group()
        if word.lower() in STOP_WORDS:
            continue
        freq[word] = freq.get(word, 0) + 1
    package_masked = PACKAGE.sub(" ", text)
    for match in IDENT.finditer(package_masked):
        word = match.group()
        if word.lower() in STOP_WORDS:
            continue
        freq[word] = freq.get(word, 0) + 1
    ranked = sorted(
        ((count, word) for word, count in freq.items() if count >= 2),
        reverse=True,
    )
    return [word for _, word in ranked[:MAX_TERMS]]


def extract_commands(lines: list[str]) -> list[str]:
    found: list[str] = []
    for line in lines:
        cleaned = strip_stamp(line)
        for pattern in COMMAND_PATTERNS:
            match = pattern.search(cleaned)
            if not match:
                continue
            segment = cleaned[match.start():].split()
            command = " ".join(segment[:4]).strip()
            if command.startswith(("sudo", "cd")):
                command = " ".join(command.split()[1:]).strip() or command
            if command and command not in found:
                found.append(command)
            break
    return found[:MAX_COMMANDS]


def extract_codes(lines: list[str]) -> list[str]:
    found: list[str] = []
    for line in lines:
        cleaned = strip_stamp(line)
        for pattern in CODE_PATTERNS:
            match = pattern.search(cleaned)
            if not match:
                continue
            code = cleaned[match.start():].strip()[:100]
            if code and code not in found:
                found.append(code)
            break
    return found[:MAX_CODES]


def extract_visual_cues(lines: list[str]) -> list[str]:
    found: list[str] = []
    for line in lines:
        cleaned = strip_stamp(line)
        if any(p.search(cleaned) for p in VISUAL_PATTERNS):
            if cleaned not in found:
                found.append(cleaned[:80])
    return found[:MAX_VISUAL_CUES]


def extract_transition_cues(lines: list[str]) -> list[str]:
    found: list[str] = []
    for line in lines:
        cleaned = strip_stamp(line)
        if any(p.search(cleaned) for p in TRANSITION_PATTERNS):
            if cleaned not in found:
                found.append(cleaned[:100])
    return found[:MAX_TRANSITION_CUES]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--chunk-dir", type=Path, default=None,
                        help="chunk directory (default: <job-root>/work/transcript/chunks)")
    parser.add_argument("--out", type=Path, default=None,
                        help="inventory output path (default: <job-root>/work/transcript/inventory.json)")
    parser.add_argument("--density-threshold", type=float, default=150.0,
                        help="chars per minute below which a chunk is marked sparse")
    args = parser.parse_args()

    job_root = args.job_root.expanduser().resolve()
    chunk_dir = (args.chunk_dir or job_root / "work" / "transcript" / "chunks").expanduser().resolve()
    inventory_path = (args.out or job_root / "work" / "transcript" / "inventory.json").expanduser().resolve()

    index_path = chunk_dir / "index.json"
    if not index_path.is_file():
        raise SystemExit(f"index.json not found: {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8-sig"))
    chunks = index.get("chunks", [])
    if not chunks:
        raise SystemExit("index.json contains no chunks")

    inventory: list[dict] = []
    for entry in chunks:
        chunk_file = chunk_dir / entry["path"]
        if not chunk_file.is_file():
            raise SystemExit(f"chunk file missing: {chunk_file}")
        text = chunk_file.read_text(encoding="utf-8-sig")
        lines = [line for line in text.splitlines() if line.strip()]

        duration_min = to_minutes(entry["end"]) - to_minutes(entry["start"])
        chars = len(re.sub(r"\s+", "", text))
        density = chars / duration_min if duration_min > 0 else float("inf")
        sparse = density < args.density_threshold

        inventory.append(
            {
                "chunk": entry["chunk"],
                "start": entry["start"],
                "end": entry["end"],
                "entries": entry["entries"],
                "density": "sparse" if sparse else "normal",
                "chars_per_minute": round(density, 1),
                "terms": extract_terms(text),
                "commands": extract_commands(lines),
                "codes": extract_codes(lines),
                "visual_cues": extract_visual_cues(lines),
                "transition_cues": extract_transition_cues(lines),
                "chapter": None,
                "points": [],
                "covered": [],
            }
        )

    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = {
        "chunk_count": len(inventory),
        "sparse_chunks": [e["chunk"] for e in inventory if e["density"] == "sparse"],
        "inventory": str(inventory_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())