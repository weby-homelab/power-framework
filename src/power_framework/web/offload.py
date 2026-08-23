"""Bounded execution bridge for synchronous POWER ApplicationService calls."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Any

import anyio

from .errors import PowerCallTimeoutError, public_http_exception

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import Request

    from .config import Settings


async def run_power_call[R](
    request: Request,
    settings: Settings,
    function: Callable[..., R],
    /,
    *args: Any,
    timeout_seconds: float | None = None,
    **kwargs: Any,
) -> R:
    """Run one blocking POWER call in a bounded, cancellation-aware worker slot."""
    limiter = getattr(request.app.state, "power_call_limiter", None)
    if limiter is None:
        limiter = anyio.CapacityLimiter(settings.power_call_max_concurrency)

    call = partial(function, *args, **kwargs)
    timeout = timeout_seconds or settings.power_call_timeout_seconds
    try:
        return await asyncio.wait_for(
            anyio.to_thread.run_sync(
                call,
                abandon_on_cancel=True,
                limiter=limiter,
            ),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise PowerCallTimeoutError from exc
    except Exception as exc:
        raise public_http_exception(exc) from exc


__all__ = ["run_power_call"]
