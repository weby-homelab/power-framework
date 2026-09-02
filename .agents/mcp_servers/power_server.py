#!/usr/bin/env python3
"""Deprecated compatibility shim for the canonical ``power-mcp`` launcher.

It intentionally loads no dotenv file and performs no configuration fallback.
New integrations must invoke the packaged ``power-mcp`` console script directly.
"""

from power_framework.mcp.entrypoint import main

if __name__ == "__main__":
    raise SystemExit(main())
