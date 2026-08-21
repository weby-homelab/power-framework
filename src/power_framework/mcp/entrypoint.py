"""Public ``power-mcp`` console entry point and fail-closed preflight."""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

from power_framework.core import __version__

from .preflight import require_configured_vault_root

if TYPE_CHECKING:
    from collections.abc import Sequence


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="power-mcp",
        description="Run the local POWER MCP server over stdio or the explicitly configured loopback HTTP profile.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"power-mcp {__version__}",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("preflight",),
        help="Run a read-only vault-root preflight without starting the server.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``power-mcp`` or its read-only preflight command."""
    args = _build_parser().parse_args(argv)
    try:
        vault_root = require_configured_vault_root()
    except RuntimeError as exc:
        sys.stderr.write(f"power-mcp preflight failed: {exc}\n")
        return 2

    if args.command == "preflight":
        payload = json.dumps(
            {
                "status": "ok",
                "transport": "stdio",
                "vault_root": str(vault_root),
                "power_version": __version__,
            },
            sort_keys=True,
        )
        sys.stdout.write(f"{payload}\n")
        return 0

    # Keep --version and preflight usable in the lean FTS-only installation;
    # the official SDK is loaded only when the server process is requested.
    from .power_server import run

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
