#!/usr/bin/env python3
"""Validate separation, local links, and content quality for a Bilibili Markdown delivery."""

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

CODE_BLOCK_RE = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
BARE_IMPORT = re.compile(r"^(import |from )", re.MULTILINE)
SHELL_LANGS = {
    "bash", "sh", "shell", "zsh", "powershell", "console", "terminal", "cmd",
    "text", "ascii", "tree", "plaintext", "log", "json", "yaml", "yml", "sql",
    "diff",
}
HAS_INSTALL = re.compile(
    r"(?:pip|pip3|pip install|npm|yarn|pnpm|bun|cnpm|apt|apt-get|brew|cargo|go"
    r"|mvn|gradle|composer|gem|dotnet|vcpkg|conda|micromamba|dnf|pacman)"
    r"\s+(?:install|add|update|upgrade|build|run)\b",
    re.IGNORECASE | re.MULTILINE,
)
BARE_INSTALL = re.compile(r"(?:pip|pip3|npm|yarn|pnpm|bun|cnpm)\s+install", re.IGNORECASE)
MISSING_CONTEXT = re.compile(
    r"(as shown in the video|see the video|like I showed|as demonstrated"
    r"|视频中的|如视频所示|如我之前|如上面所|正如我展示)",
    re.IGNORECASE,
)

REQUIRED_SECTIONS = [
    r"^# ",
    r"^## 这一讲完成什么",
    r"^## 学习路线",
]

INSTALL_COMMAND_EXAMPLES = [
    "pip install faster-whisper",
    "npm install express",
    "bun add express",
    "yarn add express",
    "pnpm add express",
    "cargo install cargo-watch",
    "go install github.com/xxx@latest",
    "conda install numpy",
    "apt install build-essential",
]


def is_remote(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "#"))


def check_code_block_quality(text: str) -> list[str]:
    errors: list[str] = []
    for match in CODE_BLOCK_RE.finditer(text):
        block_text = match.group(2)
        first_line = block_text.strip().split("\n")[0] if block_text.strip() else ""
        has_path_comment = first_line.startswith("//") or first_line.startswith("#") or first_line.startswith("/*")
        if not has_path_comment:
            lang = match.group(1) or "unknown"
            if lang not in SHELL_LANGS:
                errors.append("Code block missing file path comment (first line should be // <path> or # <path>)")
    return errors


def check_dependency_coverage(text: str) -> list[str]:
    errors: list[str] = []
    has_install = bool(HAS_INSTALL.search(text))
    if not has_install:
        code_blocks_with_imports = []
        for match in CODE_BLOCK_RE.finditer(text):
            block_text = match.group(2)
            if BARE_IMPORT.search(block_text):
                lang = match.group(1) or "unknown"
                if lang not in ("text", "ascii", "tree"):
                    code_blocks_with_imports.append(lang)
        if code_blocks_with_imports:
            errors.append(
                f"Code blocks contain imports ({', '.join(set(code_blocks_with_imports))}) "
                f"but no dependency installation command found in the document. "
                f"Add a section with an installation command near the relevant code."
            )
    return errors


def check_self_containment(text: str) -> list[str]:
    errors: list[str] = []
    for match in MISSING_CONTEXT.finditer(text):
        errors.append(f"Document references video content instead of being self-contained: '{match.group()}'")
    return errors


def check_required_sections(text: str) -> list[str]:
    errors: list[str] = []
    for pattern in REQUIRED_SECTIONS:
        if not re.search(pattern, text, re.MULTILINE):
            errors.append(f"Missing required section matching pattern: {pattern}")
    if not re.search(r"^## 一、", text, re.MULTILINE):
        errors.append("Missing at least one numbered teaching chapter (## 一、)")
    return errors


def check_figure_captions(text: str) -> list[str]:
    errors: list[str] = []
    figure_refs = re.findall(r"!\[.*?\]\(", text)
    caption_pattern = re.compile(r"^\*图 \d+：.*，画面时间 \d{2}:\d{2}。\*$", re.MULTILINE)
    for ref in figure_refs:
        if not caption_pattern.search(text):
            errors.append("Figure reference found but no matching caption with '图 N：…，画面时间 …' pattern")
            break
    return errors


def check_quality(text: str) -> dict[str, list[str]]:
    results: dict[str, list[str]] = {}
    results["code_block_quality"] = check_code_block_quality(text)
    results["dependency_coverage"] = check_dependency_coverage(text)
    results["self_containment"] = check_self_containment(text)
    results["required_sections"] = check_required_sections(text)
    results["figure_captions"] = check_figure_captions(text)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--strict", action="store_true", help="Treat quality warnings as errors")
    args = parser.parse_args()

    job_root = args.job_root.expanduser().resolve()
    markdown = args.markdown.expanduser().resolve()
    deliverables = (job_root / "deliverables").resolve()
    docs = (deliverables / "docs").resolve()
    errors: list[str] = []
    warnings: list[str] = []

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

    quality = check_quality(text)
    # Code-block path comments are best effort: the validator cannot tell a
    # project file from test/demo code, so missing annotations stay warnings
    # even under --strict. Remaining categories escalate with --strict.
    for category, cat_errors in quality.items():
        if cat_errors:
            if args.strict and category != "code_block_quality":
                errors.extend(cat_errors)
            else:
                warnings.extend(cat_errors)

    result: dict[str, object] = {
        "job_root": str(job_root),
        "markdown": str(markdown),
        "ok": not errors,
        "errors": errors,
    }
    if warnings:
        result["warnings"] = warnings
    if warnings and not errors:
        result["ok"] = True

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
