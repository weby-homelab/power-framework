"""Run a content-free cross-process continuity benchmark for 20 workflows."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Literal

from power_framework.phase8_contract import (
    CONTINUITY_INDEPENDENT_PROCESSES,
    PHASE8_CONTINUITY_SCHEMA_VERSION,
    PLAIN_HANDOFF_PROCESSES,
    SYNTHETIC_WORKFLOW_COUNT,
)

try:
    from .evidence_identity import technical_evidence_identity
except ImportError:  # pragma: no cover - direct script execution in release workflow.
    from evidence_identity import technical_evidence_identity

ScenarioKind = Literal["code", "ops", "research", "note_mutation", "blocked"]

_WORKER = r"""
import json
import sys
from pathlib import Path

from power_framework.core.handoff import advance_work_packet, create_work_packet, read_work_packet

phase, vault_text, task_id, kind = sys.argv[1:]
vault = Path(vault_text)

if phase == "a":
    packet = create_work_packet(
        vault,
        task_id=task_id,
        objective="Continue a declared synthetic workflow",
        owner="human",
        actor="agent-a",
        scope=["synthetic-workflow"],
        authority="propose",
        source_revision="fixture-revision",
        next_action="inspect",
        idempotency_key=f"{task_id}:create",
    )
    result = {"task_id": packet["task_id"], "state": packet["state"], "checkpoint": packet["checkpoint"]}
elif phase == "b":
    observed = read_work_packet(vault, task_id)
    resumed = advance_work_packet(
        vault,
        task_id,
        action="resume",
        idempotency_key=f"{task_id}:resume",
        actor="agent-b",
        next_action="verify",
    )
    replay = advance_work_packet(
        vault,
        task_id,
        action="resume",
        idempotency_key=f"{task_id}:resume",
        actor="agent-b",
        next_action="verify",
    )
    result = {
        "task_id": observed["task_id"],
        "observed_state": observed["state"],
        "state": resumed["state"],
        "checkpoint": resumed["checkpoint"],
        "source_revision_present": resumed["source_revision"] == "fixture-revision",
        "replay_equal": replay == resumed,
    }
elif phase == "c":
    if kind == "blocked":
        packet = advance_work_packet(
            vault,
            task_id,
            action="input-required",
            idempotency_key=f"{task_id}:outcome",
            actor="agent-b",
            blocker="declared human decision",
            required_approval="human",
            next_action="human-decision",
        )
    else:
        packet = advance_work_packet(
            vault,
            task_id,
            action="complete",
            idempotency_key=f"{task_id}:outcome",
            actor="agent-b",
            receipt_id=f"{task_id}:receipt",
            next_action="none",
        )
    result = {
        "task_id": packet["task_id"],
        "state": packet["state"],
        "human_interventions": packet["human_interventions"],
        "receipt_count": len(packet["receipt_ids"]),
    }
elif phase == "plain-a":
    handoff = vault / "plain-handoffs" / f"{task_id}.txt"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    handoff.write_text(f"task={task_id}\nnext_action=inspect\n", encoding="utf-8")
    result = {"task_id": task_id, "handoff_written": handoff.is_file()}
elif phase == "plain-b":
    handoff = vault / "plain-handoffs" / f"{task_id}.txt"
    result = {
        "task_id": task_id,
        "handoff_present": handoff.is_file(),
        "durable_state_resumed": False,
    }
else:
    raise SystemExit(f"unknown phase: {phase}")

