"""Compatibility module entry point; native installs should use ``power-mcp``."""

from __future__ import annotations

from .power_server import run

if __name__ == "__main__":
    run()
