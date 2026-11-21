from __future__ import annotations

import pytest

from power_framework.core.index_freshness import index_freshness


@pytest.mark.parametrize(
    ("seconds", "status"),
    [
        (None, "unknown"),
        (-1.0, "unknown"),
        (0.0, "fresh"),
        (3_599.9, "fresh"),
        (3_600.0, "stale"),
        (86_399.9, "stale"),
        (86_400.0, "critical"),
    ],
)
def test_index_freshness_thresholds(seconds: float | None, status: str) -> None:
    assert index_freshness(seconds) == status
