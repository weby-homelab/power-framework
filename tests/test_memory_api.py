from __future__ import annotations

import json

import pytest

from power_framework.core import memory_api
from power_framework.core.memory_api import (
    apply_change,
    propose_change,
    read_history,
    validate_state,
)
from power_framework.core.searcher import search_vault


def test_memory_transaction_requires_approval_and_records_history(sample_vault):
    search_marker = "closed-memory-search-marker"
    proposal = propose_change(
        sample_vault,
        "01_Projects/Transaction.md",
        '---\ntype: Project\ntitle: "Transaction"\ndescription: "A transaction"\ntimestamp: 2026-07-29T00:00:00Z\n---\n\n# Transaction\n\n'
        + search_marker
        + "\n",
    )
    with pytest.raises(PermissionError):
        apply_change(sample_vault, proposal, approved=False)
    receipt = apply_change(sample_vault, proposal, approved=True)
    assert receipt["path"] == "01_Projects/Transaction.md"
    assert receipt["proposal_id"] == proposal["proposal_id"]
    assert read_history(sample_vault)[0]["after_sha256"] == receipt["after_sha256"]
    assert receipt["search_mode"] == "fts"
    assert receipt["notes_excluded"] == "0"
    assert receipt["receipt_schema"] == "power.receipt.v1"
    assert len(receipt["trace_id"]) == 32
    assert len(receipt["span_id"]) == 16
    assert receipt["status"] == "ok"
    assert float(receipt["duration_ms"]) >= 0
    assert search_vault(sample_vault, search_marker, max_results=5, mode="fts")[0].rel_path == (
        "01_Projects/Transaction.md"
    )
    assert validate_state(sample_vault) is True


def test_memory_apply_replay_with_same_idempotency_key_is_not_a_duplicate(sample_vault):
    proposal = propose_change(
        sample_vault,
        "01_Projects/Idempotent.md",
        '---\ntype: Project\ntitle: "Idempotent"\ndescription: "idempotent"\ntimestamp: 2026-07-29T00:00:00Z\n---\nonce\n',
    )
    first = apply_change(sample_vault, proposal, approved=True)
    replay = apply_change(sample_vault, proposal, approved=True)

    assert proposal["idempotency_key"] == first["idempotency_key"]
    assert replay == first
    assert len(read_history(sample_vault)) == 1


def test_memory_transaction_rejects_stale_proposal(sample_vault):
    target = sample_vault / "01_Projects" / "TestProject.md"
    proposal = propose_change(
        sample_vault,
        "01_Projects/TestProject.md",
        '---\ntype: Project\ntitle: "Replacement"\ndescription: "replacement"\n'
        "timestamp: 2026-07-29T00:00:00Z\n---\n\nreplacement\n",
    )
    target.write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="stale"):
        apply_change(sample_vault, proposal, approved=True)


def test_memory_transaction_rejects_invalid_content_without_writing(sample_vault):
    with pytest.raises(ValueError, match="invalid or missing OKF metadata"):
        propose_change(sample_vault, "01_Projects/Invalid.md", "not a note")

    assert not (sample_vault / "01_Projects" / "Invalid.md").exists()
    assert read_history(sample_vault) == []
    assert not (sample_vault / ".power" / "proposals").exists()


def test_memory_proposal_is_durable_and_content_addressed(sample_vault):
    content = (
        '---\ntype: Project\ntitle: "Durable proposal"\n'
        'description: "durable proposal"\ntimestamp: 2026-07-29T00:00:00Z\n'
        "---\n\nproposal-marker\n"
    )
    proposal = propose_change(sample_vault, "01_Projects/Durable.md", content)
    proposal_path = sample_vault / ".power" / "proposals" / f"{proposal['proposal_id']}.json"

    assert not (sample_vault / "01_Projects" / "Durable.md").exists()
    assert (
        json.loads(proposal_path.read_text(encoding="utf-8"))["proposal_id"]
        == proposal["proposal_id"]
    )
    assert propose_change(sample_vault, "01_Projects/Durable.md", content) == proposal


def test_memory_apply_rejects_missing_durable_proposal(sample_vault):
    content = (
        '---\ntype: Project\ntitle: "Missing durable"\n'
        'description: "missing durable"\ntimestamp: 2026-07-29T00:00:00Z\n'
        "---\n"
    )
    proposal = propose_change(sample_vault, "01_Projects/MissingDurable.md", content)
    (sample_vault / ".power" / "proposals" / f"{proposal['proposal_id']}.json").unlink()

    with pytest.raises(ValueError, match="not durable"):
        apply_change(sample_vault, proposal, approved=True)


