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
    assert "preexisting_lint_warnings" not in receipt
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
    baseline = LintResult()
    post = LintResult()
    post.untyped_files.append(("01_Projects/LintFailure.md", "simulated failure"))
    calls = iter((baseline, post))
    monkeypatch.setattr(memory_api, "run_lint_vault", lambda _: next(calls))

    with pytest.raises(RuntimeError, match=r"post-mutation lint failed:.*metadata=1"):
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


def test_memory_commit_succeeds_with_preexisting_foreign_lint_debt(sample_vault):
    """Issue #464: clean writes must not fail due to unrelated pre-existing lint debt."""
    from power_framework.core.application import ApplicationService, RequestContext
    from power_framework.core.principal import Principal

    (sample_vault / "03_Resources" / "ForeignUntyped.md").write_text(
        "Unstructured foreign note without OKF frontmatter.\n",
        encoding="utf-8",
    )
    (sample_vault / "02_Areas" / "Dup.md").write_text(
        "---\n"
        "type: Area\n"
        'title: "Dup Area"\n'
        'description: "First duplicate basename"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "Dup Area.\n",
        encoding="utf-8",
    )
    (sample_vault / "03_Resources" / "Dup.md").write_text(
        "---\n"
        "type: Resource\n"
        'title: "Dup Resource"\n'
        'description: "Second duplicate basename"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "Dup Resource.\n",
        encoding="utf-8",
    )
    (sample_vault / "03_Resources" / "ForeignAmbig.md").write_text(
        "---\n"
        "type: Resource\n"
        'title: "Foreign Ambig"\n'
        'description: "Pre-existing ambiguous link"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "Links ambiguously to [[Dup]].\n",
        encoding="utf-8",
    )
    (sample_vault / "01_Projects" / "ForeignBroken.md").write_text(
        "---\n"
        "type: Project\n"
        'title: "Foreign Broken"\n'
        'description: "Pre-existing broken link"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "Links to [[ForeignMissingTarget]].\n",
        encoding="utf-8",
    )
    (sample_vault / "01_Projects" / "ForeignExpired.md").write_text(
        "---\n"
        "type: Project\n"
        'title: "Foreign Expired"\n'
        'description: "Pre-existing expired note"\n'
        "expiry: 2020-01-01\n"
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "Expired foreign body.\n",
        encoding="utf-8",
    )

    clean_proposal = propose_change(
        sample_vault,
        "01_Projects/CleanWrite.md",
        "---\n"
        "type: Project\n"
        'title: "Clean Write"\n'
        'description: "Valid note written with foreign debt present"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "clean-write-with-foreign-debt\n",
    )
    receipt = apply_change(sample_vault, clean_proposal, approved=True)

    assert (sample_vault / "01_Projects" / "CleanWrite.md").exists()
    assert receipt["notes_excluded"] == "1"
    assert "preexisting_lint_warnings" in receipt
    assert "metadata=1" in receipt["preexisting_lint_warnings"]
    assert "broken_links=1" in receipt["preexisting_lint_warnings"]
    assert "ambiguous_links=1" in receipt["preexisting_lint_warnings"]
    assert "stale=1" in receipt["preexisting_lint_warnings"]
    assert search_vault(sample_vault, "clean-write-with-foreign-debt", mode="fts")
    history = read_history(sample_vault)
    assert len(history) == 1
    assert history[0]["preexisting_lint_warnings"] == receipt["preexisting_lint_warnings"]
    assert validate_state(sample_vault) is False

    service = ApplicationService(sample_vault)
    envelope = service.ingest_note(
        name="01_Projects/IngestCleanWrite.md",
        note_type="Project",
        title="Ingest Clean Write",
        description="Ingested despite foreign untyped, ambiguous, broken, and expired debt",
        content="Clean body content.",
        context=RequestContext(authority="apply", principal=Principal.local_cli()),
    )
    assert (sample_vault / "01_Projects" / "IngestCleanWrite.md").exists()
    assert "metadata=1" in envelope.data["receipt"]["preexisting_lint_warnings"]
    assert "broken_links=1" in envelope.data["receipt"]["preexisting_lint_warnings"]


