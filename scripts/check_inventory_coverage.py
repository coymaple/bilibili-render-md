#!/usr/bin/env python3
"""Cross-check a written Markdown delivery against the chunk inventory.

Mechanical only: every term / command / code listed in the inventory must
appear somewhere in the document (after case/whitespace normalization).
Items the model recorded in `points` are not re-checked here; the model is
expected to have written them while drafting. Output is a JSON gap report
per chunk that the model can read to patch the missing coverage.

This is a checklist, not a quality judgment: it verifies the transcript's
named content was addressed, without scoring how well it was explained.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s.lower().replace("_", "").replace("-", ""))


def norm_loose(s: str) -> str:
    return re.sub(r"\s+", "", s.lower())


def norm_code(s: str) -> str:
    return re.sub(r"[\s{}\"'\";,=:\.`]", "", s.lower())


def check_entry(entry: dict[str, Any], doc_norm: str, doc_loose: str, doc_code: str) -> dict[str, Any]:
    chunk_id = entry["chunk"]
    term_items: list[dict[str, str]] = []
    for term in entry.get("terms", []):
        if norm(term) and norm(term) in doc_norm:
            term_items.append({"value": term, "covered": True})
        else:
            term_items.append({"value": term, "covered": False})

    command_items: list[dict[str, str]] = []
    for command in entry.get("commands", []):
        if norm_loose(command) in doc_loose:
            command_items.append({"value": command, "covered": True})
        else:
            command_items.append({"value": command, "covered": False})

    code_items: list[dict[str, str]] = []
    for code in entry.get("codes", []):
        if norm_code(code) and norm_code(code) in doc_code:
            code_items.append({"value": code, "covered": True})
        else:
            code_items.append({"value": code, "covered": False})

    uncovered = {
        "terms": [item["value"] for item in term_items if not item["covered"]],
        "commands": [item["value"] for item in command_items if not item["covered"]],
        "codes": [item["value"] for item in code_items if not item["covered"]],
    }
    return {
        "chunk": chunk_id,
        "time_range": f"{entry.get('start')}--{entry.get('end')}",
        "density": entry.get("density"),
        "sparse": entry.get("density") == "sparse",
        "total_checked": len(term_items) + len(command_items) + len(code_items),
        "covered_count": sum(i["covered"] for i in term_items + command_items + code_items),
        "items": {
            "terms": term_items,
            "commands": command_items,
            "codes": code_items,
        },
        "uncovered": uncovered,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=None,
                        help="inventory.json path (default: <job-root>/work/transcript/inventory.json)")
    parser.add_argument("--job-root", type=Path, default=None)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--skip", action="store_true", help="skip the cross-check and exit")
    args = parser.parse_args()

    if args.skip:
        print("[check_inventory_coverage] skipped")
        return 0

    if args.inventory is None:
        if args.job_root is None:
            raise SystemExit("provide --inventory or --job-root")
        args.inventory = args.job_root.expanduser().resolve() / "work" / "transcript" / "inventory.json"
    else:
        args.inventory = args.inventory.expanduser().resolve()

    if not args.inventory.is_file():
        raise SystemExit(f"inventory not found: {args.inventory} (run scripts/build_inventory.py first)")

    markdown_path = args.markdown.expanduser().resolve()
    if not markdown_path.is_file():
        raise SystemExit(f"markdown not found: {markdown_path}")

    inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    markdown = markdown_path.read_text(encoding="utf-8-sig")
    doc_norm = norm(markdown)
    doc_loose = norm_loose(markdown)
    doc_code = norm_code(markdown)

    results = [check_entry(entry, doc_norm, doc_loose, doc_code) for entry in inventory]

    gap_chunks = [r for r in results if r["covered_count"] < r["total_checked"]]
    ok = not gap_chunks

    report: dict[str, Any] = {
        "ok": ok,
        "chunks_checked": len(results),
        "gap_chunks": [r["chunk"] for r in gap_chunks],
        "chunks": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())