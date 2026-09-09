#!/usr/bin/env python3
"""Validate separation and local links for a Bilibili Markdown delivery."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SENSITIVE = [
    re.compile(
        r"(?i)(api[_-]?key|access[_-]?token|secret|cookie)\s*[:=]\s*[\"']?"
        r"(?!process\.env|os\.environ|<|\$\{|your[-_]|example[-_])"
        r"[A-Za-z0-9_./+=-]{16,}"
    ),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9_./+=-]{16,}"),
    re.compile(r"https://[A-Za-z0-9-]+\.upstash\.io"),
]


def is_remote(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "#"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()

    job_root = args.job_root.expanduser().resolve()
    markdown = args.markdown.expanduser().resolve()
    deliverables = (job_root / "deliverables").resolve()
    docs = (deliverables / "docs").resolve()
    errors: list[str] = []

    for required in (job_root / "source", job_root / "work", deliverables, docs):
        if not required.is_dir():
            errors.append(f"missing required directory: {required}")

    if not markdown.is_file():
        errors.append(f"missing Markdown: {markdown}")
    else:
        try:
            markdown.relative_to(docs)
        except ValueError:
            errors.append("final Markdown must be inside deliverables/docs")

    text = markdown.read_text(encoding="utf-8") if markdown.is_file() else ""
    for match in LINK.finditer(text):
        target = match.group(1).strip().strip("<>")
        if is_remote(target):
            continue
        target_path = (markdown.parent / target).resolve()
        try:
            target_path.relative_to(deliverables)
        except ValueError:
            errors.append(f"local link escapes deliverables: {target}")
            continue
        if not target_path.exists():
            errors.append(f"missing local link target: {target}")

    for pattern in SENSITIVE:
        if pattern.search(text):
            errors.append(f"possible sensitive value matched: {pattern.pattern}")

    result = {
        "job_root": str(job_root),
        "markdown": str(markdown),
        "ok": not errors,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
