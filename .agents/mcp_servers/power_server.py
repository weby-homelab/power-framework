#!/usr/bin/env python3
"""
P.O.W.E.R. MCP Server entry-point for OpenCode/Antigravity CLI.
This script launches the official MCP SDK v2 server from power_framework.mcp.

Version: 3.6.7
Updated: 2026-08-21
"""

import os

# Load .env from geminicli workspace
_env_path = "/root/geminicli/.env"
if os.path.isfile(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                _v = _v.strip().strip('"').strip("'")
                if _k not in os.environ:
                    os.environ[_k] = _v

# Run the public power-mcp entry point.
from power_framework.mcp.entrypoint import main  # type: ignore  # noqa: E402

if __name__ == "__main__":
    main()
