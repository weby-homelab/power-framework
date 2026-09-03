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

from power_framework.core.canonical_json import (
    canonical_json_dumps,
    compute_event_hash,
    compute_payload_digest,
)
from power_framework.core.task_models import TERMINAL_STATES

PHASE1_DIR = Path(__file__).parent.parent / "artifacts" / "project-state" / "phase-1"


@pytest.fixture(scope="session")
def event_schema() -> dict[str, Any]:
    schema_path = PHASE1_DIR / "event-schema-v1.json"
    with open(schema_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def semantic_schema() -> dict[str, Any]:
    schema_path = PHASE1_DIR / "semantic-entity-schema-v1.json"
    with open(schema_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def lifecycle_contract() -> dict[str, Any]:
    lifecycle_path = PHASE1_DIR / "lifecycle-v1.json"
    with open(lifecycle_path, encoding="utf-8") as f:
        return json.load(f)


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
        "schema_version": "power.project-event.v1",
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


def validate_semantic_entity(
    entity: dict[str, Any], entity_type: str, schema: dict[str, Any]
) -> None:
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
    assert event["schema_version"] == "power.project-event.v1"
    jsonschema.validate(instance=event, schema=event_schema)

    # Legacy alias '1.0' is rejected in stored schema
    event_legacy = make_valid_event()
    event_legacy["schema_version"] = "1.0"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=event_legacy, schema=event_schema)

    # Arbitrary other version rejected
    event_bad = make_valid_event()
    event_bad["schema_version"] = "2.0"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=event_bad, schema=event_schema)


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


def test_event_schema_accepts_saga_events_and_rejects_deprecated_events(
    event_schema: dict[str, Any],
) -> None:
    valid_saga_types = [
        "task.association.requested",
        "task.associated",
        "task.disassociated",
        "task.association.failed",
        "task.lifecycle.observed",
        "decision.association.requested",
        "decision.associated",
        "decision.disassociated",
        "decision.association.failed",
        "decision.lifecycle.observed",
    ]
    for et in valid_saga_types:
        ev = make_valid_event(event_type=et)
        jsonschema.validate(instance=ev, schema=event_schema)

    deprecated_shadow_types = [
        "task.created",
        "task.updated",
        "task.completed",
        "decision.proposed",
        "decision.accepted",
        "decision.rejected",
        "decision.superseded",
    ]
    for det in deprecated_shadow_types:
        ev = make_valid_event(event_type=det)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=ev, schema=event_schema)


# ==============================================================================
# 2. Deterministic Serialization & POWER Canonical JSON v1 Tests
# ==============================================================================


def test_power_canonical_json_v1_round_trip() -> None:
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


def test_power_canonical_json_v1_rejects_nan_and_infinity() -> None:
    for bad_val in [float("nan"), float("inf"), float("-inf")]:
        with pytest.raises(ValueError, match="NaN and Infinity values"):
            canonical_json_dumps({"metric": bad_val})


def test_power_canonical_json_v1_frozen_byte_vector() -> None:
    """Validate POWER Canonical JSON v1 exact byte sequence and frozen SHA-256 digest vector.

    In Phase 2, the canonicalizer will be implemented in a single authoritative production core module,
    from which all tests and runtime services will import it.
    """
    input_data = {"z": 1, "a": "Україна", "nested": {"b": False, "a": None}}

    expected_text = '{"a":"Україна","nested":{"a":null,"b":false},"z":1}'
    expected_bytes = b'{"a":"\xd0\xa3\xd0\xba\xd1\x80\xd0\xb0\xd1\x97\xd0\xbd\xd0\xb0","nested":{"a":null,"b":false},"z":1}'
    expected_sha256 = "9cfb88b8b7087e11cd405596bc4b988dc2c49164d1ccbe21a35e25c0bd971a98"

    serialized_text = canonical_json_dumps(input_data)
    assert serialized_text == expected_text

    serialized_bytes = serialized_text.encode("utf-8")
    assert serialized_bytes == expected_bytes

    digest = hashlib.sha256(serialized_bytes).hexdigest()
    assert digest == expected_sha256