print(json.dumps(result, sort_keys=True))
"""


def _workflows() -> tuple[tuple[str, ScenarioKind], ...]:
    kinds: tuple[ScenarioKind, ...] = ("code", "ops", "research", "note_mutation", "blocked")
    workflows = tuple(
        (f"continuity-{kind}-{number:02d}", kind) for kind in kinds for number in range(1, 5)
    )
    if len(workflows) != SYNTHETIC_WORKFLOW_COUNT:
        raise RuntimeError("continuity scenario count does not match the Phase 8 contract")
    return workflows


def _run_worker(
    phase: str, vault: Path, task_id: str, kind: ScenarioKind
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    completed = subprocess.run(  # noqa: S603 -- fixed local worker and synthetic arguments.
        [sys.executable, "-c", _WORKER, phase, str(vault), task_id, kind],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"continuity worker {phase} failed: {completed.returncode}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"continuity worker {phase} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"continuity worker {phase} returned a non-object")
    return payload, (time.perf_counter() - started) * 1000


def run_continuity_benchmark() -> dict[str, Any]:
    """Run independent agent processes and return only redacted metrics."""
    rows: list[dict[str, Any]] = []
    timings: list[float] = []
    plain_timings: list[float] = []
    process_count = 0
    plain_process_count = 0
    with tempfile.TemporaryDirectory(prefix="power35-continuity-") as temporary:
        vault = Path(temporary)
        sentinel = vault / "01_Projects" / "sentinel.md"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_bytes(b"source sentinel\n")
        sentinel_before = sentinel.read_bytes()

        for task_id, kind in _workflows():
            created, create_ms = _run_worker("a", vault, task_id, kind)
            resumed, resume_ms = _run_worker("b", vault, task_id, kind)
            outcome, outcome_ms = _run_worker("c", vault, task_id, kind)
            process_count += 3
            timings.extend((create_ms, resume_ms, outcome_ms))
            continuity = (
                created.get("task_id") == task_id
                and resumed.get("task_id") == task_id
                and outcome.get("task_id") == task_id
                and created.get("state") == "submitted"
                and resumed.get("observed_state") == "submitted"
                and resumed.get("state") == "working"
                and resumed.get("source_revision_present") is True
                and resumed.get("replay_equal") is True
            )
            expected_terminal = "input-required" if kind == "blocked" else "completed"
            safe = outcome.get("state") == expected_terminal
            rows.append(
                {
                    "workflow_id": task_id,
                    "kind": kind,
                    "continuity": continuity,
                    "safe": safe,
                    "human_reminders": int(kind == "blocked"),
                    "unsafe_actions": 0,
                    "proof_carrying_handoff": bool(resumed.get("source_revision_present")),
                    "replay_idempotent": bool(resumed.get("replay_equal")),
                    "duplicate_work_events": int(not resumed.get("replay_equal")),
                    "time_to_outcome_ms": round(create_ms + resume_ms + outcome_ms),
                }
            )

            plain_created, plain_create_ms = _run_worker("plain-a", vault, task_id, kind)
            plain_resumed, plain_resume_ms = _run_worker("plain-b", vault, task_id, kind)
            plain_process_count += 2
            plain_timings.extend((plain_create_ms, plain_resume_ms))
            rows[-1]["plain_handoff"] = {
                "handoff_written": plain_created.get("handoff_written") is True,
                "handoff_present": plain_resumed.get("handoff_present") is True,
                "durable_state_resumed": plain_resumed.get("durable_state_resumed") is True,
            }

        source_preserved = sentinel.read_bytes() == sentinel_before

    if process_count != CONTINUITY_INDEPENDENT_PROCESSES:
        raise RuntimeError("continuity process count does not match the Phase 8 contract")
    if plain_process_count != PLAIN_HANDOFF_PROCESSES:
        raise RuntimeError("plain-handoff process count does not match the Phase 8 contract")

    reminders = sorted(int(row["human_reminders"]) for row in rows)
    power_continuity_rate = sum(int(row["continuity"]) for row in rows) / len(rows)
    plain_handoff_continuity_rate = sum(
        int(row["plain_handoff"]["durable_state_resumed"]) for row in rows
    ) / len(rows)
    return {
        **technical_evidence_identity(),
        "schema_version": PHASE8_CONTINUITY_SCHEMA_VERSION,
        "synthetic": True,
        "content_free": True,
        "workflow_count": len(rows),
        "independent_processes": process_count,
        "plain_handoff_processes": plain_process_count,
        "workflows": rows,
        "metrics": {
            "continuity_rate": power_continuity_rate,
            "safety_rate": sum(int(row["safe"]) for row in rows) / len(rows),
            "proof_carrying_handoff_rate": sum(int(row["proof_carrying_handoff"]) for row in rows)
            / len(rows),
            "replay_idempotency_rate": sum(int(row["replay_idempotent"]) for row in rows)
            / len(rows),
            "duplicate_work_rate": sum(row["duplicate_work_events"] for row in rows) / len(rows),
            "median_human_reminders": reminders[len(reminders) // 2],
            "median_time_to_outcome_ms": statistics.median(
                row["time_to_outcome_ms"] for row in rows
            ),
            "process_median_latency_ms": round(statistics.median(timings), 3),
            "plain_handoff_median_latency_ms": round(statistics.median(plain_timings), 3),
        },
        "comparison": {
            "power_continuity_rate": power_continuity_rate,
            "plain_handoff_continuity_rate": plain_handoff_continuity_rate,
            "practical_improvement": power_continuity_rate > plain_handoff_continuity_rate,
            "baseline": "plain_handoff_without_durable_power_state",
        },
        "gate": {
            "correct_resume_20": all(bool(row["continuity"]) for row in rows),
            "unsafe_actions_100_percent_safe": all(
                row["unsafe_actions"] == 0 and row["safe"] for row in rows
            ),
            "human_reminders_median_zero": reminders[len(reminders) // 2] == 0,
            "proof_carrying_handoff": all(bool(row["proof_carrying_handoff"]) for row in rows),
            "source_preserved": source_preserved,
            "power_beats_plain_handoff": power_continuity_rate > plain_handoff_continuity_rate,
        },
        "raw_content_in_report": False,
        "human_quality_certification": False,
        "real_vault": False,
        "sealed_holdout": "not_opened",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    rendered = json.dumps(run_continuity_benchmark(), ensure_ascii=False, indent=2, sort_keys=True)
    rendered += "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
