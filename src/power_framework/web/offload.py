"""Bounded execution bridge for synchronous POWER ApplicationService calls."""

from __future__ import annotations

import asyncio
import contextlib
from functools import partial
from typing import TYPE_CHECKING, Any

import anyio

from .errors import (
    PowerCallCompletedAfterCancellationError,
    PowerCallCompletedAfterDeadlineError,
    PowerCallTimeoutError,
    public_http_exception,
    request_id_for,
)

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
    mutation: bool = False,
    **kwargs: Any,
) -> R:
    """Run one blocking POWER call in a bounded, cancellation-aware worker slot."""
    limiter = getattr(request.app.state, "power_call_limiter", None)
    if limiter is None:
        raise RuntimeError("shared POWER worker limiter is not configured")

    timeout = settings.power_call_timeout_seconds if timeout_seconds is None else timeout_seconds
    if timeout <= 0:
        raise ValueError("timeout_seconds must be positive")

    binder = getattr(getattr(function, "__self__", None), "bind_request_budget", None)
    if callable(binder):
        binder(request_id_for(request), timeout)

    call = partial(function, *args, **kwargs)
    worker = asyncio.create_task(
        anyio.to_thread.run_sync(
            call,
            abandon_on_cancel=True,
            limiter=limiter,
        )
    )
    try:
        return await asyncio.wait_for(asyncio.shield(worker), timeout=timeout)
    except TimeoutError as exc:
        if mutation:
            try:
                await _join_worker(worker)
            except Exception as worker_error:
                raise public_http_exception(worker_error) from worker_error
            raise PowerCallCompletedAfterDeadlineError from exc
        worker.add_done_callback(_consume_worker_result)
        raise PowerCallTimeoutError from exc
    except asyncio.CancelledError:
        if mutation:
            try:
                await _join_worker(worker)
            except Exception as worker_error:
                raise public_http_exception(worker_error) from worker_error
            raise PowerCallCompletedAfterCancellationError from None
        worker.add_done_callback(_consume_worker_result)
        raise
    except Exception as exc:
        raise public_http_exception(exc) from exc


async def _join_worker[R](worker: asyncio.Task[R]) -> R:
    """Observe a worker to completion without abandoning a mutation."""
    while not worker.done():
        try:
            await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            # Keep the mutation joined; the cancellation is re-raised by the
            # caller after the worker's outcome is known.
            continue
    return worker.result()


def _consume_worker_result[R](worker: asyncio.Task[R]) -> None:
    """Consume a detached read worker result to avoid unhandled-task warnings."""
    with contextlib.suppress(BaseException):
        worker.result()


__all__ = ["run_power_call"]
