"""R6A.2 future-only Stage-A holdout orchestration.

The caller supplies fixture setup and a query-only executor.  Ground truth is
never part of either callback's public input, and the atomic epoch guard is
acquired only after verification and fixture setup succeed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from power_framework.core.evaluation_execution import (
    execute_query_only_once,
    prepare_verified_holdout_execution,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path
    from typing import Any

    from power_framework.core.evaluation_contracts import SealedRevisionSpec
    from power_framework.core.evaluation_execution import (
        EpochBinding,
        HoldoutExecutionDescriptor,
        QueryOnlyRecord,
        RawRetrievalOutputArtifact,
        RawRetrievalOutputRecord,
    )

type FixtureSetup = Callable[
    [HoldoutExecutionDescriptor], Callable[[QueryOnlyRecord], RawRetrievalOutputRecord]
]


def run_verified_holdout_stage_a(
    *,
    eval_corpus: Path,
    expected_revision: str,
    revision_spec: SealedRevisionSpec | Mapping[str, Any],
    binding: EpochBinding,
    output_root: Path,
    allowed_root: Path,
    one_shot_intent: str,
    fixture_setup: FixtureSetup,
) -> tuple[RawRetrievalOutputArtifact, Any]:
    """Prepare, set up, guard, and execute a future holdout in one shot."""

    prepared = prepare_verified_holdout_execution(
        eval_corpus,
        expected_revision=expected_revision,
        revision_spec=revision_spec,
    )
    executor = fixture_setup(prepared.descriptor)
    return execute_query_only_once(
        queries=prepared.queries,
        binding=binding,
        output_root=output_root,
        allowed_root=allowed_root,
        one_shot_intent=one_shot_intent,
        executor=executor,
        verified_descriptor=prepared.descriptor,
    )


__all__ = ["run_verified_holdout_stage_a"]
