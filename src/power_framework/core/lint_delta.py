"""Finding-level blocking lint delta helpers for transactional commits."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from .linter import LintResult


@dataclass(frozen=True)
class BlockingLintDelta:
    """Count of newly introduced blocking lint findings across a mutation."""

    metadata: int = 0
    broken_links: int = 0
    ambiguous_links: int = 0
    stale: int = 0

    @property
    def has_new_issues(self) -> bool:
        """Return whether the mutation introduced any new blocking lint issue."""
        return bool(self.metadata or self.broken_links or self.ambiguous_links or self.stale)

    def format_counts(self) -> str:
        """Render stable count fields for error messages and receipts."""
        return (
            f"metadata={self.metadata}, "
            f"broken_links={self.broken_links}, "
            f"ambiguous_links={self.ambiguous_links}, "
            f"stale={self.stale}"
        )


@dataclass(frozen=True)
class MutationLintBaseline:
    """Pre-mutation vault health snapshot captured after crash recovery."""

    lint: LintResult
    invalid_sources: dict[str, str]


def _ambiguous_keys(result: LintResult) -> list[tuple[str, str, tuple[str, ...]]]:
    """Normalize ambiguous-link findings to hashable multiset keys."""
    return [
        (rp, target, tuple(sorted(candidates))) for rp, target, candidates in result.ambiguous_links
    ]


def compute_blocking_lint_delta(baseline: LintResult, post: LintResult) -> BlockingLintDelta:
    """Compare specific baseline and post-mutation findings via multiset subtraction.

    Using multiset difference ensures fixing an existing foreign defect cannot
    mask a newly introduced defect elsewhere in the vault.
    """
    new_metadata = Counter(post.untyped_files) - Counter(baseline.untyped_files)
    new_broken = Counter(post.broken_links) - Counter(baseline.broken_links)
    new_ambiguous = Counter(_ambiguous_keys(post)) - Counter(_ambiguous_keys(baseline))
    new_stale = Counter(post.stale_notes) - Counter(baseline.stale_notes)
    return BlockingLintDelta(
        metadata=sum(new_metadata.values()),
        broken_links=sum(new_broken.values()),
        ambiguous_links=sum(new_ambiguous.values()),
        stale=sum(new_stale.values()),
    )


def new_invalid_sources(
    baseline_invalid: Mapping[str, str],
    post_invalid: Mapping[str, str],
) -> dict[str, str]:
    """Return excluded sources that were newly added or changed exclusion reason."""
    return {
        rel_path: reason
        for rel_path, reason in post_invalid.items()
        if baseline_invalid.get(rel_path) != reason
    }


def capture_mutation_baseline(
    vault_dir: Path,
    run_lint: Callable[[Path], LintResult],
    list_invalid: Callable[[Path], dict[str, str]],
) -> MutationLintBaseline:
    """Capture lint findings and excluded sources before writing inside the lock."""
    return MutationLintBaseline(
        lint=run_lint(vault_dir),
        invalid_sources=dict(list_invalid(vault_dir)),
    )


def assert_no_new_invalid_sources(
    baseline: MutationLintBaseline,
    excluded_sources: Mapping[str, str],
) -> None:
    """Fail closed when the mutation introduced any newly excluded source."""
    added = new_invalid_sources(baseline.invalid_sources, excluded_sources)
    if added:
        raise RuntimeError(
            f"post-mutation source validation failed: new_invalid_sources={len(added)}"
        )


def verify_mutation_lint_gate(
    baseline: MutationLintBaseline,
    post_lint: LintResult,
    post_invalid: Mapping[str, str],
) -> bool:
    """Verify no new lint/source defects occurred; return whether partial sync is needed."""
    delta = compute_blocking_lint_delta(baseline.lint, post_lint)
    if delta.has_new_issues:
        raise RuntimeError(f"post-mutation lint failed: {delta.format_counts()}")
    assert_no_new_invalid_sources(baseline, post_invalid)
    return bool(post_invalid)


def format_blocking_lint_summary(result: LintResult, *, excluded_sources: int = 0) -> str:
    """Format a content-free blocking-debt count string for transaction receipts."""
    summary = (
        f"metadata={len(result.untyped_files)}, "
        f"broken_links={len(result.broken_links)}, "
        f"ambiguous_links={len(result.ambiguous_links)}, "
        f"stale={len(result.stale_notes)}"
    )
    if excluded_sources > len(result.untyped_files):
        return f"{summary}, excluded={excluded_sources}"
    return summary


def format_preexisting_warnings(result: LintResult, *, excluded_sources: int = 0) -> str | None:
    """Return a preexisting warning summary only when vault debt remains."""
    if result.has_blocking_issues or excluded_sources:
        return format_blocking_lint_summary(result, excluded_sources=excluded_sources)
    return None
