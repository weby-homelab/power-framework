#!/usr/bin/env python3
"""Generate the public OKF metadata JSON Schema from the typed runtime model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from power_framework.core.models import OKFMetadata

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent.parent / "docs" / "schemas" / "okf-metadata-v1.json"
)


def build_schema() -> dict[str, Any]:
    """Return the versioned public schema with stable identity metadata."""
    schema = OKFMetadata.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://weby-homelab.github.io/power-framework/schemas/okf-metadata-v1.json"
    schema["x-power-schema-version"] = "power.okf-metadata.v1"
    return schema


def main() -> int:
    """Write the generated schema and report its destination."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"OKF schema written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
