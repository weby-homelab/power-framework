"""Finding-level blocking lint delta helpers for transactional commits."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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


def format_blocking_lint_summary(result: LintResult) -> str:
    """Format a content-free blocking-debt count string for transaction receipts."""
    return (
        f"metadata={len(result.untyped_files)}, "
        f"broken_links={len(result.broken_links)}, "
        f"ambiguous_links={len(result.ambiguous_links)}, "
        f"stale={len(result.stale_notes)}"
    )
