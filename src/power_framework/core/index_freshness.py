"""Time-based advisory policy for a selected search index."""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pathlib import Path

FRESH_UNDER_SECONDS = 3_600
CRITICAL_AT_SECONDS = 86_400


def index_age_seconds(path: Path | None) -> float | None:
    if path is None:
        return None
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


def index_freshness(age: float | None) -> Literal["fresh", "stale", "critical", "unknown"]:
    if age is None or not math.isfinite(age) or age < 0:
        return "unknown"
    if age < FRESH_UNDER_SECONDS:
        return "fresh"
    if age < CRITICAL_AT_SECONDS:
        return "stale"
    return "critical"