def test_memory_commit_rejects_new_defect_even_when_fixing_old_defect(sample_vault):
    """Fixing one old broken link must never mask introducing a different broken link."""
    note_rel = "01_Projects/FixAndBreak.md"
    original = (
        "---\n"
        "type: Project\n"
        'title: "Fix And Break"\n'
        'description: "Starts with one broken link"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "Existing link [[OldMissing]].\n"
    )
    (sample_vault / note_rel).write_text(original, encoding="utf-8")

    replacement = (
        "---\n"
        "type: Project\n"
        'title: "Fix And Break"\n'
        'description: "Removes old broken link and introduces new one"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "Replaced with [[NewMissing]].\n"
    )
    proposal = propose_change(sample_vault, note_rel, replacement)

    with pytest.raises(RuntimeError, match=r"post-mutation lint failed:.*broken_links=1"):
        apply_change(sample_vault, proposal, approved=True)

    assert (sample_vault / note_rel).read_text(encoding="utf-8") == original
    assert read_history(sample_vault) == []


def test_memory_commit_rejects_new_vault_wide_ambiguous_link(sample_vault):
    """Creating a valid note that causes a vault-wide ambiguous wikilink rolls back."""
    (sample_vault / "01_Projects" / "Alpha.md").write_text(
        "---\n"
        "type: Project\n"
        'title: "Alpha Project"\n'
        'description: "Unique Alpha target"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "Project Alpha.\n",
        encoding="utf-8",
    )
    (sample_vault / "01_Projects" / "Linker.md").write_text(
        "---\n"
        "type: Project\n"
        'title: "Linker"\n'
        'description: "Links cleanly to Alpha"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "See [[Alpha]].\n",
        encoding="utf-8",
    )

    proposal = propose_change(
        sample_vault,
        "02_Areas/Alpha.md",
        "---\n"
        "type: Area\n"
        'title: "Alpha Area"\n'
        'description: "Creates basename collision"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "Area Alpha.\n",
    )

    with pytest.raises(RuntimeError, match=r"post-mutation lint failed:.*ambiguous_links=1"):
        apply_change(sample_vault, proposal, approved=True)

    assert not (sample_vault / "02_Areas" / "Alpha.md").exists()
    assert read_history(sample_vault) == []

    # Already-ambiguous wikilink worsened by adding a 3rd colliding note must also fail.
    (sample_vault / "02_Areas" / "Alpha.md").write_text(
        "---\n"
        "type: Area\n"
        'title: "Alpha Area Existing"\n'
        'description: "Existing collision"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "Existing Area Alpha.\n",
        encoding="utf-8",
    )
    (sample_vault / "log.md").write_text("Log header\n", encoding="utf-8")
    third_proposal = propose_change(
        sample_vault,
        "03_Resources/Alpha.md",
        "---\n"
        "type: Resource\n"
        'title: "Alpha Resource"\n'
        'description: "Adds third colliding basename"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "Resource Alpha.\n",
    )
    with pytest.raises(RuntimeError, match=r"post-mutation lint failed:.*ambiguous_links=1"):
        memory_api.commit_note_change(
            sample_vault,
            "03_Resources/Alpha.md",
            third_proposal["content"],
            log_entry="\nShould roll back\n",
        )
    assert not (sample_vault / "03_Resources" / "Alpha.md").exists()
    assert (sample_vault / "log.md").read_text(encoding="utf-8") == "Log header\n"


def test_memory_commit_rejects_new_stale_note_and_delta_helper_checks_multiset(sample_vault):
    """Creating an expired note fails delta check; multiset helper distinguishes findings."""
    from power_framework.core.lint_delta import compute_blocking_lint_delta
    from power_framework.core.linter import LintResult

    proposal = propose_change(
        sample_vault,
        "01_Projects/AlreadyExpired.md",
        "---\n"
        "type: Project\n"
        'title: "Already Expired"\n'
        'description: "Introduces a new stale note"\n'
        "expiry: 2020-01-01\n"
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "Expired.\n",
    )
    with pytest.raises(RuntimeError, match=r"post-mutation lint failed:.*stale=1"):
        apply_change(sample_vault, proposal, approved=True)
    assert not (sample_vault / "01_Projects" / "AlreadyExpired.md").exists()

    baseline = LintResult()
    baseline.untyped_files = [("old.md", "missing type")]
    baseline.ambiguous_links = [("a.md", "Foo", ["02_Areas/Foo.md", "01_Projects/Foo.md"])]

    post = LintResult()
    post.untyped_files = [("new.md", "missing type")]
    post.ambiguous_links = [("a.md", "Foo", ["01_Projects/Foo.md", "02_Areas/Foo.md"])]

    delta = compute_blocking_lint_delta(baseline, post)
    assert delta.has_new_issues is True
    assert delta.metadata == 1
    assert delta.ambiguous_links == 0


