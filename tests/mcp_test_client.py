"""Official MCP SDK v2 subprocess fixtures used by protocol contract tests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from mcp import ClientSession, StdioServerParameters, stdio_client, types

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _stdio_server_parameters(config: dict[str, Any]) -> StdioServerParameters:
    """Convert the documented client shape into SDK subprocess parameters."""
    if "mcpServers" in config:
        server = config["mcpServers"]["power"]
        environment = server["env"]
    elif "mcp_servers" in config:
        server = config["mcp_servers"]["power"]
        environment = server["env"]
    else:
        raise AssertionError("test config must contain mcpServers or mcp_servers")
    return StdioServerParameters(
        command=server["command"],
        args=server["args"],
        env=environment,
    )


@asynccontextmanager
async def stdio_session(
    config: dict[str, Any],
    *,
    mode: str = "legacy",
) -> AsyncIterator[ClientSession]:
    """Connect to a real subprocess using legacy or 2026-era handshake mode."""
    parameters = _stdio_server_parameters(config)
    async with (
        stdio_client(parameters) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        if mode == "legacy":
            await session.initialize()
        else:
            discovered = await session.send_discover(mode)
            session.adopt(types.DiscoverResult.model_validate(discovered))
        yield session