@pytest.mark.parametrize(
    ("field", "value"),
    [("path", 42), ("content", None), ("before_sha256", "short"), ("after_sha256", "short")],
)
def test_memory_transaction_rejects_malformed_proposal_schema(sample_vault, field, value):
    proposal = {
        "path": "01_Projects/Malformed.md",
        "content": "valid content",
        "before_sha256": "0" * 64,
        "after_sha256": "0" * 64,
    }
    proposal[field] = value

    with pytest.raises(ValueError, match="proposal"):
        apply_change(sample_vault, proposal, approved=True)

    assert not (sample_vault / "01_Projects" / "Malformed.md").exists()
    assert read_history(sample_vault) == []


def test_memory_transaction_restores_note_when_write_fails(sample_vault, monkeypatch):
    proposal = propose_change(
        sample_vault,
        "01_Projects/WriteFailure.md",
        '---\ntype: Project\ntitle: "Write failure"\ndescription: "write failure"\n'
        "timestamp: 2026-07-29T00:00:00Z\n---\n",
    )

    def fail_write(*args: object, **kwargs: object) -> None:
        raise OSError("write failed")

    monkeypatch.setattr(memory_api, "atomic_write_in_vault", fail_write)

    with pytest.raises(OSError, match="write failed"):
        apply_change(sample_vault, proposal, approved=True)

    assert not (sample_vault / "01_Projects" / "WriteFailure.md").exists()
    assert read_history(sample_vault) == []


def test_memory_transaction_restores_note_and_log_when_log_fails(sample_vault, monkeypatch):
    log_file = sample_vault / "log.md"
    log_before = "Change Log\n"
    log_file.write_text(log_before, encoding="utf-8")
    proposal = propose_change(
        sample_vault,
        "01_Projects/LogFailure.md",
        '---\ntype: Project\ntitle: "Log failure"\ndescription: "log failure"\n'
        "timestamp: 2026-07-29T00:00:00Z\n---\n",
    )

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("log failed")

    monkeypatch.setattr(memory_api, "_append_text", fail_log)

    with pytest.raises(OSError, match="log failed"):
        memory_api.commit_note_change(
            sample_vault,
            proposal["path"],
            proposal["content"],
            require_absent=True,
            log_entry="\n## failed log entry\n",
        )

    assert not (sample_vault / "01_Projects" / "LogFailure.md").exists()
    assert log_file.read_text(encoding="utf-8") == log_before
    assert read_history(sample_vault) == []


def test_memory_transaction_restores_partial_index_write(sample_vault, monkeypatch):
    index_path = sample_vault / "index.md"
    index_before = index_path.read_text(encoding="utf-8") if index_path.exists() else None
    proposal = propose_change(
        sample_vault,
        "01_Projects/PartialIndex.md",
        '---\ntype: Project\ntitle: "Partial index"\ndescription: "partial index"\n'
        "timestamp: 2026-07-29T00:00:00Z\n---\n",
    )

    def partial_index(_vault: object) -> None:
        index_path.write_text("partial index", encoding="utf-8")
        raise RuntimeError("index failed after write")

    monkeypatch.setattr(memory_api, "run_generate_hierarchical_index", partial_index)

    with pytest.raises(RuntimeError, match="index failed after write"):
        apply_change(sample_vault, proposal, approved=True)

    assert not (sample_vault / "01_Projects" / "PartialIndex.md").exists()
    assert (index_path.read_text(encoding="utf-8") if index_path.exists() else None) == index_before
    assert read_history(sample_vault) == []


def test_memory_transaction_restores_note_and_projections_when_index_fails(
    sample_vault, monkeypatch: pytest.MonkeyPatch
):
    from power_framework.core.indexer import run_generate_hierarchical_index
    from power_framework.core.vault_storage import existing_vault_cache_dir

    run_generate_hierarchical_index(sample_vault)
    index_before = (
        (sample_vault / "index.md").read_text(encoding="utf-8")
        if (sample_vault / "index.md").exists()
        else None
    )
    cache_dir = existing_vault_cache_dir(sample_vault)
    assert cache_dir is not None
    cache_path = cache_dir / "hierarchical-index-cache.json"
    cache_before = cache_path.read_text(encoding="utf-8")
    proposal = propose_change(
        sample_vault,
        "01_Projects/IndexFailure.md",
        '---\ntype: Project\ntitle: "Index failure"\ndescription: "index failure"\ntimestamp: 2026-07-29T00:00:00Z\n---\n',
    )

    def fail_index(_: object) -> None:
        raise RuntimeError("index failed")

    monkeypatch.setattr(memory_api, "run_generate_hierarchical_index", fail_index)

    with pytest.raises(RuntimeError, match="index failed"):
        apply_change(sample_vault, proposal, approved=True)

    assert not (sample_vault / "01_Projects" / "IndexFailure.md").exists()
    assert read_history(sample_vault) == []
    index_after = sample_vault / "index.md"
    assert (
        index_after.read_text(encoding="utf-8") if index_after.exists() else None
    ) == index_before
    assert cache_path.read_text(encoding="utf-8") == cache_before