def test_memory_commit_rolls_back_cleanly_on_receipt_failure_with_foreign_untyped_note(
    sample_vault,
    monkeypatch: pytest.MonkeyPatch,
):
    """Rollback search rebuild after receipt failure must tolerate foreign untyped notes."""
    (sample_vault / "03_Resources" / "ForeignUntyped.md").write_text(
        "Unstructured foreign note without frontmatter.\n",
        encoding="utf-8",
    )
    marker = "rollback-foreign-untyped-marker"
    proposal = propose_change(
        sample_vault,
        "01_Projects/RollbackUntyped.md",
        "---\n"
        "type: Project\n"
        'title: "Rollback Untyped"\n'
        'description: "Rolls back cleanly"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        f"{marker}\n",
    )

    def fail_receipt(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated receipt failure")

    monkeypatch.setattr(memory_api, "_append_receipt", fail_receipt)

    with pytest.raises(OSError, match="simulated receipt failure"):
        apply_change(sample_vault, proposal, approved=True)

    assert not (sample_vault / "01_Projects" / "RollbackUntyped.md").exists()
    assert not search_vault(sample_vault, marker, mode="fts")
    assert read_history(sample_vault) == []


def test_memory_commit_rejects_new_invalid_source_even_with_preexisting_invalid_source(
    sample_vault,
    monkeypatch: pytest.MonkeyPatch,
):
    """Pre-existing invalid sources must never permit introducing another invalid source."""
    from power_framework.core import generation_index

    (sample_vault / "03_Resources" / "ForeignUntyped.md").write_text(
        "Unstructured foreign note.\n",
        encoding="utf-8",
    )
    proposal = propose_change(
        sample_vault,
        "01_Projects/CleanCandidate.md",
        "---\n"
        "type: Project\n"
        'title: "Clean Candidate"\n'
        'description: "Valid note"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "Body.\n",
    )

    original_list_invalid = generation_index.list_invalid_sources
    calls = 0

    def list_with_new_invalid(vault_dir):
        nonlocal calls
        calls += 1
        found = original_list_invalid(vault_dir)
        if calls >= 2:
            found["03_Resources/NewlyUnreadable.md"] = "read_error"
        return found

    monkeypatch.setattr(generation_index, "list_invalid_sources", list_with_new_invalid)

    with pytest.raises(RuntimeError, match="post-mutation source validation failed"):
        apply_change(sample_vault, proposal, approved=True)

    assert not (sample_vault / "01_Projects" / "CleanCandidate.md").exists()
    assert read_history(sample_vault) == []


def test_memory_commit_runs_crash_recovery_before_baseline_lint(sample_vault):
    """Unrecovered crashed writes must be rolled back before capturing lint baseline."""
    from datetime import UTC, datetime

    from power_framework.core.task_store import TaskStore

    crashed_rel = "01_Projects/CrashedBroken.md"
    crashed_content = (
        "---\n"
        "type: Project\n"
        'title: "Crashed Broken"\n'
        'description: "Left by crashed transaction"\n'
        "timestamp: 2026-07-29T00:00:00Z\n"
        "---\n\n"
        "Broken [[MissingCrashTarget]].\n"
    )
    crashed_path = sample_vault / crashed_rel
    crashed_path.write_text(crashed_content, encoding="utf-8")

    store = TaskStore(sample_vault)
    tx_dir = store.tx_dir / "txcrash1"
    tx_dir.mkdir(parents=True)
    manifest = {
        "tx_id": "txcrash1",
        "op": "memory_apply",
        "idempotency_key": "mcrash",
        "command_sha256": None,
        "stage": "prepared",
        "created_at": datetime.now(UTC).isoformat(),
        "vault": store.vault_dir.as_posix(),
        "touched": [
            {"label": "note", "rel": crashed_rel, "preimage_digest": None},
            {"label": "history", "rel": ".power/memory-history.jsonl", "preimage_digest": None},
        ],
    }
    (tx_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match=r"post-mutation lint failed:.*broken_links=1"):
        memory_api.commit_note_change(sample_vault, crashed_rel, crashed_content)

    assert not crashed_path.exists()
    assert read_history(sample_vault) == []
