"""Tests for Phase 5E Living Retrieval Regression Benchmark."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import pytest

from power_framework.core.application import ApplicationService
from power_framework.core.vault_storage import existing_vault_cache_dir
from scripts.run_living_benchmark import (
    DEFAULT_DATASET_DIR,
    _gates_pass,
    _hash_benchmark_storage,
    load_dataset,
    run_living_benchmark,
)

if TYPE_CHECKING:
    from pathlib import Path


def _assert_all_invariants_zero(mode_report: dict[str, Any]) -> None:
    assert mode_report["all_invariants_zero"] is True, mode_report["invariants"]
    for key, val in mode_report["invariants"].items():
        assert val == 0, f"Expected invariant {key} == 0, got {val}"


def test_living_dataset_integrity() -> None:
    """Dataset is complete, anonymized, covers core/daily/semantic/security and UA/EN/MIXED."""
    canonical, lexicon, queries = load_dataset(DEFAULT_DATASET_DIR)

    assert len(queries) >= 30
    groups = {str(q["group"]) for q in queries}
    assert {"core", "daily_work", "semantic_paraphrase", "security"} <= groups
    languages = {str(q["language"]) for q in queries}
    assert {"UA", "EN", "MIXED"} <= languages

    clusters = lexicon.get("clusters", {})
    assert len(clusters) >= 15
    assert int(lexicon.get("dimension", 0)) == 1024

    canonical_ids = (
        {f"task:{t['task_id']}" for t in canonical.get("tasks", [])}
        | {f"decision:{d['decision_id']}" for d in canonical.get("decisions", [])}
        | {f"project:{p['project_id']}" for p in canonical.get("projects", [])}
    )
    corpus_dir = DEFAULT_DATASET_DIR / "corpus"

    for q in queries:
        refs = [
            *q.get("expected_relevant", []),
            *q.get("expected_exclusions", []),
            *(
                [q["expected_authority_winner"]]
                if q.get("expected_authority_winner") is not None
                else []
            ),
        ]
        for ref in refs:
            ref_str = str(ref)
            if ref_str.startswith(("task:", "decision:", "project:")):
                assert ref_str in canonical_ids, f"Missing canonical fixture {ref_str}"
            else:
                assert (corpus_dir / ref_str).is_file(), f"Missing corpus note {ref_str}"


def test_living_benchmark_fast_mode_invariants_and_quality() -> None:
    """FAST lexical + canonical mode passes all hard invariants and baseline recall floors."""
    report = run_living_benchmark(
        DEFAULT_DATASET_DIR,
        modes=("FAST",),
        embedder_mode="hermetic",
    )
    fast = report["modes"]["FAST"]
    _assert_all_invariants_zero(fast)

    summary = fast["summary"]
    assert summary["dense_used_count"] == 0
    assert summary["recall_at_5"] >= 0.55
    assert summary["mrr"] >= 0.50
    assert summary["ndcg_at_10"] >= 0.55
    assert fast["by_group"]["core"]["recall_at_5"] >= 0.80


def test_living_benchmark_detects_query_side_cache_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    caller_cache = tmp_path / "caller-cache"
    caller_db = tmp_path / "caller.db"
    caller_db.write_bytes(b"untouched")
    monkeypatch.setenv("XDG_CACHE_HOME", str(caller_cache))
    monkeypatch.setenv("POWER_SEARCH_DB", str(caller_db))
    original = ApplicationService.compile_context
    written_files: list[Path] = []

    def compile_with_cache_write(self: ApplicationService, **kwargs: Any) -> Any:
        result = original(self, **kwargs)
        cache = existing_vault_cache_dir(vault)
        assert cache is not None
        marker = cache / "unexpected-query-write"
        # The second read restores the original file tree. The first read must
        # still count as a violation.
        if marker.exists():
            marker.unlink()
        else:
            marker.write_bytes(b"query wrote outside the vault")
            written_files.append(marker)
        return result

    monkeypatch.setattr(ApplicationService, "compile_context", compile_with_cache_write)
    report = run_living_benchmark(modes=("FAST",), vault_dir=vault)

    assert report["modes"]["FAST"]["invariants"]["query_side_writes"] == report["query_count"]
    assert _gates_pass(report)[0] is False
    assert written_files
    assert not written_files[0].parent.exists()
    assert not caller_cache.exists()
    assert caller_db.read_bytes() == b"untouched"
    assert os.environ["XDG_CACHE_HOME"] == str(caller_cache)
    assert os.environ["POWER_SEARCH_DB"] == str(caller_db)


def test_living_benchmark_hashes_nonempty_sqlite_wal(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    cache = tmp_path / "cache"
    vault.mkdir()
    cache.mkdir()
    (cache / "index.db").write_bytes(b"database")
    (cache / "index.db-shm").write_bytes(b"read coordination")
    wal = cache / "index.db-wal"
    wal.touch()

    before = _hash_benchmark_storage(vault, cache)
    assert set(before[1]) == {"index.db"}
    wal.write_bytes(b"pending database writes")
    assert set(_hash_benchmark_storage(vault, cache)[1]) == {"index.db", "index.db-wal"}


def test_living_benchmark_balanced_real_dense_beats_fast_on_semantic_paraphrases() -> None:
    """BALANCED executes real Stage 3 dense search, preserves invariants, and beats FAST on paraphrases."""
    pytest.importorskip("numpy")

    report = run_living_benchmark(
        DEFAULT_DATASET_DIR,
        modes=("FAST", "BALANCED"),
        embedder_mode="hermetic",
    )
    fast = report["modes"]["FAST"]
    balanced = report["modes"]["BALANCED"]

    _assert_all_invariants_zero(fast)
    _assert_all_invariants_zero(balanced)

    bal_summary = balanced["summary"]
    fast_summary = fast["summary"]
    assert bal_summary["dense_used_count"] == report["query_count"]
    assert bal_summary["degraded_count"] == 0
    assert bal_summary["recall_at_5"] >= 0.85
    assert bal_summary["mrr"] >= 0.80
    assert bal_summary["ndcg_at_10"] >= 0.85
    assert bal_summary["recall_at_5"] >= fast_summary["recall_at_5"]

    fast_sem = fast["by_group"]["semantic_paraphrase"]["recall_at_5"]
    bal_sem = balanced["by_group"]["semantic_paraphrase"]["recall_at_5"]
    assert bal_sem > fast_sem
    assert bal_sem >= 0.85
