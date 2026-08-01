"""Materialize a development-only de-identified corpus as an OKF vault.

The evaluator consumes the same relative document IDs as frozen qrels. This
helper intentionally refuses sealed rows and writes only reviewed corpus text;
raw judgments, qrels and source provenance never enter the generated vault.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SAFE_DOCUMENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read JSONL objects without logging their content."""
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"corpus row {line_number} is not an object")
            rows.append(value)
    return rows


def build(corpus: Path, output: Path) -> int:
    """Write one validated OKF note per development corpus document."""
    records = load_jsonl(corpus)
    output.mkdir(parents=True, exist_ok=True)
    written = 0
    for row in records:
        document_id = row.get("document_id")
        if (
            not isinstance(document_id, str)
            or SAFE_DOCUMENT_ID.fullmatch(document_id) is None
            or row.get("split") != "development"
        ):
            raise ValueError("corpus contains a non-development or unsafe document row")
        title = row.get("title")
        text = row.get("text")
        if not isinstance(title, str) or not isinstance(text, str) or not text.strip():
            raise ValueError(f"document {document_id} is missing title or text")

        note = (
            "---\n"
            "type: Resource\n"
            f"title: {json.dumps(title, ensure_ascii=False)}\n"
            'description: "De-identified M2 development evaluation document"\n'
            'okf_version: "0.2"\n'
            "memory:\n"
            "  kind: semantic\n"
            "timestamp: 2026-08-01T00:00:00\n"
            "---\n\n"
            f"{text.strip()}\n"
        )
        (output / f"{document_id}.md").write_text(note, encoding="utf-8")
        written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sys.stdout.write(f"built_development_notes={build(args.corpus, args.output)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