def test_memory_transaction_restores_note_when_blocking_lint_fails(
    sample_vault, monkeypatch: pytest.MonkeyPatch
):
    from power_framework.core.linter import LintResult

    proposal = propose_change(
        sample_vault,
        "01_Projects/LintFailure.md",
        '---\ntype: Project\ntitle: "Lint failure"\ndescription: "lint failure"\ntimestamp: 2026-07-29T00:00:00Z\n---\n',
    )
    lint_result = LintResult()
    lint_result.untyped_files.append(("existing.md", "simulated failure"))
    monkeypatch.setattr(memory_api, "run_lint_vault", lambda _: lint_result)

    with pytest.raises(RuntimeError, match="post-mutation lint failed"):
        apply_change(sample_vault, proposal, approved=True)

    assert not (sample_vault / "01_Projects" / "LintFailure.md").exists()
    assert read_history(sample_vault) == []


def test_memory_transaction_restores_note_when_sync_fails(
    sample_vault, monkeypatch: pytest.MonkeyPatch
):
    from power_framework.core import generation_index

    proposal = propose_change(
        sample_vault,
        "01_Projects/SyncFailure.md",
        '---\ntype: Project\ntitle: "Sync failure"\ndescription: "sync failure"\ntimestamp: 2026-07-29T00:00:00Z\n---\n',
    )

    def fail_sync(*args: object, **kwargs: object) -> None:
        raise RuntimeError("sync failed")

    monkeypatch.setattr(generation_index, "sync_vault_atomically", fail_sync)

    with pytest.raises(RuntimeError, match="sync failed"):
        apply_change(sample_vault, proposal, approved=True)

    assert not (sample_vault / "01_Projects" / "SyncFailure.md").exists()
    assert read_history(sample_vault) == []


def test_memory_transaction_preserves_previous_search_on_later_sync_failure(
    sample_vault, monkeypatch: pytest.MonkeyPatch
):
    first_marker = "first-committed-marker"
    first_proposal = propose_change(
        sample_vault,
        "01_Projects/FirstCommitted.md",
        '---\ntype: Project\ntitle: "First committed"\ndescription: "first"\ntimestamp: 2026-07-29T00:00:00Z\n---\n\n'
        + first_marker
        + "\n",
    )
    apply_change(sample_vault, first_proposal, approved=True)

    second_marker = "second-failed-marker"
    second_proposal = propose_change(
        sample_vault,
        "01_Projects/SecondFailed.md",
        '---\ntype: Project\ntitle: "Second failed"\ndescription: "second"\ntimestamp: 2026-07-29T00:00:00Z\n---\n\n'
        + second_marker
        + "\n",
    )
    from power_framework.core import generation_index

    def fail_sync(*args: object, **kwargs: object) -> None:
        raise RuntimeError("sync failed after previous generation")

    monkeypatch.setattr(generation_index, "sync_vault_atomically", fail_sync)

    with pytest.raises(RuntimeError, match="sync failed after previous generation"):
        apply_change(sample_vault, second_proposal, approved=True)

    assert search_vault(sample_vault, first_marker, mode="fts")
    assert not search_vault(sample_vault, second_marker, mode="fts")
    assert read_history(sample_vault)[0]["path"] == "01_Projects/FirstCommitted.md"


def test_memory_transaction_restores_search_when_receipt_fails(
    sample_vault, monkeypatch: pytest.MonkeyPatch
):
    marker = "receipt-failure-marker"
    proposal = propose_change(
        sample_vault,
        "01_Projects/ReceiptFailure.md",
        '---\ntype: Project\ntitle: "Receipt failure"\ndescription: "receipt failure"\ntimestamp: 2026-07-29T00:00:00Z\n---\n\n'
        + marker
        + "\n",
    )

    def fail_receipt(*args: object, **kwargs: object) -> None:
        raise OSError("receipt unavailable")

    monkeypatch.setattr(memory_api, "_append_receipt", fail_receipt)

    with pytest.raises(OSError, match="receipt unavailable"):
        apply_change(sample_vault, proposal, approved=True)

    assert not (sample_vault / "01_Projects" / "ReceiptFailure.md").exists()
    assert read_history(sample_vault) == []
    assert not search_vault(sample_vault, marker, mode="fts")
