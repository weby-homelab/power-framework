"""Phase 1 Contract and Schema Verification for POWER Project State Engine (PSE).

Tests compliance with:
- event-schema-v1.json (draft 2020-12)
- semantic-entity-schema-v1.json
- lifecycle-v1.json
- Deterministic canonical JSON serialization round-trip
- Mandatory entity provenance
- State machine transition rules and rollback flags
- Machine evaluation of DoR/DoD predicates and overrides
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

PHASE1_DIR = Path(__file__).parent.parent / "artifacts" / "project-state" / "phase-1"


@pytest.fixture(scope="session")
def event_schema() -> dict[str, Any]:
    schema_path = PHASE1_DIR / "event-schema-v1.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def semantic_schema() -> dict[str, Any]:
    schema_path = PHASE1_DIR / "semantic-entity-schema-v1.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def lifecycle_contract() -> dict[str, Any]:
    lifecycle_path = PHASE1_DIR / "lifecycle-v1.json"
    with open(lifecycle_path, "r", encoding="utf-8") as f:
        return json.load(f)


def canonical_json_dumps(data: Any) -> str:
    """Canonical JSON serialization conforming to Phase 1 contract."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_payload_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_dumps(payload).encode("utf-8")).hexdigest()


def compute_event_hash(event: dict[str, Any]) -> str:
    header_manifest = {
        "actor": event["actor"],
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "payload_digest": event["payload_digest"],
        "prev_event_hash": event["prev_event_hash"],
        "project_id": event["project_id"],
        "schema_version": event["schema_version"],
        "sequence": event["sequence"],
        "source": event["source"],
        "timestamp": event["timestamp"],
    }
    return hashlib.sha256(canonical_json_dumps(header_manifest).encode("utf-8")).hexdigest()


def make_valid_event(
    *,
    sequence: int = 1,
    event_type: str = "project.created",
    prev_event_hash: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if payload is None:
        payload = {"name": "Test Project", "objective": "Validate PSE contracts"}

    payload_digest = compute_payload_digest(payload)
    event: dict[str, Any] = {
        "event_id": f"evt_prj_test_engine_{sequence}_abcdef0123",
        "schema_version": "1.0",
        "project_id": "prj_test_engine",
        "sequence": sequence,
        "timestamp": "2026-09-03T16:00:00Z",
        "actor": "user:rekvizitor",
        "source": "cli",
        "session_id": "ses_12345",
        "event_type": event_type,
        "payload": payload,
        "payload_digest": payload_digest,
        "prev_event_hash": prev_event_hash,
        "event_hash": "",
        "artifact_refs": ["01_Projects/test/charter.md"],
        "evidence_refs": ["tcr_0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"],
        "correlation_id": "corr_abc",
        "causation_id": None,
        "idempotency_key": f"idem_test_{sequence}",
    }
    event["event_hash"] = compute_event_hash(event)
    return event


def validate_semantic_entity(entity: dict[str, Any], entity_type: str, schema: dict[str, Any]) -> None:
    """Validate a semantic entity against a specific definition within the root schema."""
    subschema = {
        "$schema": schema.get("$schema", "https://json-schema.org/draft/2020-12/schema"),
        "$defs": schema["$defs"],
        "$ref": f"#/$defs/{entity_type}",
    }
    jsonschema.validate(instance=entity, schema=subschema)


# ==============================================================================
# 1. Event Schema Tests: Valid Event, Bad Version, Bad ID, Bad Timestamp, Bad Enum
# ==============================================================================


def test_valid_project_event_passes_schema(event_schema: dict[str, Any]) -> None:
    event = make_valid_event()
    jsonschema.validate(instance=event, schema=event_schema)


def test_event_schema_rejects_invalid_schema_version(event_schema: dict[str, Any]) -> None:
    event = make_valid_event()
    event["schema_version"] = "2.0"
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        jsonschema.validate(instance=event, schema=event_schema)
    assert "'2.0' is not one of" in str(exc_info.value) or "schema_version" in str(exc_info.value)


def test_event_schema_rejects_invalid_project_id(event_schema: dict[str, Any]) -> None:
    event = make_valid_event()
    # Missing prj_ prefix
    event["project_id"] = "invalid_id_without_prefix"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=event, schema=event_schema)

    # Illegal uppercase in slug or invalid characters
    event["project_id"] = "prj_INVALID/PATH"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=event, schema=event_schema)


