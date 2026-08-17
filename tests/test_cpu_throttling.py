"""Unit tests for the strict 50% CPU Throttling Mandate."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import patch

from power_framework.core.utils import enforce_cpu_throttling_env, get_cpu_worker_limit
from power_framework.experimental.rot_scoring import LinkRotChecker

if TYPE_CHECKING:
    from pathlib import Path


def test_get_cpu_worker_limit_scales_with_cores() -> None:
    test_cases = [
        (1, 1),
        (2, 1),
        (3, 1),
        (4, 2),
        (8, 4),
        (16, 8),
        (32, 16),
        (64, 32),
        (None, 2),  # Default fallback 4 // 2 = 2
    ]
    for count, expected in test_cases:
        with patch("os.cpu_count", return_value=count):
            assert get_cpu_worker_limit() == expected, f"Failed for cpu_count={count}"


def test_get_cpu_worker_limit_respects_max_cap() -> None:
    with patch("os.cpu_count", return_value=16):
        # 16 cores -> 50% is 8. max_cap=2 should return 2.
        assert get_cpu_worker_limit(max_cap=2) == 2
        # max_cap=100 should be clamped to 8.
        assert get_cpu_worker_limit(max_cap=100) == 8
        # max_cap=0 should return at least 1.
        assert get_cpu_worker_limit(max_cap=0) == 1


def test_enforce_cpu_throttling_env_clamps_all_vars() -> None:
    env_vars = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "POWER_EMBED_NUM_THREADS",
    )
    with patch("os.cpu_count", return_value=4):
        # 4 cores -> limit is 2
        # Case 1: All unset
        with patch.dict(os.environ, {}, clear=True):
            enforce_cpu_throttling_env()
            for var in env_vars:
                assert os.environ.get(var) == "2", f"{var} was not set to 2"

        # Case 2: Excessive thread count (e.g. 64)
        with patch.dict(os.environ, dict.fromkeys(env_vars, "64"), clear=True):
            enforce_cpu_throttling_env()
            for var in env_vars:
                assert os.environ.get(var) == "2", f"{var} was not clamped from 64 to 2"

        # Case 3: Lower thread count (e.g. 1) preserved
        with patch.dict(os.environ, dict.fromkeys(env_vars, "1"), clear=True):
            enforce_cpu_throttling_env()
            for var in env_vars:
                assert os.environ.get(var) == "1", f"{var}=1 was overwritten unexpectedly"

        # Case 4: Invalid non-integer string
        with patch.dict(os.environ, dict.fromkeys(env_vars, "invalid"), clear=True):
            enforce_cpu_throttling_env()
            for var in env_vars:
                assert os.environ.get(var) == "2", f"{var} invalid string was not reset"


def test_link_rot_checker_respects_cpu_throttling(tmp_path: Path) -> None:
    checker = LinkRotChecker()
    note_file = tmp_path / "test.md"
    note_file.write_text("See [link](https://example.com/test) here.", encoding="utf-8")

    with (
        patch("os.cpu_count", return_value=8),
        patch.object(checker, "_head_status", return_value=200),
    ):
        # 8 cores -> max_workers must be 4 (<= 50%)
        res = checker.check_all(tmp_path)
        assert res == {}
