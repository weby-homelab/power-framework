"""Opt-in, content-free timing spans for retrieval diagnostics."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class TimingReceipt:
    """Aggregate inclusive component timings without query or note content."""

    totals_ms: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, name: str, elapsed_ms: float) -> None:
        """Record one inclusive span."""
        self.totals_ms[name] += elapsed_ms
        self.counts[name] += 1

    def as_dict(self) -> dict[str, object]:
        """Return a stable, content-free diagnostic object."""
        return {
            "schema_version": "power.retrieval-timings.v1",
            "inclusive": True,
            "components_ms": {
                name: round(self.totals_ms[name], 3) for name in sorted(self.totals_ms)
            },
            "span_counts": {name: self.counts[name] for name in sorted(self.counts)},
        }


_CURRENT: ContextVar[TimingReceipt | None] = ContextVar("power_timing_receipt", default=None)


@contextmanager
def collect_timings() -> Iterator[TimingReceipt]:
    """Collect timing spans in the current execution context."""
    receipt = TimingReceipt()
    token = _CURRENT.set(receipt)
    try:
        yield receipt
    finally:
        _CURRENT.reset(token)


@contextmanager
def timing_span(name: str) -> Iterator[None]:
    """Record an inclusive span when a diagnostic collector is active."""
    receipt = _CURRENT.get()
    if receipt is None:
        yield
        return

    started = perf_counter()
    try:
        yield
    finally:
        receipt.add(name, (perf_counter() - started) * 1000)