def test_event_schema_rejects_invalid_timestamp(event_schema: dict[str, Any]) -> None:
    event = make_valid_event()
    event["timestamp"] = "not-a-timestamp"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=event, schema=event_schema)


def test_event_schema_rejects_unknown_event_type_enum(event_schema: dict[str, Any]) -> None:
    event = make_valid_event()
    event["event_type"] = "project.telemetry.unknown_action"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=event, schema=event_schema)


# ==============================================================================
# 2. Deterministic Serialization & Round-Trip Tests
# ==============================================================================


def test_canonical_serialization_round_trip() -> None:
    original_dict = {
        "z_field": 100,
        "a_field": "test value with unicode: українська мова 🚀",
        "m_nested": {
            "sub_b": False,
            "sub_a": [3, 2, 1],
            "sub_c": None,
        },
    }

    serialized_1 = canonical_json_dumps(original_dict)
    deserialized = json.loads(serialized_1)
    serialized_2 = canonical_json_dumps(deserialized)

    assert serialized_1 == serialized_2
    assert serialized_1.startswith('{"a_field":')
    assert '"m_nested":{"sub_a":[3,2,1],"sub_b":false,"sub_c":null}' in serialized_1
    assert "українська мова 🚀" in serialized_1


def test_hash_chain_verification() -> None:
    event1 = make_valid_event(sequence=1, event_type="project.created", prev_event_hash="")
    event2 = make_valid_event(
        sequence=2,
        event_type="task.associated",
        prev_event_hash=event1["event_hash"],
        payload={"task_id": "tsk_001", "relation": "core_deliverable"},
    )

    assert compute_event_hash(event1) == event1["event_hash"]
    assert compute_event_hash(event2) == event2["event_hash"]
    assert event2["prev_event_hash"] == event1["event_hash"]

    tampered_event1 = dict(event1)
    tampered_event1["payload"] = {"name": "Tampered Name"}
    tampered_digest = compute_payload_digest(tampered_event1["payload"])
    assert tampered_digest != event1["payload_digest"]


# ==============================================================================
# 3. Semantic Entity Contracts & Mandatory Provenance
# ==============================================================================


