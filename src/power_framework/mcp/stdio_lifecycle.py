"""Lifecycle diagnostics and EOF-draining wrappers for native stdio MCP transport."""

from __future__ import annotations

import contextlib
import logging
import math
import os
import sys
from collections import Counter
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import anyio
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCError, JSONRPCRequest, JSONRPCResponse

from power_framework.core import __version__

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

logger = logging.getLogger(__name__)

DEFAULT_EOF_DRAIN_TIMEOUT_S = 30.0


def eof_drain_timeout_seconds() -> float:
    """Return the bounded time in seconds to drain in-flight requests after stdin EOF."""
    raw = os.getenv("POWER_MCP_EOF_DRAIN_TIMEOUT_S")
    if raw is None or not raw.strip():
        return DEFAULT_EOF_DRAIN_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "Ignoring invalid POWER_MCP_EOF_DRAIN_TIMEOUT_S=%r; using %.1fs",
            raw,
            DEFAULT_EOF_DRAIN_TIMEOUT_S,
        )
        return DEFAULT_EOF_DRAIN_TIMEOUT_S
    if not math.isfinite(value) or value < 0.0:
        logger.warning(
            "Ignoring out-of-range POWER_MCP_EOF_DRAIN_TIMEOUT_S=%r; using %.1fs",
            raw,
            DEFAULT_EOF_DRAIN_TIMEOUT_S,
        )
        return DEFAULT_EOF_DRAIN_TIMEOUT_S
    return value


def write_lifecycle_stderr(message: str, *, warning: bool = False) -> None:
    """Emit a content-free, path-free lifecycle diagnostic line on stderr."""
    if warning:
        logger.warning("%s", message)
    else:
        logger.info("%s", message)
    with contextlib.suppress(OSError):
        sys.stderr.write(f"{message}\n")
        sys.stderr.flush()


@asynccontextmanager
async def power_mcp_lifespan(_server: Any) -> AsyncIterator[None]:
    """Emit explicit startup and shutdown diagnostics for the stdio server lifespan."""
    write_lifecycle_stderr(
        f"power-mcp lifecycle: starting (version={__version__}, transport=stdio)"
    )
    try:
        yield
    finally:
        write_lifecycle_stderr(
            f"power-mcp lifecycle: stopped (version={__version__}, transport=stdio)"
        )


@asynccontextmanager
async def drain_stdio_streams(
    read_stream: MemoryObjectReceiveStream[SessionMessage | Exception],
    write_stream: MemoryObjectSendStream[SessionMessage],
    *,
    drain_timeout_s: float | None = None,
) -> AsyncIterator[
    tuple[
        MemoryObjectReceiveStream[SessionMessage | Exception],
        MemoryObjectSendStream[SessionMessage],
    ]
]:
    """Keep the server dispatcher alive across stdin EOF until in-flight tool responses land."""
    timeout = (
        eof_drain_timeout_seconds() if drain_timeout_s is None else max(0.0, float(drain_timeout_s))
    )
    inner_read_send, inner_read_recv = anyio.create_memory_object_stream[
        SessionMessage | Exception
    ](0)
    inner_write_send, inner_write_recv = anyio.create_memory_object_stream[SessionMessage](0)

    pending: Counter[int | str] = Counter()
    stdin_eof = False
    drain_event: anyio.Event | None = None
    read_scope = anyio.CancelScope()

    async def forward_reads() -> None:
        nonlocal stdin_eof, drain_event
        with read_scope:
            try:
                async with inner_read_send, read_stream:
                    async for item in read_stream:
                        if isinstance(item, SessionMessage) and isinstance(
                            item.message, JSONRPCRequest
                        ):
                            pending[item.message.id] += 1
                        await inner_read_send.send(item)
                    stdin_eof = True
                    if pending and timeout > 0.0:
                        write_lifecycle_stderr(
                            f"power-mcp lifecycle: draining {sum(pending.values())} in-flight "
                            f"request(s) after stdin EOF (timeout={timeout:.1f}s)"
                        )
                        drain_event = anyio.Event()
                        with anyio.move_on_after(timeout) as scope:
                            await drain_event.wait()
                        if scope.cancelled_caught and pending:
                            write_lifecycle_stderr(
                                f"power-mcp lifecycle: drain timed out with "
                                f"{sum(pending.values())} in-flight request(s) remaining",
                                warning=True,
                            )
            except (anyio.BrokenResourceError, anyio.ClosedResourceError):
                await anyio.lowlevel.checkpoint()

    async def forward_writes() -> None:
        try:
            async with inner_write_recv:
                async for item in inner_write_recv:
                    await write_stream.send(item)
                    msg = item.message
                    if isinstance(msg, (JSONRPCResponse, JSONRPCError)):
                        req_id = msg.id
                        if req_id is not None and req_id in pending:
                            pending[req_id] -= 1
                            if pending[req_id] <= 0:
                                del pending[req_id]
                        if stdin_eof and not pending and drain_event is not None:
                            drain_event.set()
                    elif isinstance(msg, JSONRPCRequest) and stdin_eof and drain_event is not None:
                        # Server-initiated requests cannot receive a reply once stdin is at EOF.
                        drain_event.set()
        except (anyio.BrokenResourceError, anyio.ClosedResourceError):
            await anyio.lowlevel.checkpoint()
        finally:
            if drain_event is not None:
                drain_event.set()
            with anyio.CancelScope(shield=True):
                await write_stream.aclose()

    async with anyio.create_task_group() as tg:
        tg.start_soon(forward_reads)
        tg.start_soon(forward_writes)
        try:
            yield inner_read_recv, inner_write_send
        finally:
            with anyio.CancelScope(shield=True):
                await inner_read_recv.aclose()
                await inner_write_send.aclose()
            read_scope.cancel()
