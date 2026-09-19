"""Shared query execution core for development and future Stage-A runners."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from power_framework.core.evaluation_execution import QueryOnlyRecord


@dataclass(frozen=True)
class CommonQueryObservation:
    """Observed runtime calls; no ground-truth or metric inputs are accepted."""

    legacy_envelope: Any
    shadow_envelope: Any
    shadow_repeat_envelope: Any
    legacy_latency_ms: float
    shadow_latency_ms: float


def execute_runtime_query(
    app: Any,
    query: QueryOnlyRecord,
) -> CommonQueryObservation:
    """Run legacy and shadow retrieval for one query-only input."""

    legacy_started = time.perf_counter()
    legacy_envelope = app.retrieve(query=query.query, max_results=20)
    legacy_latency_ms = (time.perf_counter() - legacy_started) * 1000.0

    shadow_started = time.perf_counter()
    shadow_envelope = app.compile_context(
        query=query.query,
        intent=query.intent,
        budget_class=query.budget_class,
    )
    shadow_latency_ms = (time.perf_counter() - shadow_started) * 1000.0
    shadow_repeat_envelope = app.compile_context(
        query=query.query,
        intent=query.intent,
        budget_class=query.budget_class,
    )
    return CommonQueryObservation(
        legacy_envelope=legacy_envelope,
        shadow_envelope=shadow_envelope,
        shadow_repeat_envelope=shadow_repeat_envelope,
        legacy_latency_ms=legacy_latency_ms,
        shadow_latency_ms=shadow_latency_ms,
    )


__all__ = ["CommonQueryObservation", "execute_runtime_query"]