def test_semantic_entities_require_mandatory_provenance(semantic_schema: dict[str, Any]) -> None:
    valid_project = {
        "project_id": "prj_power_3_8_pse",
        "title": "POWER 3.8 Project State Engine",
        "description": "Deterministic project state management",
        "charter": "Build production-grade project state engine",
        "state": "PLANNING",
        "owner": "user:rekvizitor",
        "repo_ref": "weby-homelab/power-framework",
        "vault_path": "01_Projects/Power_PSE",
        "task_refs": ["tsk_001"],
        "decision_refs": ["dec_001"],
        "tags": ["core", "pse", "3.8"],
        "provenance": {
            "source_event_id": "evt_prj_power_3_8_pse_1_abcdef01",
            "actor": "user:rekvizitor",
            "timestamp": "2026-09-03T16:30:00Z",
            "source_type": "event_replay",
            "correlation_id": "corr_setup",
        },
        "created_at": "2026-09-03T16:00:00Z",
        "updated_at": "2026-09-03T16:30:00Z",
    }
    validate_semantic_entity(valid_project, "Project", semantic_schema)

    # Missing provenance entirely
    invalid_project = dict(valid_project)
    del invalid_project["provenance"]
    with pytest.raises(jsonschema.ValidationError) as exc_info:
        validate_semantic_entity(invalid_project, "Project", semantic_schema)
    assert "'provenance' is a required property" in str(exc_info.value)

    # Incomplete provenance (missing actor)
    invalid_provenance_project = dict(valid_project)
    invalid_provenance_project["provenance"] = {
        "source_event_id": "evt_1",
        "timestamp": "2026-09-03T16:30:00Z",
        "source_type": "event_replay",
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_semantic_entity(invalid_provenance_project, "Project", semantic_schema)


def test_raid_and_raci_semantic_schemas(semantic_schema: dict[str, Any]) -> None:
    valid_risk = {
        "risk_id": "rsk_perf_degradation",
        "project_id": "prj_power_3_8_pse",
        "title": "High event replay latency on massive vaults",
        "probability": "low",
        "impact": "high",
        "mitigation_plan": "Snapshot checkpoints and SQLite query projections",
        "owner": "agent:agy",
        "status": "identified",
        "related_task_ids": ["tsk_snapshot_builder"],
        "provenance": {
            "source_event_id": "evt_prj_power_3_8_pse_3_abcdef03",
            "actor": "agent:agy",
            "timestamp": "2026-09-03T17:00:00Z",
            "source_type": "direct_mutation",
        },
        "created_at": "2026-09-03T17:00:00Z",
        "updated_at": "2026-09-03T17:00:00Z",
    }
    validate_semantic_entity(valid_risk, "Risk", semantic_schema)

    valid_raci = {
        "raci_id": "raci_phase_1_contract",
        "project_id": "prj_power_3_8_pse",
        "scope_ref": "milestone_phase_1",
        "responsible": ["agent:agy", "user:developer"],
        "accountable": "user:rekvizitor",  # Strictly ONE accountable actor
        "consulted": ["agent:code-reviewer"],
        "informed": ["user:observer"],
        "provenance": {
            "source_event_id": "evt_prj_power_3_8_pse_4_abcdef04",
            "actor": "user:rekvizitor",
            "timestamp": "2026-09-03T17:15:00Z",
            "source_type": "direct_mutation",
        },
        "updated_at": "2026-09-03T17:15:00Z",
    }
    validate_semantic_entity(valid_raci, "RACI", semantic_schema)


# ==============================================================================
# 4. Lifecycle State Machine Transition Contract Tests
# ==============================================================================


def test_lifecycle_transitions_table(lifecycle_contract: dict[str, Any]) -> None:
    transitions = lifecycle_contract["transitions"]
    allowed_map: dict[str, set[str]] = {}
    rollback_map: dict[tuple[str, str], bool] = {}

    for t in transitions:
        from_s = t["from_state"]
        to_s = t["to_state"]
        allowed_map.setdefault(from_s, set()).add(to_s)
        rollback_map[(from_s, to_s)] = t["is_rollback"]

    # Test valid progression
    assert "PLANNING" in allowed_map["DISCOVERY"]
    assert "EXECUTION" in allowed_map["PLANNING"]
    assert "MONITORING" in allowed_map["EXECUTION"]
    assert "CLOSING" in allowed_map["EXECUTION"]
    assert "CLOSED" in allowed_map["CLOSING"]

    # Test illegal direct leaps
    assert "EXECUTION" not in allowed_map["DISCOVERY"]
    assert "CLOSING" not in allowed_map["DISCOVERY"]
    assert "CLOSING" not in allowed_map["PLANNING"]

    # Test rollback semantics
    assert rollback_map[("EXECUTION", "PLANNING")] is True
    assert rollback_map[("CLOSING", "EXECUTION")] is True
    assert rollback_map[("PLANNING", "EXECUTION")] is False

    # Test reopen semantics from CLOSED
    assert "PLANNING" in allowed_map["CLOSED"]
    assert "EXECUTION" in allowed_map["CLOSED"]
    assert rollback_map[("CLOSED", "PLANNING")] is True


# ==============================================================================
# 5. Machine-Evaluable DoR and DoD Rule Evaluation Tests
# ==============================================================================


class QualityGateEvaluator:
    """Evaluates DoR and DoD rules against live project/subsystem state."""

    @staticmethod
    def evaluate_rule(rule: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        predicate = rule["predicate_kind"]
        rule_id = rule["rule_id"]

        if predicate == "all_tasks_terminal":
            tasks = context.get("tasks", [])
            non_terminal = [t for t in tasks if t.get("state") not in {"completed", "failed", "canceled"}]
            passed = len(non_terminal) == 0
            msg = "All tasks are terminal" if passed else f"{len(non_terminal)} tasks still non-terminal"
            return {"rule_id": rule_id, "passed": passed, "message": msg, "evidence_ref": None}

        elif predicate == "no_open_blockers":
            issues = context.get("issues", [])
            blockers = [i for i in issues if i.get("severity") == "blocker" and i.get("status") == "open"]
            passed = len(blockers) == 0
            msg = "No open blockers" if passed else f"{len(blockers)} open blocker issues detected"
            return {"rule_id": rule_id, "passed": passed, "message": msg, "evidence_ref": None}

        elif predicate == "receipt_present":
            receipts = context.get("receipts", [])
            passed = len(receipts) > 0
            msg = "Completion receipt present" if passed else "No completion receipt found"
            return {"rule_id": rule_id, "passed": passed, "message": msg, "evidence_ref": receipts[0] if receipts else None}

        elif predicate == "assumption_validated":
            assumptions = context.get("assumptions", [])
            unvalidated = [a for a in assumptions if a.get("status") != "valid" and a.get("status") != "confirmed"]
            passed = len(unvalidated) == 0
            msg = "All assumptions valid" if passed else f"{len(unvalidated)} assumptions unvalidated"
            return {"rule_id": rule_id, "passed": passed, "message": msg, "evidence_ref": None}

        raise ValueError(f"Unknown predicate: {predicate}")

    @classmethod
    def evaluate_gate(
        cls,
        rules: list[dict[str, Any]],
        context: dict[str, Any],
        override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        evaluations = [cls.evaluate_rule(r, context) for r in rules]
        blocking_failed = any(
            not ev["passed"]
            for ev, r in zip(evaluations, rules)
            if r.get("severity") == "blocking"
        )

        if not blocking_failed:
            overall = "passed"
            passed = True
        elif override is not None:
            overall = "overridden"
            passed = True
        else:
            overall = "failed"
            passed = False

        return {
            "passed": passed,
            "overall_status": overall,
            "rule_evaluations": evaluations,
            "override": override,
        }


def test_dor_dod_machine_evaluation_success() -> None:
    rules = [
        {
            "rule_id": "dod_tasks_terminal",
            "category": "dod",
            "phase": "CLOSING",
            "description": "All project tasks must reach terminal state",
            "predicate_kind": "all_tasks_terminal",
            "predicate_params": {},
            "severity": "blocking",
        },
        {
            "rule_id": "dod_no_blockers",
            "category": "dod",
            "phase": "CLOSING",
            "description": "Zero open blocker issues",
            "predicate_kind": "no_open_blockers",
            "predicate_params": {},
            "severity": "blocking",
        },
        {
            "rule_id": "dod_receipt_verification",
            "category": "dod",
            "phase": "CLOSING",
            "description": "Terminal completion receipt must be attached",
            "predicate_kind": "receipt_present",
            "predicate_params": {},
            "severity": "blocking",
        },
    ]

    context = {
        "tasks": [{"task_id": "t1", "state": "completed"}, {"task_id": "t2", "state": "canceled"}],
        "issues": [{"issue_id": "i1", "severity": "minor", "status": "open"}],
        "receipts": ["tcr_1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"],
    }

    result = QualityGateEvaluator.evaluate_gate(rules, context)
    assert result["passed"] is True
    assert result["overall_status"] == "passed"
    assert all(r["passed"] for r in result["rule_evaluations"])


def test_dor_dod_machine_evaluation_failure_and_override() -> None:
    rules = [
        {
            "rule_id": "dod_tasks_terminal",
            "category": "dod",
            "phase": "CLOSING",
            "description": "All project tasks must reach terminal state",
            "predicate_kind": "all_tasks_terminal",
            "predicate_params": {},
            "severity": "blocking",
        },
        {
            "rule_id": "dod_no_blockers",
            "category": "dod",
            "phase": "CLOSING",
            "description": "Zero open blocker issues",
            "predicate_kind": "no_open_blockers",
            "predicate_params": {},
            "severity": "blocking",
        },
    ]

    # Context with an active blocker issue
    failing_context = {
        "tasks": [{"task_id": "t1", "state": "completed"}],
        "issues": [{"issue_id": "i2", "severity": "blocker", "status": "open"}],
    }

    # Evaluate without override: must fail
    res_fail = QualityGateEvaluator.evaluate_gate(rules, failing_context)
    assert res_fail["passed"] is False
    assert res_fail["overall_status"] == "failed"
    assert res_fail["rule_evaluations"][1]["passed"] is False
    assert "1 open blocker issues detected" in res_fail["rule_evaluations"][1]["message"]

    # Evaluate with formal override: status becomes overridden and passed
    override = {
        "overridden_by": "user:rekvizitor",
        "justification": "Blocker mitigated via hotfix in branch 3.8-hf1",
        "timestamp": "2026-09-03T18:00:00Z",
        "approved_by": "user:rekvizitor",
    }
    res_override = QualityGateEvaluator.evaluate_gate(rules, failing_context, override=override)
    assert res_override["passed"] is True
    assert res_override["overall_status"] == "overridden"
    assert res_override["override"] == override
