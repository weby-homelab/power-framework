"""Check the installed native CLI and MCP process, without starting Web."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from profile_acceptance import MARKER, mcp_acceptance, run


def main(bin_dir: Path, vault: Path, tag: str) -> None:
    """Use disposable storage, with no checkout or token in the server environment."""
    power, mcp = bin_dir / "power", bin_dir / "power-mcp"
    env = {
        "PATH": os.defpath,
        "HOME": str(vault.parent / "core-proof-home"),
        "POWER_MODEL_OFFLINE": "1",
        "HF_HUB_OFFLINE": "1",
        "POWER_VAULT_DIR": str(vault),
    }
    Path(env["HOME"]).mkdir(mode=0o700)
    for launcher in (power, mcp):
        if tag.removeprefix("v") not in run([str(launcher), "--version"], env=env).split():
            raise ValueError(f"unexpected version for {launcher.name}")
    run([str(power), "init", str(vault)], env=env)
    (vault / "00_Inbox" / "acceptance.md").write_text(
        "---\ntype: Resource\ntitle: Native acceptance\ndescription: FTS readback\n"
        "tags: [acceptance]\ntimestamp: 2026-01-01T00:00:00Z\n---\n\n" + MARKER + "\n",
        encoding="utf-8",
    )
    run([str(power), "sync", str(vault), "--fts-only", "--strict"], env=env)
    if MARKER not in run([str(power), "search", str(vault), MARKER, "--mode", "fts"], env=env):
        raise ValueError("installed CLI did not find the disposable fixture")
    asyncio.run(mcp_acceptance(mcp, vault, env))
    Path("dist/power-profile-acceptance.json").write_text(
        json.dumps({"profile": "core-cli-mcp-v1", "tag": tag, "cli_fts": True, "mcp_stdio": True})
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