def test_hash_chain_verification() -> None:
    event1 = make_valid_event(sequence=1, event_type="project.created", prev_event_hash="")
    event2 = make_valid_event(
        sequence=2,
        event_type="task.associated",
        prev_event_hash=event1["event_hash"],
        payload={"task_id": "tsk_001", "relation": "core_deliverable"},
    )

    # Genesis rule: sequence 1 requires empty prev_event_hash
    assert event1["sequence"] == 1
    assert event1["prev_event_hash"] == ""

    # Non-genesis rule: sequence > 1 requires non-empty prev_event_hash matching predecessor event_hash
    assert event2["sequence"] == 2
    assert event2["prev_event_hash"] != ""
    assert event2["prev_event_hash"] == event1["event_hash"]

    assert compute_event_hash(event1) == event1["event_hash"]
    assert compute_event_hash(event2) == event2["event_hash"]

    tampered_event1 = dict(event1)
    tampered_event1["payload"] = {"name": "Tampered Name"}
    tampered_digest = compute_payload_digest(tampered_event1["payload"])
    assert tampered_digest != event1["payload_digest"]


def test_full_envelope_tampering_fails_verification() -> None:
    base_event = make_valid_event(
        sequence=1,
        event_type="project.created",
        prev_event_hash="",
        payload={"title": "Original Project"},
    )
    original_hash = base_event["event_hash"]

    # Critical envelope fields whose mutation must break event_hash verification
    tamper_cases = [
        ("actor", "user:impostor"),
        ("timestamp", "2026-09-03T19:00:00Z"),
        ("artifact_refs", ["01_Projects/test/malicious.md"]),
        ("evidence_refs", ["tcr_9999999999abcdef9999999999abcdef9999999999abcdef9999999999abcdef"]),
        ("causation_id", "cmd_tampered_001"),
        ("correlation_id", "corr_injected"),
        ("session_id", "ses_forged"),
        ("sequence", 99),
        ("source", "untrusted_source"),
        ("prev_event_hash", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"),
    ]

    for field, tampered_val in tamper_cases:
        mutated = dict(base_event)
        mutated[field] = tampered_val
        tampered_hash = compute_event_hash(mutated)
        assert tampered_hash != original_hash, (
            f"Tampering field '{field}' failed to invalidate hash!"
        )


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
            "source_event_ids": ["evt_prj_power_3_8_pse_1_abcdef01"],
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
        "source_event_ids": ["evt_1"],
        "timestamp": "2026-09-03T16:30:00Z",
        "source_type": "event_replay",
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_semantic_entity(invalid_provenance_project, "Project", semantic_schema)

    # Empty source_event_ids
    empty_events_project = dict(valid_project)
    empty_events_project["provenance"] = {
        "source_event_ids": [],
        "actor": "user:rekvizitor",
        "timestamp": "2026-09-03T16:30:00Z",
        "source_type": "event_replay",
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_semantic_entity(empty_events_project, "Project", semantic_schema)

    # Duplicate source_event_ids
    dup_events_project = dict(valid_project)
    dup_events_project["provenance"] = {
        "source_event_ids": ["evt_prj_1", "evt_prj_1"],
        "actor": "user:rekvizitor",
        "timestamp": "2026-09-03T16:30:00Z",
        "source_type": "event_replay",
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_semantic_entity(dup_events_project, "Project", semantic_schema)


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
            "source_event_ids": ["evt_prj_power_3_8_pse_3_abcdef03"],
            "actor": "agent:agy",
            "timestamp": "2026-09-03T17:00:00Z",
            "source_type": "direct_mutation",
        },
        "created_at": "2026-09-03T17:00:00Z",
        "updated_at": "2026-09-03T17:00:00Z",
    }
    validate_semantic_entity(valid_risk, "Risk", semantic_schema)

    valid_assumption = {
        "assumption_id": "asm_git_clean_state",
        "project_id": "prj_power_3_8_pse",
        "statement": "Host worktree has a clean working tree before phase execution",
        "rationale": "Prevents accidental dirty commits",
        "confidence": 0.95,
        "status": "confirmed",
        "provenance": {
            "source_event_ids": ["evt_prj_power_3_8_pse_2_abcdef02"],
            "actor": "user:rekvizitor",
            "timestamp": "2026-09-03T16:45:00Z",
            "source_type": "direct_mutation",
        },
        "created_at": "2026-09-03T16:45:00Z",
    }
    validate_semantic_entity(valid_assumption, "Assumption", semantic_schema)

    valid_issue = {
        "issue_id": "iss_sqlite_lock_contention",
        "project_id": "prj_power_3_8_pse",
        "title": "SQLite WAL concurrency under high MCP query rate",
        "description": "WAL busy timeouts observed during parallel index scans",
        "severity": "major",
        "status": "investigating",
        "blocking_task_ids": [],
        "provenance": {
            "source_event_ids": ["evt_prj_power_3_8_pse_5_abcdef05"],
            "actor": "agent:agy",
            "timestamp": "2026-09-03T17:30:00Z",
            "source_type": "direct_mutation",
        },
        "created_at": "2026-09-03T17:30:00Z",
    }
    validate_semantic_entity(valid_issue, "Issue", semantic_schema)

    valid_dependency = {
        "dependency_id": "dep_pse_core_taskstore",
        "project_id": "prj_power_3_8_pse",
        "source_id": "tsk_pse_coordinator",
        "target_id": "tsk_taskstore_v2",
        "target_type": "task",
        "dependency_kind": "requires",
        "status": "satisfied",
        "provenance": {
            "source_event_ids": ["evt_prj_power_3_8_pse_6_abcdef06"],
            "actor": "user:rekvizitor",
            "timestamp": "2026-09-03T17:45:00Z",
            "source_type": "direct_mutation",
        },
        "created_at": "2026-09-03T17:45:00Z",
    }
    validate_semantic_entity(valid_dependency, "Dependency", semantic_schema)

    valid_raci = {
        "raci_id": "raci_phase_1_contract",
        "project_id": "prj_power_3_8_pse",
        "scope_ref": "milestone_phase_1",
        "responsible": ["agent:agy", "user:developer"],
        "accountable": "user:rekvizitor",  # Strictly ONE accountable actor
        "consulted": ["agent:code-reviewer"],
        "informed": ["user:observer"],
        "provenance": {
            "source_event_ids": ["evt_prj_power_3_8_pse_4_abcdef04"],
            "actor": "user:rekvizitor",
            "timestamp": "2026-09-03T17:15:00Z",
            "source_type": "direct_mutation",
        },
        "updated_at": "2026-09-03T17:15:00Z",
    }
    validate_semantic_entity(valid_raci, "RACI", semantic_schema)


def test_all_semantic_entity_types_schema_validation(semantic_schema: dict[str, Any]) -> None:
    common_provenance = {
        "source_event_ids": ["evt_prj_power_3_8_pse_10_abcdef10"],
        "actor": "agent:agy",
        "timestamp": "2026-09-03T18:00:00Z",
        "source_type": "agent_inference",
    }

    # 1. Fact
    valid_fact = {
        "fact_id": "fct_kernel_threads",
        "project_id": "prj_power_3_8_pse",
        "statement": "WS server has 10 cores / 20 threads Intel Xeon E5-2666 v3",
        "category": "technical",
        "verified_at": "2026-09-03T18:00:00Z",
        "verification_method": "lscpu check",
        "provenance": common_provenance,
        "created_at": "2026-09-03T18:00:00Z",
    }
    validate_semantic_entity(valid_fact, "Fact", semantic_schema)

    bad_fact = dict(valid_fact)
    bad_fact["fact_id"] = "invalid_prefix_fact"
    with pytest.raises(jsonschema.ValidationError):
        validate_semantic_entity(bad_fact, "Fact", semantic_schema)

    # 2. Hypothesis
    valid_hypo = {
        "hypothesis_id": "hyp_wal_checkpoint_perf",
        "project_id": "prj_power_3_8_pse",
        "statement": "Enabling PRAGMA synchronous=NORMAL reduces SQLite write latency by 40%",
        "confidence": 0.8,
        "status": "testing",
        "provenance": common_provenance,
        "created_at": "2026-09-03T18:05:00Z",
    }
    validate_semantic_entity(valid_hypo, "Hypothesis", semantic_schema)

    bad_hypo = dict(valid_hypo)
    bad_hypo["confidence"] = 1.5  # Out of range 0.0-1.0
    with pytest.raises(jsonschema.ValidationError):
        validate_semantic_entity(bad_hypo, "Hypothesis", semantic_schema)

    # 3. Observation
    valid_obs = {
        "observation_id": "obs_memory_headroom",
        "project_id": "prj_power_3_8_pse",
        "content": "Available RAM is 124GB, zero swap pressure during indexing test",
        "observed_at": "2026-09-03T18:10:00Z",
        "provenance": common_provenance,
        "created_at": "2026-09-03T18:10:00Z",
    }
    validate_semantic_entity(valid_obs, "Observation", semantic_schema)

    bad_obs = dict(valid_obs)
    del bad_obs["observed_at"]
    with pytest.raises(jsonschema.ValidationError):
        validate_semantic_entity(bad_obs, "Observation", semantic_schema)

    # 4. Lesson
    valid_lesson = {
        "lesson_id": "lsn_sequential_edits_mandate",
        "project_id": "prj_power_3_8_pse",
        "title": "Always perform sequential single replace per tool turn",
        "summary": "Parallel replacements in the same file risk race collisions in agent harness",
        "category": "process",
        "recommendation": "Execute edits one block per turn and validate immediately",
        "provenance": common_provenance,
        "created_at": "2026-09-03T18:15:00Z",
    }
    validate_semantic_entity(valid_lesson, "Lesson", semantic_schema)

    bad_lesson = dict(valid_lesson)
    del bad_lesson["recommendation"]
    with pytest.raises(jsonschema.ValidationError):
        validate_semantic_entity(bad_lesson, "Lesson", semantic_schema)

    # 5. DecisionReference
    valid_dref = {
        "decision_ref_id": "dref_adr_pse_004_integration",
        "project_id": "prj_power_3_8_pse",
        "decision_id": "dec_use_taskstore_v2_canonical",
        "relation": "architectural_boundary",
        "status": "accepted",
        "task_id": "tsk_pse_001",
        "provenance": common_provenance,
        "created_at": "2026-09-03T18:20:00Z",
    }
    validate_semantic_entity(valid_dref, "DecisionReference", semantic_schema)

    bad_dref = dict(valid_dref)
    bad_dref["status"] = "non_existent_status"
    with pytest.raises(jsonschema.ValidationError):
        validate_semantic_entity(bad_dref, "DecisionReference", semantic_schema)


def test_multi_event_provenance_and_epistemic_fields(semantic_schema: dict[str, Any]) -> None:
    multi_provenance = {
        "source_event_ids": [
            "evt_prj_power_3_8_pse_11_abcdef11",
            "evt_prj_power_3_8_pse_12_abcdef12",
        ],
        "primary_source_event_id": "evt_prj_power_3_8_pse_11_abcdef11",
        "actor": "agent:agy",
        "timestamp": "2026-09-03T18:30:00Z",
        "source_type": "agent_inference",
        "correlation_id": "corr_deep_audit",
        "evidence_refs": ["tcr_0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"],
        "confidence": 0.88,
        "verification_status": "verified",
        "valid_from": "2026-09-03T18:30:00Z",
        "valid_to": "2026-12-31T23:59:59Z",
        "supersedes": "hyp_old_hypothesis_01",
        "invalidates": "asm_stale_assumption_02",
    }

    hypo_entity = {
        "hypothesis_id": "hyp_multi_source_deduction",
        "project_id": "prj_power_3_8_pse",
        "statement": "Correlating event logs with task completion receipts proves zero dropped tasks",
        "confidence": 0.88,
        "status": "validated",
        "provenance": multi_provenance,
        "created_at": "2026-09-03T18:30:00Z",
    }
    validate_semantic_entity(hypo_entity, "Hypothesis", semantic_schema)


# ==============================================================================
# 4. Lifecycle State Machine Transition Contract Tests
# ==============================================================================


def test_lifecycle_transitions_table(lifecycle_contract: dict[str, Any]) -> None:
    transitions = lifecycle_contract["transitions"]
    assert len(transitions) == 17, f"Expected exactly 17 transitions, found {len(transitions)}"

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
    assert rollback_map[("CLOSED", "EXECUTION")] is True


def test_closed_state_contract_semantics(lifecycle_contract: dict[str, Any]) -> None:
    states = lifecycle_contract["states"]
    closed_state = next(s for s in states if s["name"] == "CLOSED")
    assert closed_state.get("is_closed") is True
    assert closed_state.get("normal_mutations_blocked") is True
    assert closed_state.get("requires_explicit_reopen") is True


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
            non_terminal = [t for t in tasks if t.get("state") not in TERMINAL_STATES]
            passed = len(non_terminal) == 0
            msg = (
                "All tasks are terminal"
                if passed
                else f"{len(non_terminal)} tasks still non-terminal"
            )
            return {"rule_id": rule_id, "passed": passed, "message": msg, "evidence_ref": None}

        if predicate == "no_open_blockers":
            issues = context.get("issues", [])
            unresolved_blockers = [
                i
                for i in issues
                if i.get("severity") == "blocker" and i.get("status") not in {"resolved", "closed"}
            ]
            passed = len(unresolved_blockers) == 0
            msg = (
                "No unresolved blockers"
                if passed
                else f"{len(unresolved_blockers)} unresolved blocker issues detected"
            )
            return {"rule_id": rule_id, "passed": passed, "message": msg, "evidence_ref": None}

        if predicate == "receipt_present":
            receipts = context.get("receipts", [])
            passed = len(receipts) > 0
            msg = "Completion receipt present" if passed else "No completion receipt found"
            return {
                "rule_id": rule_id,
                "passed": passed,
                "message": msg,
                "evidence_ref": receipts[0] if receipts else None,
            }

        if predicate == "assumption_validated":
            assumptions = context.get("assumptions", [])
            unvalidated = [
                a
                for a in assumptions
                if a.get("status") != "valid" and a.get("status") != "confirmed"
            ]
            passed = len(unvalidated) == 0
            msg = (
                "All assumptions valid" if passed else f"{len(unvalidated)} assumptions unvalidated"
            )
            return {"rule_id": rule_id, "passed": passed, "message": msg, "evidence_ref": None}

        if predicate == "registered_policy":
            policy_fn = context.get("policies", {}).get(rule_id)
            passed = bool(policy_fn(context)) if policy_fn else False
            return {
                "rule_id": rule_id,
                "passed": passed,
                "message": f"Policy {rule_id}: {passed}",
                "evidence_ref": None,
            }

        if predicate == "custom_script":
            raise PermissionError(
                "Arbitrary custom_script execution is prohibited in DoR/DoD quality gates"
            )

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
            for ev, r in zip(evaluations, rules, strict=True)
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
    assert "1 unresolved blocker issues detected" in res_fail["rule_evaluations"][1]["message"]

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


def test_task_v2_rejected_is_terminal_for_dor_dod() -> None:
    assert "rejected" in TERMINAL_STATES
    assert {"completed", "failed", "canceled", "rejected"} == TERMINAL_STATES

    rules = [
        {
            "rule_id": "dod_tasks_terminal",
            "category": "dod",
            "phase": "CLOSING",
            "predicate_kind": "all_tasks_terminal",
            "predicate_params": {},
            "severity": "blocking",
        }
    ]
    context = {
        "tasks": [
            {"task_id": "t1", "state": "rejected"},
            {"task_id": "t2", "state": "completed"},
        ]
    }
    result = QualityGateEvaluator.evaluate_gate(rules, context)
    assert result["passed"] is True
    assert result["overall_status"] == "passed"


def test_blocker_issue_investigating_is_not_resolved() -> None:
    rule = {
        "rule_id": "dod_no_blockers",
        "category": "dod",
        "phase": "CLOSING",
        "predicate_kind": "no_open_blockers",
        "predicate_params": {},
        "severity": "blocking",
    }

    # Investigating blocker MUST NOT be considered resolved
    ctx_investigating = {
        "issues": [{"issue_id": "i_inv", "severity": "blocker", "status": "investigating"}]
    }
    res_inv = QualityGateEvaluator.evaluate_rule(rule, ctx_investigating)
    assert res_inv["passed"] is False
    assert "1 unresolved blocker issues detected" in res_inv["message"]

    # Open blocker fails
    ctx_open = {"issues": [{"issue_id": "i_open", "severity": "blocker", "status": "open"}]}
    res_open = QualityGateEvaluator.evaluate_rule(rule, ctx_open)
    assert res_open["passed"] is False

    # Resolved blocker passes
    ctx_resolved = {"issues": [{"issue_id": "i_res", "severity": "blocker", "status": "resolved"}]}
    res_resolved = QualityGateEvaluator.evaluate_rule(rule, ctx_resolved)
    assert res_resolved["passed"] is True

    # Closed blocker passes
    ctx_closed = {"issues": [{"issue_id": "i_cls", "severity": "blocker", "status": "closed"}]}
    res_closed = QualityGateEvaluator.evaluate_rule(rule, ctx_closed)
    assert res_closed["passed"] is True


def test_dor_dod_prohibits_custom_script_and_accepts_registered_policy(
    semantic_schema: dict[str, Any],
) -> None:
    # 1. Schema prohibits custom_script
    bad_rule = {
        "rule_id": "rule_arbitrary_eval",
        "category": "dod",
        "phase": "CLOSING",
        "description": "Attempting arbitrary script execution",
        "predicate_kind": "custom_script",
        "predicate_params": {"script": "rm -rf /"},
        "severity": "blocking",
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_semantic_entity(bad_rule, "DoRDoDRule", semantic_schema)

    # 2. Schema accepts registered_policy
    good_rule = {
        "rule_id": "rule_policy_eval",
        "category": "dod",
        "phase": "CLOSING",
        "description": "Verified registered policy execution",
        "predicate_kind": "registered_policy",
        "predicate_params": {"policy_name": "verify_security_audit"},
        "severity": "blocking",
    }
    validate_semantic_entity(good_rule, "DoRDoDRule", semantic_schema)

    # 3. Evaluator rejects custom_script at runtime fail-closed
    with pytest.raises(PermissionError):
        QualityGateEvaluator.evaluate_rule(bad_rule, {})

    # 4. Evaluator executes registered_policy
    ctx = {"policies": {"rule_policy_eval": lambda c: True}}
    res = QualityGateEvaluator.evaluate_rule(good_rule, ctx)
    assert res["passed"] is True
