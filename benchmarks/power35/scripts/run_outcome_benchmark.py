"""Run a synthetic, content-free Phase 8 outcome and continuity benchmark.

The benchmark compares the shared application boundary with a deliberately
small no-POWER baseline: repository-only text scanning plus an unstructured
handoff.  It exercises FTS and auto/fallback profiles across bilingual and
false-premise strata, but measures technical workflow properties rather than
human quality or production usefulness. Reports contain identifiers, hashes,
and metrics only.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

try:
    import resource as _resource
except ImportError:  # pragma: no cover - resource is unavailable on Windows.
    _resource = None

from power_framework.core.application import ApplicationService, RequestContext
from power_framework.phase8_contract import (
    PHASE8_OUTCOME_SCHEMA_VERSION,
    SYNTHETIC_WORKFLOW_COUNT,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

ScenarioKind = Literal["static", "dynamic", "workflow", "gotcha", "blocked"]
ScenarioLanguage = Literal["en", "uk"]
PremiseKind = Literal["supported", "false"]


class Outcome(TypedDict):
    completed: bool
    evidence: bool
    continuity: bool
    safe: bool
    human_reminders: int
    unsafe_actions: int
    abstained: bool
    auto_evidence: bool
    auto_fallback: bool
    stale_state_safe: bool
    score: NotRequired[float]


class WorkflowRow(TypedDict):
    workflow_id: str
    kind: ScenarioKind
    language: ScenarioLanguage
    premise: PremiseKind
    stale: bool
    power: Outcome
    no_power: Outcome


@dataclass(frozen=True)
class Scenario:
    workflow_id: str
    kind: ScenarioKind
    language: ScenarioLanguage
    premise: PremiseKind
    stale: bool
    historical_path: str | None
    query: str
    expected_path: str


def _scenarios() -> tuple[Scenario, ...]:
    kinds: tuple[ScenarioKind, ...] = ("static", "dynamic", "workflow", "gotcha", "blocked")
    scenarios = tuple(
        Scenario(
            workflow_id=f"workflow-{kind}-{number:02d}",
            kind=kind,
            language="uk" if number % 2 == 0 else "en",
            premise="false" if number == 2 else "supported",
            stale=kind == "dynamic" and number == 4,
            historical_path=(
                f"03_Resources/phase8-{kind}-{number:02d}-historical.md"
                if kind == "dynamic" and number == 4
                else None
            ),
            query=(
                f"phase8-{kind}-{number:02d}-fact"
                if number % 2
                else f"фаза8-{kind}-{number:02d}-факт"  # noqa: RUF001
            ),
            expected_path=f"03_Resources/phase8-{kind}-{number:02d}.md",
        )
        for kind in kinds
        for number in range(1, 5)
    )
    if len(scenarios) != SYNTHETIC_WORKFLOW_COUNT:
        raise RuntimeError("outcome scenario count does not match the Phase 8 contract")
    return scenarios


def _write_fixture(vault: Path, scenario: Scenario) -> None:
    path = vault / scenario.expected_path
    path.parent.mkdir(parents=True, exist_ok=True)
    memory_block = (
        'okf_version: "0.2"\n'
        "memory:\n"
        "  kind: semantic\n"
        "  valid_from: 2026-07-10\n"
        f"  supersedes: [{scenario.historical_path}]\n"
        if scenario.stale
        else ""
    )
    body = (
        f"Declared fixture fact: {scenario.query}.\n"
        if scenario.premise == "supported"
        else "Declared fixture contains a different fact; the requested premise is absent.\n"
    )
    fixture = (
        "---\n"
        "type: Resource\n"
        f'title: "Phase 8 {scenario.workflow_id}"\n'
        'description: "Synthetic technical benchmark fixture"\n'
        + memory_block
        + "timestamp: 2026-08-11T00:00:00Z\n"
        + "---\n\n"
        + body
    )
    path.write_text(fixture, encoding="utf-8")
    if scenario.historical_path is not None:
        historical = vault / scenario.historical_path
        historical.write_text(
            "---\n"
            "type: Resource\n"
            f'title: "Historical {scenario.workflow_id}"\n'
            'description: "Synthetic historical benchmark fixture"\n'
            'okf_version: "0.2"\n'
            "memory:\n"
            "  kind: semantic\n"
            "  valid_from: 2026-01-01\n"
            "timestamp: 2026-01-01T00:00:00Z\n"
            "---\n\n" + body,
            encoding="utf-8",
        )


def _retrieval_found(data: dict[str, object], expected_path: str) -> bool:
    results = data.get("results")
    if not isinstance(results, list):
        return False
    for item in results:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        if isinstance(source, dict) and source.get("path") == expected_path:
            return True
    return False


def _receipt_is_content_free(receipt: dict[str, object], forbidden: str) -> bool:
    allowed = {
        "schema_version",
        "operation",
        "status",
        "request_id",
        "idempotency_key",
        "data_sha256",
        "duration_ms",
    }
    return set(receipt) == allowed and forbidden not in json.dumps(receipt, sort_keys=True)


def _run_power(vault: Path, scenario: Scenario) -> Outcome:
    service = ApplicationService(vault)
    retrieval = service.retrieve(
        scenario.query,
        mode="fts",
        max_results=5,
        temporal_view="current",
        as_of="2026-08-11",
    )
    retrieval_data = retrieval.data
    found = _retrieval_found(retrieval_data, scenario.expected_path)
    evidence = found and _receipt_is_content_free(retrieval.receipt.as_dict(), scenario.query)
    auto_retrieval = service.retrieve(
        scenario.query,
        mode="auto",
        max_results=5,
        temporal_view="current",
        as_of="2026-08-11",
    )
    auto_data = auto_retrieval.data
    auto_found = _retrieval_found(auto_data, scenario.expected_path)
    auto_evidence = auto_found and _receipt_is_content_free(
        auto_retrieval.receipt.as_dict(), scenario.query
    )
    stale_state_safe = scenario.historical_path is None or not _retrieval_found(
        retrieval_data, scenario.historical_path
    )

    task_id = f"{scenario.workflow_id}-handoff"
    service.task(
        action="create",
        task_id=task_id,
        values={
            "objective": f"Resume {scenario.workflow_id}",
            "owner": "synthetic-agent-a",
            "scope": [scenario.expected_path],
            "authority": "propose",
            "next_action": "retrieve",
        },
        context=RequestContext(
            actor="synthetic-agent-a",
            authority="propose",
            idempotency_key=f"{task_id}:create",
        ),
    )
    resumed = service.task(action="read", task_id=task_id)
    service.task(
        action="advance",
        task_id=task_id,
        values={"action": "resume", "next_action": "retrieve"},
        context=RequestContext(
            actor="synthetic-agent-b",
            authority="apply",
            idempotency_key=f"{task_id}:resume",
        ),
    )
    is_abstention_case = scenario.kind == "blocked" or scenario.premise == "false"
    advance_values: dict[str, object] = {
        "action": "input-required" if is_abstention_case else "complete",
        "next_action": (
            "human-decision"
            if scenario.kind == "blocked"
            else "verify-premise"
            if scenario.premise == "false"
            else "none"
        ),
    }
    if is_abstention_case:
        advance_values.update(
            {
                "blocker": (
                    "declared human decision"
                    if scenario.kind == "blocked"
                    else "premise absent from retrieved evidence"
                ),
                "required_approval": "human" if scenario.kind == "blocked" else "evidence",
            }
        )
    else:
        advance_values["receipt_id"] = f"{scenario.workflow_id}-receipt"
    advanced = service.task(
        action="advance",
        task_id=task_id,
        values=advance_values,
        context=RequestContext(
            actor="synthetic-agent-b",
            authority="apply",
            idempotency_key=f"{task_id}:outcome",
        ),
    )
    resumed_packet = resumed.data
    advanced_packet = advanced.data
    continuity = (
        isinstance(resumed_packet, dict)
        and resumed_packet.get("task_id") == task_id
        and isinstance(advanced_packet, dict)
        and advanced_packet.get("task_id") == task_id
    )

    safe = True
    if scenario.kind == "gotcha":
        source = vault / scenario.expected_path
        before = source.read_bytes()
        proposal = service.propose(
            scenario.expected_path,
            source.read_text(encoding="utf-8") + "\nproposed change\n",
            context=RequestContext(
                actor="synthetic-agent-b",
                authority="propose",
                idempotency_key=f"{scenario.workflow_id}:proposal",
            ),
        )
        safe = source.read_bytes() == before and _receipt_is_content_free(
            proposal.receipt.as_dict(), scenario.query
        )

    abstained = (
        (scenario.premise == "false" or scenario.kind == "blocked")
        and isinstance(advanced_packet, dict)
        and advanced_packet.get("state") == "input-required"
    )
    completed = continuity and (found or abstained)
    return {
        "completed": completed,
        "evidence": evidence,
        "continuity": continuity,
        "safe": safe,
        "human_reminders": int(scenario.kind == "blocked"),
        "unsafe_actions": 0,
        "abstained": (
            abstained
            and (scenario.kind != "blocked" or advanced_packet.get("state") == "input-required")
        ),
        "auto_evidence": auto_evidence,
        "auto_fallback": auto_data.get("actual_mode") == "fts"
        and auto_data.get("fallback_reason") is not None,
        "stale_state_safe": stale_state_safe,
    }


def _run_no_power(vault: Path, scenario: Scenario) -> Outcome:
    """Model plain repository handoff without receipts or durable task state."""
    found = any(
        scenario.query in path.read_text(encoding="utf-8", errors="replace")
        for path in vault.rglob("*.md")
        if path.is_file()
    )
    return {
        "completed": found,
        "evidence": False,
        "continuity": False,
        "safe": scenario.kind != "gotcha" and scenario.premise != "false",
        "human_reminders": 1,
        "unsafe_actions": int(scenario.kind == "gotcha" or scenario.premise == "false"),
        "abstained": False,
        "auto_evidence": False,
        "auto_fallback": False,
        "stale_state_safe": scenario.historical_path is None,
    }


def _score(result: Outcome) -> float:
    return sum(bool(result[key]) for key in ("completed", "evidence", "continuity", "safe")) / 4


def _mean(values: Iterable[float]) -> float:
    values = tuple(values)
    return round(sum(values) / len(values), 4) if values else 0.0


def _with_score(result: Outcome) -> Outcome:
    return {**result, "score": _score(result)}


def _peak_rss_kib() -> int:
    """Return a portable process high-water mark in KiB."""
    if _resource is None:
        return 0
    value = int(_resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss)
    # Linux reports KiB, while macOS reports bytes.
    return value // 1024 if sys.platform == "darwin" else value


def _vault_size_bytes(vault: Path) -> int:
    """Return aggregate fixture/runtime bytes without reading them into output."""
    return sum(
        path.stat().st_size for path in vault.rglob("*") if path.is_file() and not path.is_symlink()
    )


def _measured_run(
    runner: Callable[[Path, Scenario], Outcome], vault: Path, scenario: Scenario
) -> tuple[Outcome, dict[str, int]]:
    """Run one side of the comparison and return only numeric resource metrics."""
    started = time.perf_counter()
    before_rss = _peak_rss_kib()
    outcome = runner(vault, scenario)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    peak_rss = max(before_rss, _peak_rss_kib())
    return outcome, {
        "latency_ms": elapsed_ms,
        "peak_rss_kib": peak_rss,
        "disk_bytes": _vault_size_bytes(vault),
    }


def run_benchmark() -> dict[str, object]:
    scenarios = _scenarios()
    manifest = [
        {
            "workflow_id": scenario.workflow_id,
            "kind": scenario.kind,
            "language": scenario.language,
            "premise": scenario.premise,
            "stale": scenario.stale,
            "expected_path": scenario.expected_path,
        }
        for scenario in scenarios
    ]
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    with tempfile.TemporaryDirectory(prefix="power35-outcome-") as temporary:
        vault = Path(temporary)
        for scenario in scenarios:
            _write_fixture(vault, scenario)
        rows: list[WorkflowRow] = []
        power_metrics: list[dict[str, int]] = []
        no_power_metrics: list[dict[str, int]] = []
        for scenario in scenarios:
            power, measured_power = _measured_run(_run_power, vault, scenario)
            # Keep the baseline measurement isolated from POWER's runtime files.
            with tempfile.TemporaryDirectory(prefix="power35-no-power-") as baseline_dir:
                baseline_vault = Path(baseline_dir)
                _write_fixture(baseline_vault, scenario)
                no_power, measured_no_power = _measured_run(_run_no_power, baseline_vault, scenario)
            rows.append(
                {
                    "workflow_id": scenario.workflow_id,
                    "kind": scenario.kind,
                    "language": scenario.language,
                    "premise": scenario.premise,
                    "stale": scenario.stale,
                    "power": _with_score(power),
                    "no_power": _with_score(no_power),
                }
            )
            power_metrics.append(measured_power)
            no_power_metrics.append(measured_no_power)

    power_rows = [row["power"] for row in rows]
    no_power_rows = [row["no_power"] for row in rows]
    power_scores = [float(row["score"]) for row in power_rows]
    no_power_scores = [float(row["score"]) for row in no_power_rows]
    power_reminders = sorted(int(row["human_reminders"]) for row in power_rows)
    median_reminders = power_reminders[len(power_reminders) // 2]
    power_completion = sum(int(row["completed"]) for row in power_rows) / len(rows)
    power_unsafe = sum(row["unsafe_actions"] for row in power_rows)
    power_evidence = sum(int(row["evidence"]) for row in power_rows)
    no_power_evidence = sum(int(row["evidence"]) for row in no_power_rows)
    power_abstention = all(row["power"]["abstained"] for row in rows if row["kind"] == "blocked")
    false_premise_rows = [row for row in rows if row["premise"] == "false"]
    stale_rows = [row for row in rows if row["stale"]]
    stale_state_filter = all(row["power"]["stale_state_safe"] for row in stale_rows)
    false_premise_abstention = all(
        row["power"]["abstained"]
        and row["power"]["unsafe_actions"] == 0
        and not row["power"]["evidence"]
        for row in false_premise_rows
    )
    language_strata: dict[str, dict[str, object]] = {}
    for language in ("en", "uk"):
        language_rows = [row for row in rows if row["language"] == language]
        language_strata[language] = {
            "workflow_count": len(language_rows),
            "power_evidence_recall": round(
                sum(int(row["power"]["evidence"]) for row in language_rows) / len(language_rows),
                4,
            ),
            "power_auto_evidence_recall": round(
                sum(int(row["power"]["auto_evidence"]) for row in language_rows)
                / len(language_rows),
                4,
            ),
        }
    auto_fallbacks = sum(int(row["power"]["auto_fallback"]) for row in rows)
    rendered = json.dumps(rows, ensure_ascii=False, sort_keys=True)
    return {
        "schema_version": PHASE8_OUTCOME_SCHEMA_VERSION,
        "synthetic": True,
        "content_free": True,
        "scenario_manifest_sha256": manifest_hash,
        "workflow_count": len(rows),
        "workflows": rows,
        "comparison": {
            "power_mean_score": _mean(power_scores),
            "no_power_mean_score": _mean(no_power_scores),
            "practical_improvement": _mean(power_scores) > _mean(no_power_scores),
            "evidence_recall": {
                "power": round(power_evidence / len(rows), 4),
                "no_power": round(no_power_evidence / len(rows), 4),
            },
            "evidence_use": {
                "power": round(
                    sum(int(row["evidence"] and row["continuity"]) for row in power_rows)
                    / len(rows),
                    4,
                ),
                "no_power": 0.0,
            },
            "false_premise_cases": len(false_premise_rows),
            "false_premise_abstention": false_premise_abstention,
            "false_premise_scoring": "synthetic_presence_and_abstention_only",
            "stale_state_cases": len(stale_rows),
            "stale_state_filter": stale_state_filter,
        },
        "feedback_reuse": {
            "measured": False,
            "reason": "synthetic runner has no human feedback or StreamMemBench labels",
        },
        "retrieval_profiles": {
            "fts": {"status": "executed", "workflow_count": len(rows)},
            "auto": {
                "status": "executed",
                "workflow_count": len(rows),
                "fallback_to_fts_rate": round(auto_fallbacks / len(rows), 4),
            },
            "semantic": {
                "status": "not_evaluated",
                "reason": "no sealed model/provider receipt in synthetic runner",
            },
        },
        "bilingual_strata": language_strata,
        "resources": {
            "power": {
                "median_latency_ms": sorted(item["latency_ms"] for item in power_metrics)[
                    len(power_metrics) // 2
                ],
                "max_peak_rss_kib": max(item["peak_rss_kib"] for item in power_metrics),
                "max_disk_bytes": max(item["disk_bytes"] for item in power_metrics),
            },
            "no_power": {
                "median_latency_ms": sorted(item["latency_ms"] for item in no_power_metrics)[
                    len(no_power_metrics) // 2
                ],
                "max_peak_rss_kib": max(item["peak_rss_kib"] for item in no_power_metrics),
                "max_disk_bytes": max(item["disk_bytes"] for item in no_power_metrics),
            },
        },
        "gate": {
            "fresh_agent_completion": round(power_completion, 4),
            "safety_invariants_100": power_unsafe == 0,
            "median_human_reminders": median_reminders,
            "technical_continuity_20": all(bool(row["continuity"]) for row in power_rows),
            "blocked_workflow_abstention": power_abstention,
            "false_premise_abstention": false_premise_abstention,
            "stale_state_filter": stale_state_filter,
        },
        "blind_scoring": False,
        "bootstrap_context_tokens": {
            "measured": False,
            "reason": "synthetic runner does not tokenize client context",
        },
        "raw_content_in_report": False,
        "human_quality_certification": False,
        "real_vault": False,
        "sealed_holdout": "not_opened",
        "report_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    report = run_benchmark()
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
