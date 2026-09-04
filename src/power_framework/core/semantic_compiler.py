"""POWER Project State Engine (PSE) Phase 3 — Project Semantic Compiler.

Transforms canonical events and unstructured text/observations into typed,
provenance-bound, validated semantic entities and proposals.

Pipeline Architecture:
event -> deterministic normalization -> structured parser -> optional model extraction
 -> entity candidates -> deduplication -> provenance linking
 -> contradiction/supersession proposal -> validation -> candidate entities.

Strict Gating Guarantees:
- G3.1: Structured events require no LLM (Deterministic-First).
- G3.2: Model-extracted candidates cannot bypass verification policy (strictly 'proposed' / 'unverified').
- G3.3: Every entity has mandatory, complete provenance.
- G3.4: Re-compilation is deterministic and idempotent.
- G3.5: Contradictions and supersessions preserve history; old records are never deleted.
- G3.6: Untrusted text is isolated; prompt injection attempts cannot escape or alter policy.
- G3.7: Evaluation metrics report precision, recall, false-verified rate (0.0), and contradiction rate.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from copy import deepcopy
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from power_framework.core.canonical_json import (
    compute_event_hash,
    compute_payload_digest,
)
from power_framework.core.project_ingestion import replay_project_verified
from power_framework.core.project_models import (
    PROJECT_EVENT_TYPES,
    ProjectEvent,
    TrustedReplayReceipt,
    VerifiedReplayBatch,
    validate_project_id,
)
from power_framework.core.project_store import ProjectEventStore
from power_framework.core.semantic_models import (
    ASSUMPTION_ID_COMPILED,
    DECISION_REF_ID_COMPILED,
    DEPENDENCY_ID_COMPILED,
    ENTITY_TYPE_TO_MODEL,
    ISSUE_ID_COMPILED,
    LESSON_ID_COMPILED,
    OBSERVATION_ID_COMPILED,
    RISK_ID_COMPILED,
    Assumption,
    ContradictionKind,
    ContradictionProposal,
    DecisionReference,
    Dependency,
    Fact,
    Hypothesis,
    Issue,
    Lesson,
    Observation,
    Provenance,
    Risk,
    SemanticEntityCandidate,
    SemanticEntityType,
    VerificationStatus,
    generate_deterministic_entity_id,
)

logger = logging.getLogger(__name__)

# Prompt injection signatures to detect and quarantine
PROMPT_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?(previous\s+)?instructions", re.IGNORECASE),
    re.compile(r"system\s*:\s*(grant|override|set|delete|allow|escalate)", re.IGNORECASE),
    re.compile(r"set\s+verification_status\s*=\s*['\"]?verified['\"]?", re.IGNORECASE),
    re.compile(r"mark\s+(all\s+)?(as\s+)?verified", re.IGNORECASE),
    re.compile(r"grant\s+(root|admin|superuser)\s+access", re.IGNORECASE),
    re.compile(r"bypass\s+(verification|policy|security|gate)", re.IGNORECASE),
    re.compile(r"drop\s+table\s+", re.IGNORECASE),
    re.compile(r"<script[\s>]", re.IGNORECASE),
    re.compile(r"rm\s+-rf\s+", re.IGNORECASE),
]

# Secret patterns for scrubbing in text
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("github_pat", re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,255}")),
    ("generic_bearer", re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE)),
    ("aws_key", re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}")),
    ("private_key", re.compile(r"-----BEGIN\s+[A-Z\s]+PRIVATE\s+KEY-----")),
]


def scrub_secrets(text: str) -> tuple[str, list[str]]:
    """Detect and scrub credentials from text before storing in semantic entities."""
    scrubbed = text
    detected: list[str] = []
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(scrubbed):
            detected.append(name)
            scrubbed = pattern.sub(f"[REDACTED_{name.upper()}]", scrubbed)
    return scrubbed, detected


def detect_prompt_injection(text: str) -> bool:
    """Detect prompt injection patterns aiming to hijack instructions or escalate privilege."""
    return any(pattern.search(text) is not None for pattern in PROMPT_INJECTION_PATTERNS)


@runtime_checkable
class ExtractionProviderProtocol(Protocol):
    """Abstract model provider protocol for extracting candidate entities from unstructured text."""

    def extract_unstructured(
        self,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Extract typed candidate entities from passive unstructured text."""
        pass


class EventSemanticDisposition(StrEnum):
    """Deterministic classification of all 44 canonical project event types (Phase 3)."""

    A_SEMANTIC_ENTITY = "A_semantic_entity"
    B_RELATIONSHIP_PROPOSAL = "B_relationship_proposal"
    C_LIFECYCLE_METADATA_NOOP = "C_lifecycle_metadata_noop"
    D_EXPLICITLY_REJECTED = "D_explicitly_rejected"


PROJECT_EVENT_DISPATCH_REGISTRY: dict[str, EventSemanticDisposition] = {
    # Category A: Semantic entity producer (RAID, Decision, Fact, Observation, Lesson)
    "risk.opened": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "risk.updated": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "risk.closed": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "assumption.created": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "assumption.updated": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "assumption.invalidated": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "assumption.confirmed": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "issue.opened": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "issue.updated": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "issue.resolved": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "issue.closed": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "dependency.created": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "dependency.updated": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "dependency.resolved": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "decision.association.requested": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "decision.associated": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "decision.disassociated": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "decision.association.failed": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "decision.lifecycle.observed": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "observation.recorded": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    "lesson.recorded": EventSemanticDisposition.A_SEMANTIC_ENTITY,
    # Category B: Semantic relationship/proposal producer (association sagas, supersession)
    "task.association.requested": EventSemanticDisposition.B_RELATIONSHIP_PROPOSAL,
    "task.associated": EventSemanticDisposition.B_RELATIONSHIP_PROPOSAL,
    "task.disassociated": EventSemanticDisposition.B_RELATIONSHIP_PROPOSAL,
    "task.association.failed": EventSemanticDisposition.B_RELATIONSHIP_PROPOSAL,
    "task.lifecycle.observed": EventSemanticDisposition.B_RELATIONSHIP_PROPOSAL,
    # Category C: Deterministic metadata / lifecycle / no-op for Phase 3
    "project.created": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "project.updated": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "project.renamed": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "project.relocated": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "project.phase.proposed": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "project.phase.changed": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "project.archived": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "project.reopened": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "session.started": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "session.ended": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "raci.assigned": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "raci.revoked": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "dor.evaluated": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "dod.evaluated": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "gate.overridden": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "artifact.created": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "artifact.updated": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
    "evidence.attached": EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP,
}

# Invariant: The dispatch registry must cover all 44 canonical project event types
assert set(PROJECT_EVENT_DISPATCH_REGISTRY.keys()) == PROJECT_EVENT_TYPES, (
    "PROJECT_EVENT_DISPATCH_REGISTRY must contain exactly all 44 PROJECT_EVENT_TYPES"
)


class VerifiedEventBatch(BaseModel):
    """Legacy event container; the authority marker is informational only."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    events: list[ProjectEvent] = Field(default_factory=list)
    is_authoritative: bool = False


class CompilationResult(BaseModel):
    """Comprehensive outcome of a Semantic Compiler compilation run."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    candidates: list[SemanticEntityCandidate] = Field(default_factory=list)
    contradiction_proposals: list[ContradictionProposal] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    compiled_event_count: int = 0
    duplicate_count: int = 0
    prompt_injection_detected_count: int = 0
    metrics: dict[str, Any] = Field(default_factory=dict)


class SemanticCompiler:
    """POWER Project State Engine Semantic Compiler (Phase 3).

    Deterministic-first compiler converting canonical events and unstructured observations
    into typed, provenance-bound, validated semantic entities and proposals.
    """

    def __init__(
        self,
        model_provider: ExtractionProviderProtocol | None = None,
        default_project_id: str | None = None,
    ) -> None:
        self.model_provider = model_provider
        self.default_project_id = default_project_id

    def compile_events(
        self,
        events: Sequence[ProjectEvent | dict[str, Any]] | VerifiedReplayBatch,
        existing_candidates: Sequence[SemanticEntityCandidate] | None = None,
        as_of: str | None = None,
        replay_receipt: TrustedReplayReceipt | None = None,
        vault_root: Path | None = None,
    ) -> CompilationResult:
        """Execute the full compiler pipeline over a batch of canonical project events.

        P0 Authority Boundary (Integrity != Authority):
        A cryptographically self-consistent event stream is not automatically an
        authoritative POWER ledger event.
        Structured semantic verification requires an explicit trusted replay/ledger boundary.
        """
        receipt: TrustedReplayReceipt | None
        event_list: Sequence[ProjectEvent | dict[str, Any]]
        if isinstance(events, VerifiedReplayBatch):
            receipt = events.receipt
            event_list = events.events
        else:
            receipt = replay_receipt
            event_list = events

        # Snapshot caller-owned sequences and mutable payloads before authority
        # verification. The exact snapshot checked against the ledger must also
        # be the snapshot compiled below.
        event_list = tuple(
            event.model_copy(deep=True) if isinstance(event, ProjectEvent) else deepcopy(event)
            for event in event_list
        )

        if not event_list:
            return CompilationResult(
                project_id=self.default_project_id or "prj_default",
                candidates=[],
                compiled_event_count=0,
            )

        # Determine project_id from first event
        first_evt = event_list[0]
        project_id = (
            first_evt.project_id
            if isinstance(first_evt, ProjectEvent)
            else first_evt.get("project_id", self.default_project_id or "prj_default")
        )
        validate_project_id(project_id)

        # P0 Authority Boundary Check.  Receipt fields are audit metadata only;
        # authority is granted solely after exact canonical ledger membership
        # verification under an explicit vault root.
        is_ledger_authorized = self._canonical_replay_matches(
            event_list=event_list,
            project_id=project_id,
            receipt=receipt,
            vault_root=vault_root,
        )

        # Deterministic timestamp anchor (G3.4)
        if as_of is None:
            last_evt = event_list[-1]
            as_of = (
                last_evt.timestamp
                if isinstance(last_evt, ProjectEvent)
                else last_evt.get("timestamp", "1970-01-01T00:00:00Z")
            )

        all_candidates: list[SemanticEntityCandidate] = []
        contradiction_proposals: list[ContradictionProposal] = []
        errors: list[str] = []
        prompt_injection_count = 0
        prev_event_dict: dict[str, Any] | None = None

        # Step 1 & 2: Normalize and parse structured events deterministically
        for evt in event_list:
            event_dict = evt.model_dump() if isinstance(evt, ProjectEvent) else dict(evt)
            event_id = event_dict.get("event_id", "")
            if not event_id:
                errors.append(f"Event missing event_id: {event_dict}")
                continue

            # P0: Trust Boundary Validation
            # 1. Reject mixed project_id across single batch
            evt_proj = event_dict.get("project_id")
            if evt_proj != project_id:
                errors.append(
                    f"Untrusted batch: mixed project_id '{evt_proj}' != '{project_id}' for event {event_id}"
                )
                continue

            # 2. Cryptographic ProjectEvent schema compliance
            try:
                if not isinstance(evt, ProjectEvent):
                    ProjectEvent.model_validate(event_dict)
            except Exception as exc:
                errors.append(f"Event {event_id} failed ProjectEvent schema validation: {exc}")
                continue

            # 3. Cryptographic envelope & payload digests
            if event_dict.get("schema_version") != "power.project-event.v1":
                errors.append(
                    f"Untrusted event {event_id}: schema_version must be 'power.project-event.v1'"
                )
                continue

            calc_payload_digest = compute_payload_digest(event_dict.get("payload", {}))
            if event_dict.get("payload_digest") != calc_payload_digest:
                errors.append(
                    f"Untrusted event {event_id}: payload_digest mismatch ({event_dict.get('payload_digest')} != {calc_payload_digest})"
                )
                continue

            calc_event_hash = compute_event_hash(event_dict)
            if event_dict.get("event_hash") != calc_event_hash:
                errors.append(
                    f"Untrusted event {event_id}: event_hash mismatch ({event_dict.get('event_hash')} != {calc_event_hash})"
                )
                continue

            # 4. Batch sequence monotonicity and hash chain continuity
            if prev_event_dict is not None:
                current_seq = event_dict.get("sequence", 0)
                prev_seq = prev_event_dict.get("sequence", 0)
                if current_seq <= prev_seq:
                    errors.append(
                        f"Untrusted batch: non-monotonic sequence ({prev_seq} -> {current_seq}) for event {event_id}"
                    )
                    continue
                if current_seq != prev_seq + 1:
                    errors.append(
                        f"Untrusted batch: sequence gap ({prev_seq} -> {current_seq}) for event {event_id}"
                    )
                    continue
                if event_dict.get("prev_event_hash") != prev_event_dict.get("event_hash"):
                    errors.append(
                        f"Untrusted batch: broken prev_event_hash chain ({event_dict.get('prev_event_hash')} != {prev_event_dict.get('event_hash')}) for event {event_id}"
                    )
                    continue

            prev_event_dict = event_dict

            # 5. Dispatch classification against the 44-event taxonomy (G3.1)
            event_type = event_dict.get("event_type", "")
            disposition = PROJECT_EVENT_DISPATCH_REGISTRY.get(event_type)
            if disposition is None or disposition == EventSemanticDisposition.D_EXPLICITLY_REJECTED:
                errors.append(
                    f"Event {event_id}: unrecognized or rejected event_type '{event_type}'"
                )
                continue

            if disposition == EventSemanticDisposition.C_LIFECYCLE_METADATA_NOOP:
                # Deterministic lifecycle/metadata no-op for Phase 3 semantic extraction
                continue

            if disposition == EventSemanticDisposition.B_RELATIONSHIP_PROPOSAL:
                # Deterministic relationship / saga handling
                continue

            try:
                # 1. Deterministic Normalization
                normalized_evt = self._normalize_event(event_dict)

                # 2. Structured Parser (Deterministic-First, no LLM, G3.1)
                structured_candidates, inj_in_struct = self._parse_structured_event(
                    normalized_evt, is_ledger_authorized=is_ledger_authorized
                )
                if inj_in_struct:
                    prompt_injection_count += 1
                all_candidates.extend(structured_candidates)

                # 3. Optional Unstructured Extraction if event contains unstructured text and provider is configured
                if self.model_provider is not None and self._has_unstructured_content(
                    normalized_evt
                ):
                    unstructured_candidates, inj_detected = self._extract_from_event_unstructured(
                        normalized_evt, as_of=as_of
                    )
                    if inj_detected:
                        prompt_injection_count += 1
                    all_candidates.extend(unstructured_candidates)

            except Exception as e:
                logger.exception("Failed to compile event %s: %s", event_id, e)
                errors.append(f"Event {event_id}: {type(e).__name__}: {e!s}")

        # Step 4: Deduplication & Idempotent ID generation (G3.4)
        existing_for_merge = list(existing_candidates or [])
        if not is_ledger_authorized:
            existing_for_merge = [
                self._downgrade_untrusted_existing_candidate(candidate)
                for candidate in existing_for_merge
            ]
        deduped_candidates, duplicate_count = self._deduplicate_candidates(
            all_candidates, existing_for_merge
        )

        # Step 5: Contradiction and Supersession Detection (G3.5)
        detected_proposals = self._detect_contradictions_and_supersessions(
            new_candidates=deduped_candidates,
            existing_candidates=existing_candidates or [],
            as_of=as_of,
        )
        contradiction_proposals.extend(detected_proposals)

        # Step 6: Validation against schemas
        valid_candidates, validation_errors = self._validate_candidates(deduped_candidates)
        errors.extend(validation_errors)

        duplicate_rate = duplicate_count / len(all_candidates) if all_candidates else 0.0

        return CompilationResult(
            project_id=project_id,
            candidates=valid_candidates,
            contradiction_proposals=contradiction_proposals,
            errors=errors,
            compiled_event_count=len(event_list),
            duplicate_count=duplicate_count,
            prompt_injection_detected_count=prompt_injection_count,
            metrics={
                "raw_candidate_count": len(all_candidates),
                "deduped_candidate_count": len(valid_candidates),
                "duplicate_rate": round(duplicate_rate, 4),
                "contradiction_proposal_count": len(contradiction_proposals),
                "error_count": len(errors),
                "ledger_authorized": is_ledger_authorized,
            },
        )

    def compile_event(
        self,
        event: ProjectEvent | dict[str, Any],
        existing_candidates: Sequence[SemanticEntityCandidate] | None = None,
        as_of: str | None = None,
        replay_receipt: TrustedReplayReceipt | None = None,
        vault_root: Path | None = None,
    ) -> CompilationResult:
        """Compile a single project event."""
        return self.compile_events(
            [event],
            existing_candidates=existing_candidates,
            as_of=as_of,
            replay_receipt=replay_receipt,
            vault_root=vault_root,
        )

    def compile_ledger_replay(
        self,
        vault_root: Path,
        project_id: str,
        from_sequence: int = 1,
        as_of: str | None = None,
    ) -> CompilationResult:
        """Compile events read and verified directly from the authoritative Phase-2 project ledger."""
        batch = replay_project_verified(vault_root, project_id, from_sequence=from_sequence)
        return self.compile_events(batch, as_of=as_of, vault_root=vault_root)

    def compile_verified_batch(
        self,
        batch: VerifiedReplayBatch,
        existing_candidates: Sequence[SemanticEntityCandidate] | None = None,
        as_of: str | None = None,
        *,
        vault_root: Path,
    ) -> CompilationResult:
        """Compile a batch after independently checking canonical ledger membership.

        ``vault_root`` is mandatory because a caller-created replay batch is not an
        authority capability.  The supplied receipt path and metadata are checked
        only as consistency evidence after the canonical store is re-read.
        """
        return self.compile_events(
            batch,
            existing_candidates=existing_candidates,
            as_of=as_of,
            vault_root=vault_root,
        )

    def _canonical_replay_matches(
        self,
        event_list: Sequence[ProjectEvent | dict[str, Any]],
        project_id: str,
        receipt: TrustedReplayReceipt | None,
        vault_root: Path | None,
    ) -> bool:
        """Return true only for an exact replay of the canonical project ledger.

        A ``TrustedReplayReceipt`` is caller-constructible evidence, so its boolean,
        path, range, and hashes never grant authority by themselves.  The canonical
        store is derived from ``project_id`` and ``vault_root``; its verified replay
        must match every supplied event in order, not only the batch endpoints.
        """
        if receipt is None or vault_root is None or receipt.verified is not True:
            return False

        try:
            supplied_events = [
                event if isinstance(event, ProjectEvent) else ProjectEvent.model_validate(event)
                for event in event_list
            ]
            if not supplied_events or receipt.project_id != project_id:
                return False
            if any(event.project_id != project_id for event in supplied_events):
                return False
            if receipt.event_count != len(supplied_events):
                return False
            if (
                supplied_events[0].sequence != receipt.from_sequence
                or supplied_events[-1].sequence != receipt.to_sequence
                or supplied_events[-1].event_hash != receipt.head_event_hash
            ):
                return False

            store = ProjectEventStore(project_id, vault_root)
            expected_ledger_path = store.active_events_file.resolve()
            supplied_ledger_path = Path(receipt.ledger_path).expanduser().resolve(strict=True)
            if supplied_ledger_path != expected_ledger_path:
                return False

            canonical_batch = store.read_verified_replay(from_sequence=receipt.from_sequence)
            canonical_receipt = canonical_batch.receipt
            if (
                canonical_receipt.project_id != receipt.project_id
                or canonical_receipt.from_sequence != receipt.from_sequence
                or canonical_receipt.to_sequence != receipt.to_sequence
                or canonical_receipt.event_count != receipt.event_count
                or canonical_receipt.head_event_hash != receipt.head_event_hash
                or canonical_receipt.verified is not True
            ):
                return False

            supplied_identity = [event.model_dump() for event in supplied_events]
            canonical_identity = [event.model_dump() for event in canonical_batch.events]
            return supplied_identity == canonical_identity
        except Exception as exc:
            # Fail closed without echoing potentially untrusted paths or payloads.
            logger.debug("Canonical replay authority check failed: %s", type(exc).__name__)
            return False

    @staticmethod
    def _downgrade_untrusted_existing_candidate(
        candidate: SemanticEntityCandidate,
    ) -> SemanticEntityCandidate:
        """Prevent caller-provided prior evidence from promoting an untrusted batch."""
        provenance = dict(candidate.entity.get("provenance", {}))
        if (
            candidate.verification_status != VerificationStatus.VERIFIED
            and provenance.get("verification_status") != "verified"
        ):
            return candidate

        try:
            safe_confidence = min(float(candidate.confidence), 0.5)
        except (TypeError, ValueError):
            safe_confidence = 0.5
        provenance["verification_status"] = "unverified"
        provenance["confidence"] = safe_confidence
        entity = dict(candidate.entity)
        entity["provenance"] = provenance
        return SemanticEntityCandidate(
            entity_type=candidate.entity_type,
            entity_id=candidate.entity_id,
            entity=entity,
            verification_status=VerificationStatus.PROPOSED,
            source=candidate.source,
            confidence=safe_confidence,
            metadata=dict(candidate.metadata),
        )

    def compile_unstructured(
        self,
        project_id: str,
        text: str,
        actor: str = "agent:model",
        source_event_id: str | None = None,
        session_id: str | None = None,
        correlation_id: str | None = None,
        existing_candidates: Sequence[SemanticEntityCandidate] | None = None,
        as_of: str | None = None,
        model_provider: ExtractionProviderProtocol | None = None,
    ) -> CompilationResult:
        """Compile unstructured text (meeting notes, transcripts, documents) via model extraction.

        Strictly enforces G3.2 (cannot bypass verification policy) and G3.6 (prompt injection boundary).
        """
        validate_project_id(project_id)
        normalized_text = text.strip()
        scrubbed_text, secrets_found = scrub_secrets(normalized_text)

        # Prompt injection detection (G3.6)
        injection_detected = detect_prompt_injection(scrubbed_text)

        candidates: list[SemanticEntityCandidate] = []
        errors: list[str] = []
        timestamp = as_of or "1970-01-01T00:00:00Z"
        evt_id = (
            source_event_id
            or f"evt_unstructured_{hashlib.sha256(scrubbed_text.encode()).hexdigest()[:16]}"
        )

        effective_provider = model_provider if model_provider is not None else self.model_provider

        if effective_provider is None:
            # When no model provider is given, unstructured text is safely preserved as an Observation candidate
            obs_id = generate_deterministic_entity_id(
                project_id, SemanticEntityType.OBSERVATION, scrubbed_text
            )
            prov = Provenance(
                source_event_ids=[evt_id],
                primary_source_event_id=evt_id,
                actor=actor,
                timestamp=timestamp,
                source_type="agent_inference",
                correlation_id=correlation_id,
                confidence=0.5 if not injection_detected else 0.0,
                verification_status="quarantined" if injection_detected else "unverified",
            )
            obs = Observation(
                observation_id=obs_id,
                project_id=project_id,
                content=scrubbed_text,
                context="unstructured_text_input",
                observer=actor,
                confidence=0.5 if not injection_detected else 0.0,
                observed_at=timestamp,
                provenance=prov,
                created_at=timestamp,
            )
            candidates.append(
                SemanticEntityCandidate(
                    entity_type=SemanticEntityType.OBSERVATION,
                    entity_id=obs_id,
                    entity=obs.model_dump(exclude_none=True),
                    verification_status=VerificationStatus.PROPOSED,
                    source="model_extraction",
                    confidence=0.5 if not injection_detected else 0.0,
                    metadata={
                        "prompt_injection": injection_detected,
                        "scrubbed_secrets": secrets_found,
                    },
                )
            )
        else:
            try:
                # Wrap text with isolation delimiters to enforce prompt injection boundary (G3.6)
                isolated_context = {
                    "project_id": project_id,
                    "session_id": session_id,
                    "correlation_id": correlation_id,
                    "timestamp": timestamp,
                    "prompt_boundary": "UNTRUSTED_CONTENT_DATA_ONLY",
                }
                raw_extracted = effective_provider.extract_unstructured(
                    text=f"<<<UNTRUSTED_PROJECT_DATA>>>\n{scrubbed_text}\n<<<END_UNTRUSTED_PROJECT_DATA>>>",
                    context=isolated_context,
                )
                for item in raw_extracted:
                    cand = self._convert_extracted_dict_to_candidate(
                        project_id=project_id,
                        extracted=item,
                        source_event_id=evt_id,
                        actor=actor,
                        timestamp=timestamp,
                        correlation_id=correlation_id,
                        injection_detected=injection_detected,
                    )
                    if cand is not None:
                        candidates.append(cand)
            except Exception as e:
                logger.exception("Model extraction failed on unstructured text: %s", e)
                errors.append(f"ModelProvider: {type(e).__name__}: {e!s}")

        # Deduplicate and propose contradictions. Unstructured compilation has
        # no canonical ledger authority, so prior caller-provided candidates must
        # not promote the current model/observation output.
        existing_for_merge = [
            self._downgrade_untrusted_existing_candidate(candidate)
            for candidate in existing_candidates or []
        ]
        deduped, dup_count = self._deduplicate_candidates(candidates, existing_for_merge)
        proposals = self._detect_contradictions_and_supersessions(
            new_candidates=deduped,
            existing_candidates=existing_for_merge,
            as_of=timestamp,
        )
        valid_candidates, val_errors = self._validate_candidates(deduped)
        errors.extend(val_errors)

        return CompilationResult(
            project_id=project_id,
            candidates=valid_candidates,
            contradiction_proposals=proposals,
            errors=errors,
            compiled_event_count=1,
            duplicate_count=dup_count,
            prompt_injection_detected_count=1 if injection_detected else 0,
            metrics={
                "raw_candidate_count": len(candidates),
                "deduped_candidate_count": len(valid_candidates),
                "contradiction_proposal_count": len(proposals),
                "injection_detected": injection_detected,
                "secrets_scrubbed_count": len(secrets_found),
            },
        )

    # -------------------------------------------------------------------------
    # Internal Pipeline Steps
    # -------------------------------------------------------------------------

    def _normalize_event(self, event_dict: dict[str, Any]) -> dict[str, Any]:
        """Normalize event envelope and payload deterministically."""
        normalized = dict(event_dict)
        if "project_id" in normalized:
            normalized["project_id"] = str(normalized["project_id"]).strip()
        if "actor" in normalized:
            normalized["actor"] = str(normalized["actor"]).strip()
        if "timestamp" in normalized:
            normalized["timestamp"] = str(normalized["timestamp"]).strip()
        if "payload" in normalized and isinstance(normalized["payload"], dict):
            clean_payload = {}
            for k, v in normalized["payload"].items():
                if isinstance(v, str):
                    clean_payload[k] = v.strip()
                else:
                    clean_payload[k] = v
            normalized["payload"] = clean_payload
        return normalized

    def _has_unstructured_content(self, event_dict: dict[str, Any]) -> bool:
        """Check if event payload contains raw text suitable for model extraction."""
        event_type = event_dict.get("event_type", "")
        payload = event_dict.get("payload", {})
        if event_type == "observation.recorded":
            return True
        return any(k in payload for k in ("text", "raw_content", "notes", "dialogue", "transcript"))

    def _extract_from_event_unstructured(
        self, event_dict: dict[str, Any], as_of: str | None = None
    ) -> tuple[list[SemanticEntityCandidate], bool]:
        """Extract candidate entities from an event's unstructured text using the model provider."""
        assert self.model_provider is not None
        payload = event_dict.get("payload", {})
        text_content = (
            payload.get("content")
            or payload.get("text")
            or payload.get("raw_content")
            or payload.get("notes")
            or ""
        )
        if not text_content:
            return [], False

        scrubbed_text, _ = scrub_secrets(text_content)
        injection_detected = detect_prompt_injection(scrubbed_text)

        context = {
            "project_id": event_dict.get("project_id"),
            "event_id": event_dict.get("event_id"),
            "event_type": event_dict.get("event_type"),
            "timestamp": event_dict.get("timestamp"),
            "actor": event_dict.get("actor"),
            "prompt_boundary": "UNTRUSTED_CONTENT_DATA_ONLY",
        }

        try:
            raw_items = self.model_provider.extract_unstructured(
                text=f"<<<UNTRUSTED_PROJECT_DATA>>>\n{scrubbed_text}\n<<<END_UNTRUSTED_PROJECT_DATA>>>",
                context=context,
            )
        except Exception as e:
            logger.warning("Model extraction raised exception: %s", e)
            return [], injection_detected

        candidates: list[SemanticEntityCandidate] = []
        for item in raw_items:
            cand = self._convert_extracted_dict_to_candidate(
                project_id=event_dict["project_id"],
                extracted=item,
                source_event_id=event_dict["event_id"],
                actor=event_dict.get("actor", "agent:model"),
                timestamp=event_dict.get("timestamp") or as_of or "1970-01-01T00:00:00Z",
                correlation_id=event_dict.get("correlation_id"),
                injection_detected=injection_detected,
            )
            if cand is not None:
                candidates.append(cand)
        return candidates, injection_detected

    def _convert_extracted_dict_to_candidate(
        self,
        project_id: str,
        extracted: dict[str, Any],
        source_event_id: str,
        actor: str,
        timestamp: str,
        correlation_id: str | None,
        injection_detected: bool,
    ) -> SemanticEntityCandidate | None:
        """Convert a model extraction output dictionary into a validated SemanticEntityCandidate.

        Strictly enforces G3.2: candidate receives VerificationStatus.PROPOSED and provenance
        verification_status='unverified', completely preventing model-driven verification bypass.
        """
        raw_type = str(extracted.get("type") or extracted.get("entity_type") or "").upper()
        if raw_type not in SemanticEntityType.__members__:
            # Map common variations
            type_mapping = {
                "FACT": SemanticEntityType.FACT,
                "DECISION": SemanticEntityType.DECISION,
                "DECISION_REFERENCE": SemanticEntityType.DECISION,
                "ASSUMPTION": SemanticEntityType.ASSUMPTION,
                "HYPOTHESIS": SemanticEntityType.HYPOTHESIS,
                "RISK": SemanticEntityType.RISK,
                "ISSUE": SemanticEntityType.ISSUE,
                "DEPENDENCY": SemanticEntityType.DEPENDENCY,
                "OBSERVATION": SemanticEntityType.OBSERVATION,
                "LESSON": SemanticEntityType.LESSON,
            }
            entity_type = type_mapping.get(raw_type)
            if entity_type is None:
                return None
        else:
            entity_type = SemanticEntityType(raw_type)

        content_str = (
            extracted.get("statement")
            or extracted.get("title")
            or extracted.get("content")
            or extracted.get("summary")
            or extracted.get("decision_id")
            or ""
        )
        if not content_str:
            return None

        # Scrub secrets
        content_str, _ = scrub_secrets(content_str)

        # Generate deterministic entity ID (G3.4) - strictly ignore provider-supplied entity_id (G3.2/G3.4)
        entity_id = generate_deterministic_entity_id(project_id, entity_type, content_str)

        confidence_val = float(extracted.get("confidence", 0.75))
        confidence_val = max(0.0, min(1.0, confidence_val))
        if injection_detected:
            confidence_val = 0.0

        # Provenance: Strictly 'agent_inference' and 'unverified' (G3.2)
        provenance = Provenance(
            source_event_ids=[source_event_id],
            primary_source_event_id=source_event_id,
            actor=actor,
            timestamp=timestamp,
            source_type="agent_inference",
            correlation_id=correlation_id,
            confidence=confidence_val,
            verification_status="quarantined" if injection_detected else "unverified",
        )

        entity_dict: dict[str, Any] = {
            "project_id": project_id,
            "provenance": provenance.model_dump(exclude_none=True),
            "created_at": timestamp,
        }

        # Populate type-specific fields
        if entity_type == SemanticEntityType.FACT:
            entity_dict.update(
                {
                    "fact_id": entity_id,
                    "statement": content_str,
                    "category": extracted.get("category", "technical")
                    if extracted.get("category")
                    in ("domain", "technical", "organizational", "environmental", "historical")
                    else "technical",
                }
            )
        elif entity_type == SemanticEntityType.DECISION:
            decision_id = extracted.get("decision_id") or f"dec_{entity_id[5:]}"
            entity_dict.update(
                {
                    "decision_ref_id": entity_id,
                    "decision_id": decision_id,
                    "relation": extracted.get("relation", "governs"),
                    "status": "proposed",  # Model extraction decisions are always 'proposed'
                    "task_id": extracted.get("task_id"),
                }
            )
        elif entity_type == SemanticEntityType.ASSUMPTION:
            entity_dict.update(
                {
                    "assumption_id": entity_id,
                    "statement": content_str,
                    "rationale": extracted.get("rationale", ""),
                    "confidence": confidence_val,
                    "status": "valid",
                }
            )
        elif entity_type == SemanticEntityType.HYPOTHESIS:
            entity_dict.update(
                {
                    "hypothesis_id": entity_id,
                    "statement": content_str,
                    "rationale": extracted.get("rationale", ""),
                    "validation_criteria": extracted.get("validation_criteria", ""),
                    "confidence": confidence_val,
                    "status": "proposed",
                }
            )
        elif entity_type == SemanticEntityType.RISK:
            prob = extracted.get("probability", "medium")
            if prob not in ("low", "medium", "high"):
                prob = "medium"
            imp = extracted.get("impact", "medium")
            if imp not in ("low", "medium", "high", "critical"):
                imp = "medium"
            entity_dict.update(
                {
                    "risk_id": entity_id,
                    "title": content_str,
                    "description": extracted.get("description", ""),
                    "probability": prob,
                    "impact": imp,
                    "owner": extracted.get("owner", actor),
                    "status": "identified",
                    "mitigation_plan": extracted.get("mitigation_plan", ""),
                    "updated_at": timestamp,
                }
            )
        elif entity_type == SemanticEntityType.ISSUE:
            sev = extracted.get("severity", "major")
            if sev not in ("minor", "major", "critical", "blocker"):
                sev = "major"
            entity_dict.update(
                {
                    "issue_id": entity_id,
                    "title": content_str,
                    "description": extracted.get("description", ""),
                    "severity": sev,
                    "status": "open",
                    "blocking_task_ids": extracted.get("blocking_task_ids", []),
                }
            )
        elif entity_type == SemanticEntityType.DEPENDENCY:
            entity_dict.update(
                {
                    "dependency_id": entity_id,
                    "source_id": extracted.get("source_id", project_id),
                    "target_id": extracted.get("target_id", "external_component"),
                    "target_type": extracted.get("target_type", "task")
                    if extracted.get("target_type")
                    in ("task", "decision", "artifact", "project", "external")
                    else "external",
                    "dependency_kind": extracted.get("dependency_kind", "requires")
                    if extracted.get("dependency_kind")
                    in ("blocks", "blocked_by", "relates_to", "requires")
                    else "requires",
                    "status": "pending",
                }
            )
        elif entity_type == SemanticEntityType.OBSERVATION:
            entity_dict.update(
                {
                    "observation_id": entity_id,
                    "content": content_str,
                    "context": extracted.get("context", "model_extraction"),
                    "observer": actor,
                    "confidence": confidence_val,
                    "observed_at": timestamp,
                }
            )
        elif entity_type == SemanticEntityType.LESSON:
            cat = extracted.get("category", "process")
            if cat not in (
                "process",
                "technical",
                "architecture",
                "coordination",
                "quality",
                "security",
            ):
                cat = "process"
            entity_dict.update(
                {
                    "lesson_id": entity_id,
                    "title": extracted.get("title", content_str[:128]),
                    "summary": content_str,
                    "category": cat,
                    "recommendation": extracted.get("recommendation", content_str),
                }
            )

        # Validate with Pydantic model
        model_cls = ENTITY_TYPE_TO_MODEL[entity_type]
        try:
            validated_model = model_cls.model_validate(entity_dict)
            clean_dict = validated_model.model_dump(exclude_none=True)
        except Exception as e:
            logger.debug("Failed validation for model-extracted entity %s: %s", entity_id, e)
            return None

        # Return candidate forced unconditionally to PROPOSED (G3.2)
        return SemanticEntityCandidate(
            entity_type=entity_type,
            entity_id=entity_id,
            entity=clean_dict,
            verification_status=VerificationStatus.PROPOSED,
            source="model_extraction",
            confidence=confidence_val,
            metadata={"prompt_injection": injection_detected},
        )

    def _parse_structured_event(
        self, event_dict: dict[str, Any], is_ledger_authorized: bool = False
    ) -> tuple[list[SemanticEntityCandidate], bool]:
        """Deterministic structured parser for canonical project events (G3.1: Zero LLM)."""
        event_type = event_dict.get("event_type", "")
        project_id = event_dict["project_id"]
        event_id = event_dict["event_id"]
        actor = event_dict["actor"]
        timestamp = event_dict["timestamp"]
        correlation_id = event_dict.get("correlation_id")
        evidence_refs = event_dict.get("evidence_refs", [])
        payload = event_dict.get("payload", {})

        # P0 Authority Boundary (Integrity != Authority):
        # Only explicitly verified ledger replay batches produce authoritative VERIFIED entities.
        cand_status = (
            VerificationStatus.VERIFIED if is_ledger_authorized else VerificationStatus.PROPOSED
        )
        prov_status: Literal["verified", "unverified"] = (
            "verified" if is_ledger_authorized else "unverified"
        )
        source_type: Literal["direct_mutation", "event_replay"] = (
            "direct_mutation" if event_dict.get("source") == "cli" else "event_replay"
        )
        confidence = 1.0 if is_ledger_authorized else 0.5

        # Default provenance for deterministic structured events
        provenance = Provenance(
            source_event_ids=[event_id],
            primary_source_event_id=event_id,
            actor=actor,
            timestamp=timestamp,
            source_type=source_type,
            correlation_id=correlation_id,
            evidence_refs=evidence_refs,
            confidence=confidence,
            verification_status=prov_status,
        )

        candidates: list[SemanticEntityCandidate] = []
        injection_detected = False

        # 1. RAID: Risk
        if event_type in ("risk.opened", "risk.updated", "risk.closed"):
            title = payload.get("title")
            if not title or not isinstance(title, str) or not title.strip():
                raise ValueError(
                    f"Event {event_id} ({event_type}) missing required non-empty 'title'"
                )

            prob = payload.get("probability")
            if prob not in ("low", "medium", "high"):
                raise ValueError(
                    f"Event {event_id} ({event_type}) missing or invalid 'probability' (expected low/medium/high, got {prob!r})"
                )

            imp = payload.get("impact")
            if imp not in ("low", "medium", "high", "critical"):
                raise ValueError(
                    f"Event {event_id} ({event_type}) missing or invalid 'impact' (expected low/medium/high/critical, got {imp!r})"
                )

            risk_id = payload.get("risk_id")
            if not risk_id or not RISK_ID_COMPILED.match(risk_id):
                risk_id = generate_deterministic_entity_id(
                    project_id, SemanticEntityType.RISK, title
                )

            status_map = {
                "risk.opened": "identified",
                "risk.updated": payload.get("status", "identified"),
                "risk.closed": "retired",
            }
            status = status_map[event_type]
            if status not in ("identified", "mitigated", "materialized", "retired"):
                status = "identified"

            risk = Risk(
                risk_id=risk_id,
                project_id=project_id,
                title=title,
                description=payload.get("description", ""),
                probability=prob,
                impact=imp,
                mitigation_plan=payload.get("mitigation_plan", ""),
                owner=payload.get("owner", actor),
                status=status,
                related_task_ids=payload.get("related_task_ids", []),
                provenance=provenance,
                created_at=timestamp,
                updated_at=timestamp,
            )
            candidates.append(
                SemanticEntityCandidate(
                    entity_type=SemanticEntityType.RISK,
                    entity_id=risk_id,
                    entity=risk.model_dump(exclude_none=True),
                    verification_status=cand_status,
                    source="structured_event",
                    confidence=confidence,
                )
            )

        # 2. RAID: Assumption
        elif event_type in (
            "assumption.created",
            "assumption.updated",
            "assumption.invalidated",
            "assumption.confirmed",
        ):
            statement = payload.get("statement")
            if not statement or not isinstance(statement, str) or not statement.strip():
                raise ValueError(
                    f"Event {event_id} ({event_type}) missing required non-empty 'statement'"
                )

            asm_id = payload.get("assumption_id")
            if not asm_id or not ASSUMPTION_ID_COMPILED.match(asm_id):
                asm_id = generate_deterministic_entity_id(
                    project_id, SemanticEntityType.ASSUMPTION, statement
                )

            status_map = {
                "assumption.created": "valid",
                "assumption.updated": payload.get("status", "valid"),
                "assumption.invalidated": "invalidated",
                "assumption.confirmed": "confirmed",
            }
            status = status_map[event_type]
            if status not in ("valid", "invalidated", "confirmed"):
                status = "valid"

            invalidated_by = payload.get("invalidated_by")
            if event_type == "assumption.invalidated" and not invalidated_by:
                invalidated_by = actor

            asm = Assumption(
                assumption_id=asm_id,
                project_id=project_id,
                statement=statement,
                rationale=payload.get("rationale", ""),
                confidence=float(payload.get("confidence", 0.9)),
                status=status,
                validated_at=payload.get("validated_at"),
                invalidated_by=invalidated_by,
                provenance=provenance,
                created_at=timestamp,
            )
            candidates.append(
                SemanticEntityCandidate(
                    entity_type=SemanticEntityType.ASSUMPTION,
                    entity_id=asm_id,
                    entity=asm.model_dump(exclude_none=True),
                    verification_status=cand_status
                    if status != "invalidated"
                    else VerificationStatus.INVALIDATED,
                    source="structured_event",
                    confidence=confidence,
                )
            )

        # 3. RAID: Issue
        elif event_type in ("issue.opened", "issue.updated", "issue.resolved", "issue.closed"):
            title = payload.get("title")
            if not title or not isinstance(title, str) or not title.strip():
                raise ValueError(
                    f"Event {event_id} ({event_type}) missing required non-empty 'title'"
                )

            sev = payload.get("severity")
            if sev not in ("minor", "major", "critical", "blocker"):
                raise ValueError(
                    f"Event {event_id} ({event_type}) missing or invalid 'severity' (expected minor/major/critical/blocker, got {sev!r})"
                )

            issue_id = payload.get("issue_id")
            if not issue_id or not ISSUE_ID_COMPILED.match(issue_id):
                issue_id = generate_deterministic_entity_id(
                    project_id, SemanticEntityType.ISSUE, title
                )

            status_map = {
                "issue.opened": "open",
                "issue.updated": payload.get("status", "open"),
                "issue.resolved": "resolved",
                "issue.closed": "closed",
            }
            status = status_map[event_type]
            if status not in ("open", "investigating", "resolved", "closed"):
                status = "open"

            issue = Issue(
                issue_id=issue_id,
                project_id=project_id,
                title=title,
                description=payload.get("description", ""),
                severity=sev,
                status=status,
                blocking_task_ids=payload.get("blocking_task_ids", []),
                resolution=payload.get("resolution"),
                provenance=provenance,
                created_at=timestamp,
                resolved_at=payload.get("resolved_at")
                if status in ("resolved", "closed")
                else None,
            )
            candidates.append(
                SemanticEntityCandidate(
                    entity_type=SemanticEntityType.ISSUE,
                    entity_id=issue_id,
                    entity=issue.model_dump(exclude_none=True),
                    verification_status=cand_status,
                    source="structured_event",
                    confidence=confidence,
                )
            )

        # 4. RAID: Dependency
        elif event_type in ("dependency.created", "dependency.updated", "dependency.resolved"):
            source_id = payload.get("source_id") or payload.get("source")
            if not source_id or not isinstance(source_id, str) or not source_id.strip():
                raise ValueError(f"Event {event_id} ({event_type}) missing required 'source_id'")

            target_id = payload.get("target_id") or payload.get("target")
            if not target_id or not isinstance(target_id, str) or not target_id.strip():
                raise ValueError(f"Event {event_id} ({event_type}) missing required 'target_id'")

            dep_kind = payload.get("dependency_kind")
            if dep_kind not in ("blocks", "blocked_by", "relates_to", "requires"):
                raise ValueError(
                    f"Event {event_id} ({event_type}) missing or invalid 'dependency_kind' (expected blocks/blocked_by/relates_to/requires, got {dep_kind!r})"
                )

            dep_id = payload.get("dependency_id")
            if not dep_id or not DEPENDENCY_ID_COMPILED.match(dep_id):
                dep_id = generate_deterministic_entity_id(
                    project_id, SemanticEntityType.DEPENDENCY, f"{source_id}:{target_id}:{dep_kind}"
                )

            status = (
                "satisfied"
                if event_type == "dependency.resolved"
                else payload.get("status", "pending")
            )
            if status not in ("pending", "satisfied", "broken"):
                status = "pending"

            target_type = payload.get("target_type", "task")
            if target_type not in ("task", "decision", "artifact", "project", "external"):
                target_type = "task"

            dep = Dependency(
                dependency_id=dep_id,
                project_id=project_id,
                source_id=source_id,
                target_id=target_id,
                target_type=target_type,
                dependency_kind=dep_kind,
                status=status,
                external_ref=payload.get("external_ref"),
                provenance=provenance,
                created_at=timestamp,
            )
            candidates.append(
                SemanticEntityCandidate(
                    entity_type=SemanticEntityType.DEPENDENCY,
                    entity_id=dep_id,
                    entity=dep.model_dump(exclude_none=True),
                    verification_status=cand_status,
                    source="structured_event",
                    confidence=confidence,
                )
            )

        # 5. DecisionReference
        elif event_type in (
            "decision.associated",
            "decision.association.requested",
            "decision.disassociated",
            "decision.association.failed",
            "decision.lifecycle.observed",
        ):
            decision_id = payload.get("decision_id")
            if not decision_id or not isinstance(decision_id, str) or not decision_id.strip():
                raise ValueError(f"Event {event_id} ({event_type}) missing required 'decision_id'")

            relation = payload.get("relation", "governs")
            dref_id = payload.get("decision_ref_id")
            if not dref_id or not DECISION_REF_ID_COMPILED.match(dref_id):
                dref_id = generate_deterministic_entity_id(
                    project_id, SemanticEntityType.DECISION, decision_id
                )

            status_map = {
                "decision.associated": "accepted",
                "decision.association.requested": "proposed",
                "decision.disassociated": "rejected",
                "decision.association.failed": "rejected",
                "decision.lifecycle.observed": payload.get("status", "accepted"),
            }
            dec_status = status_map[event_type]
            if dec_status not in ("proposed", "pending", "accepted", "rejected", "superseded"):
                dec_status = "accepted"

            # Check if payload indicates superseding an older decision
            supersedes_ref = payload.get("supersedes")
            if supersedes_ref:
                provenance.supersedes = supersedes_ref

            dref = DecisionReference(
                decision_ref_id=dref_id,
                project_id=project_id,
                decision_id=decision_id,
                relation=relation,
                status=dec_status,
                task_id=payload.get("task_id"),
                receipt_ref=payload.get("receipt_ref"),
                provenance=provenance,
                created_at=timestamp,
                updated_at=timestamp,
            )
            candidates.append(
                SemanticEntityCandidate(
                    entity_type=SemanticEntityType.DECISION,
                    entity_id=dref_id,
                    entity=dref.model_dump(exclude_none=True),
                    verification_status=cand_status
                    if dec_status == "accepted"
                    else (
                        VerificationStatus.REJECTED
                        if dec_status == "rejected"
                        else VerificationStatus.PROPOSED
                    ),
                    source="structured_event",
                    confidence=confidence,
                )
            )

        # 6. Observation, Fact, or Hypothesis (observation.recorded)
        elif event_type == "observation.recorded":
            target_entity_type = str(payload.get("entity_type", "OBSERVATION")).upper()
            if target_entity_type == "FACT":
                stmt = payload.get("statement") or payload.get("content")
                if not stmt or not isinstance(stmt, str) or not stmt.strip():
                    raise ValueError(
                        f"Event {event_id} fact missing required non-empty 'statement'"
                    )

                fct_id = payload.get("fact_id") or generate_deterministic_entity_id(
                    project_id, SemanticEntityType.FACT, stmt
                )
                cat = payload.get("category", "technical")
                if cat not in (
                    "domain",
                    "technical",
                    "organizational",
                    "environmental",
                    "historical",
                ):
                    cat = "technical"
                fact = Fact(
                    fact_id=fct_id,
                    project_id=project_id,
                    statement=stmt,
                    category=cat,
                    verified_at=payload.get("verified_at", timestamp),
                    verification_method=payload.get("verification_method", "canonical_event"),
                    provenance=provenance,
                    created_at=timestamp,
                )
                candidates.append(
                    SemanticEntityCandidate(
                        entity_type=SemanticEntityType.FACT,
                        entity_id=fct_id,
                        entity=fact.model_dump(exclude_none=True),
                        verification_status=cand_status,
                        source="structured_event",
                        confidence=confidence,
                    )
                )
            elif target_entity_type == "HYPOTHESIS":
                stmt = payload.get("statement") or payload.get("content")
                if not stmt or not isinstance(stmt, str) or not stmt.strip():
                    raise ValueError(
                        f"Event {event_id} hypothesis missing required non-empty 'statement'"
                    )

                hyp_id = payload.get("hypothesis_id") or generate_deterministic_entity_id(
                    project_id, SemanticEntityType.HYPOTHESIS, stmt
                )
                hypothesis = Hypothesis(
                    hypothesis_id=hyp_id,
                    project_id=project_id,
                    statement=stmt,
                    rationale=payload.get("rationale", ""),
                    validation_criteria=payload.get("validation_criteria", ""),
                    confidence=float(payload.get("confidence", 0.8)),
                    status=payload.get("status", "proposed"),
                    provenance=provenance,
                    created_at=timestamp,
                )
                candidates.append(
                    SemanticEntityCandidate(
                        entity_type=SemanticEntityType.HYPOTHESIS,
                        entity_id=hyp_id,
                        entity=hypothesis.model_dump(exclude_none=True),
                        verification_status=VerificationStatus.PROPOSED,
                        source="structured_event",
                        confidence=float(payload.get("confidence", 0.8)),
                    )
                )
            else:
                content = payload.get("content")
                if not content or not isinstance(content, str) or not content.strip():
                    raise ValueError(
                        f"Event {event_id} (observation.recorded) missing required non-empty 'content'"
                    )

                obs_id = payload.get("observation_id")
                if not obs_id or not OBSERVATION_ID_COMPILED.match(obs_id):
                    obs_id = generate_deterministic_entity_id(
                        project_id, SemanticEntityType.OBSERVATION, content
                    )

                context_str = str(payload.get("context", ""))
                injection_detected = detect_prompt_injection(content) or detect_prompt_injection(
                    context_str
                )

                if injection_detected:
                    verification_status = VerificationStatus.PROPOSED
                    confidence_val = 0.0
                    obs_prov = provenance.model_copy(
                        update={
                            "verification_status": "quarantined",
                            "confidence": 0.0,
                        }
                    )
                else:
                    verification_status = cand_status
                    confidence_val = (
                        float(payload.get("confidence", 1.0)) if is_ledger_authorized else 0.5
                    )
                    obs_prov = provenance.model_copy(
                        update={
                            "verification_status": prov_status,
                            "confidence": confidence_val,
                        }
                    )

                obs = Observation(
                    observation_id=obs_id,
                    project_id=project_id,
                    content=content,
                    context=context_str,
                    observer=payload.get("observer", actor),
                    confidence=confidence_val,
                    observed_at=payload.get("observed_at", timestamp),
                    provenance=obs_prov,
                    created_at=timestamp,
                )
                candidates.append(
                    SemanticEntityCandidate(
                        entity_type=SemanticEntityType.OBSERVATION,
                        entity_id=obs_id,
                        entity=obs.model_dump(exclude_none=True),
                        verification_status=verification_status,
                        source="structured_event",
                        confidence=confidence_val,
                        metadata={"prompt_injection": injection_detected},
                    )
                )

        # 7. Lesson
        elif event_type == "lesson.recorded":
            title = payload.get("title")
            if not title or not isinstance(title, str) or not title.strip():
                raise ValueError(
                    f"Event {event_id} (lesson.recorded) missing required non-empty 'title'"
                )

            summary = payload.get("summary")
            if not summary or not isinstance(summary, str) or not summary.strip():
                raise ValueError(
                    f"Event {event_id} (lesson.recorded) missing required non-empty 'summary'"
                )

            lsn_id = payload.get("lesson_id")
            if not lsn_id or not LESSON_ID_COMPILED.match(lsn_id):
                lsn_id = generate_deterministic_entity_id(
                    project_id, SemanticEntityType.LESSON, title
                )

            cat = payload.get("category", "process")
            if cat not in (
                "process",
                "technical",
                "architecture",
                "coordination",
                "quality",
                "security",
            ):
                cat = "process"

            lesson = Lesson(
                lesson_id=lsn_id,
                project_id=project_id,
                title=title,
                summary=summary,
                category=cat,
                applies_to=payload.get("applies_to", []),
                recommendation=payload.get("recommendation", summary),
                provenance=provenance,
                created_at=timestamp,
            )
            candidates.append(
                SemanticEntityCandidate(
                    entity_type=SemanticEntityType.LESSON,
                    entity_id=lsn_id,
                    entity=lesson.model_dump(exclude_none=True),
                    verification_status=cand_status,
                    source="structured_event",
                    confidence=confidence,
                )
            )

        # 8. Fact in payload
        elif "statement" in payload and payload.get("entity_type", "").upper() == "FACT":
            stmt = payload.get("statement")
            if not stmt or not isinstance(stmt, str) or not stmt.strip():
                raise ValueError(f"Event {event_id} fact missing required non-empty 'statement'")

            fct_id = payload.get("fact_id") or generate_deterministic_entity_id(
                project_id, SemanticEntityType.FACT, stmt
            )
            cat = payload.get("category", "technical")
            if cat not in ("domain", "technical", "organizational", "environmental", "historical"):
                cat = "technical"
            fact = Fact(
                fact_id=fct_id,
                project_id=project_id,
                statement=stmt,
                category=cat,
                verified_at=payload.get("verified_at", timestamp),
                verification_method=payload.get("verification_method", "canonical_event"),
                provenance=provenance,
                created_at=timestamp,
            )
            candidates.append(
                SemanticEntityCandidate(
                    entity_type=SemanticEntityType.FACT,
                    entity_id=fct_id,
                    entity=fact.model_dump(exclude_none=True),
                    verification_status=cand_status,
                    source="structured_event",
                    confidence=confidence,
                )
            )

        # 9. Hypothesis in payload
        elif "statement" in payload and payload.get("entity_type", "").upper() == "HYPOTHESIS":
            stmt = payload.get("statement")
            if not stmt or not isinstance(stmt, str) or not stmt.strip():
                raise ValueError(
                    f"Event {event_id} hypothesis missing required non-empty 'statement'"
                )

            hyp_id = payload.get("hypothesis_id") or generate_deterministic_entity_id(
                project_id, SemanticEntityType.HYPOTHESIS, stmt
            )
            hypothesis = Hypothesis(
                hypothesis_id=hyp_id,
                project_id=project_id,
                statement=stmt,
                rationale=payload.get("rationale", ""),
                validation_criteria=payload.get("validation_criteria", ""),
                confidence=float(payload.get("confidence", 0.8)),
                status=payload.get("status", "proposed"),
                provenance=provenance,
                created_at=timestamp,
            )
            candidates.append(
                SemanticEntityCandidate(
                    entity_type=SemanticEntityType.HYPOTHESIS,
                    entity_id=hyp_id,
                    entity=hypothesis.model_dump(exclude_none=True),
                    verification_status=VerificationStatus.PROPOSED,
                    source="structured_event",
                    confidence=float(payload.get("confidence", 0.8)),
                )
            )

        return candidates, injection_detected

    def _deduplicate_candidates(
        self,
        new_candidates: Sequence[SemanticEntityCandidate],
        existing_candidates: Sequence[SemanticEntityCandidate],
    ) -> tuple[list[SemanticEntityCandidate], int]:
        """Merge identical candidates deterministically, combining provenance without duplicates (G3.4)."""
        existing_by_id: dict[str, SemanticEntityCandidate] = {
            c.entity_id: c for c in existing_candidates
        }
        merged_by_id: dict[str, SemanticEntityCandidate] = {}
        duplicate_count = 0

        for candidate in new_candidates:
            cid = candidate.entity_id
            if cid in merged_by_id:
                # Merge into existing in current batch
                duplicate_count += 1
                merged_by_id[cid] = self._merge_two_candidates(merged_by_id[cid], candidate)
            elif cid in existing_by_id:
                # Merge into existing from earlier state
                duplicate_count += 1
                # The current event is the source of truth for the current
                # compilation. Prior candidates may be stale or caller-created.
                merged_by_id[cid] = self._merge_two_candidates(candidate, existing_by_id[cid])
            else:
                merged_by_id[cid] = candidate

        return list(merged_by_id.values()), duplicate_count

    def _merge_two_candidates(
        self,
        first: SemanticEntityCandidate,
        second: SemanticEntityCandidate,
    ) -> SemanticEntityCandidate:
        """Merge two candidates with the same ID, ensuring structured fields have absolute priority (G3.4)."""
        # Determine if there is a structured vs model extraction mix
        if first.source == "structured_event" and second.source == "model_extraction":
            structured_cand: SemanticEntityCandidate | None = first
            model_cand: SemanticEntityCandidate | None = second
        elif first.source == "model_extraction" and second.source == "structured_event":
            structured_cand = second
            model_cand = first
        else:
            structured_cand = None
            model_cand = None

        if structured_cand is not None and model_cand is not None:
            # G3.4 / Point 7: Structured entity fields have absolute priority
            # Model arbitrary fields CANNOT overwrite structured fields or become VERIFIED
            merged_dict = dict(structured_cand.entity)
            struct_prov = structured_cand.entity.get("provenance", {})
            model_prov = model_cand.entity.get("provenance", {})

            # Safely merge only provenance source_event_ids and evidence_refs
            combined_events = list(
                dict.fromkeys(
                    struct_prov.get("source_event_ids", []) + model_prov.get("source_event_ids", [])
                )
            )
            combined_evidence = list(
                dict.fromkeys(
                    struct_prov.get("evidence_refs", []) + model_prov.get("evidence_refs", [])
                )
            )
            merged_prov = dict(struct_prov)
            merged_prov["source_event_ids"] = combined_events
            merged_prov["evidence_refs"] = combined_evidence
            merged_dict["provenance"] = merged_prov

            return SemanticEntityCandidate(
                entity_type=structured_cand.entity_type,
                entity_id=structured_cand.entity_id,
                entity=merged_dict,
                verification_status=structured_cand.verification_status,
                source="structured_event",
                confidence=structured_cand.confidence,
                metadata={**model_cand.metadata, **structured_cand.metadata},
            )

        # Same-source deduplication
        merged_dict = dict(first.entity)
        first_prov = first.entity.get("provenance", {})
        second_prov = second.entity.get("provenance", {})

        # Merge source_event_ids uniquely
        combined_events = list(
            dict.fromkeys(
                first_prov.get("source_event_ids", []) + second_prov.get("source_event_ids", [])
            )
        )
        combined_evidence = list(
            dict.fromkeys(
                first_prov.get("evidence_refs", []) + second_prov.get("evidence_refs", [])
            )
        )

        merged_prov = dict(first_prov)
        merged_prov["source_event_ids"] = combined_events
        merged_prov["evidence_refs"] = combined_evidence

        # Preserve supersedes / invalidates links
        if second_prov.get("supersedes"):
            merged_prov["supersedes"] = second_prov["supersedes"]
        if second_prov.get("invalidates"):
            merged_prov["invalidates"] = second_prov["invalidates"]

        merged_dict["provenance"] = merged_prov

        # Verification status priority: verified > rejected > invalidated > superseded > proposed
        status_priority = {
            VerificationStatus.VERIFIED: 5,
            VerificationStatus.REJECTED: 4,
            VerificationStatus.INVALIDATED: 3,
            VerificationStatus.SUPERSEDED: 2,
            VerificationStatus.PROPOSED: 1,
        }
        status_chosen = (
            first.verification_status
            if status_priority.get(first.verification_status, 0)
            >= status_priority.get(second.verification_status, 0)
            else second.verification_status
        )

        # Gate G3.2 rule: If both candidates are model_extraction, it CANNOT be VERIFIED!
        if first.source == "model_extraction" and second.source == "model_extraction":
            status_chosen = VerificationStatus.PROPOSED

        return SemanticEntityCandidate(
            entity_type=first.entity_type,
            entity_id=first.entity_id,
            entity=merged_dict,
            verification_status=status_chosen,
            source=first.source,
            confidence=max(first.confidence, second.confidence),
            metadata={**first.metadata, **second.metadata},
        )

    def _detect_contradictions_and_supersessions(
        self,
        new_candidates: Sequence[SemanticEntityCandidate],
        existing_candidates: Sequence[SemanticEntityCandidate],
        as_of: str = "1970-01-01T00:00:00Z",
    ) -> list[ContradictionProposal]:
        """Distinguish the 5 contradiction/supersession categories required by Phase 3 (G3.5).

        1. conflicting_observation
        2. explicit_correction
        3. superseding_decision
        4. stale_fact
        5. unresolved_contradiction

        Never deletes the old record; produces structured proposals linking them.
        """
        proposals: list[ContradictionProposal] = []
        all_candidates = list(existing_candidates) + list(new_candidates)
        now_iso = as_of

        for new_cand in new_candidates:
            new_ent = new_cand.entity
            new_prov = new_ent.get("provenance", {})
            new_id = new_cand.entity_id

            # Case 2: Explicit Correction / Invalidation
            invalidates_target = new_prov.get("invalidates") or new_ent.get("invalidated_by")
            if invalidates_target:
                prop = ContradictionProposal(
                    proposal_id=f"prop_corr_{hashlib.sha256(f'{new_id}:{invalidates_target}'.encode()).hexdigest()[:12]}",
                    kind=ContradictionKind.EXPLICIT_CORRECTION,
                    subject_entity_id=new_id,
                    conflicting_entity_id=invalidates_target,
                    proposed_action="invalidate",
                    rationale=f"Entity {new_id} explicitly invalidates or corrects {invalidates_target}",
                    confidence=1.0,
                    created_at=now_iso,
                )
                proposals.append(prop)

            # Case 3: Superseding Decision
            supersedes_target = new_prov.get("supersedes")
            if new_cand.entity_type == SemanticEntityType.DECISION and (
                supersedes_target or new_ent.get("status") == "superseded"
            ):
                target = supersedes_target or new_ent.get("decision_id", "")
                prop = ContradictionProposal(
                    proposal_id=f"prop_sup_{hashlib.sha256(f'{new_id}:{target}'.encode()).hexdigest()[:12]}",
                    kind=ContradictionKind.SUPERSEDING_DECISION,
                    subject_entity_id=new_id,
                    conflicting_entity_id=target,
                    proposed_action="supersede",
                    rationale=f"Decision {new_id} supersedes prior decision {target}",
                    confidence=1.0,
                    created_at=now_iso,
                )
                proposals.append(prop)

            # Cross-candidate comparisons with all other candidates
            for other_cand in all_candidates:
                if other_cand.entity_id == new_id:
                    continue

                other_ent = other_cand.entity
                other_id = other_cand.entity_id

                # Case 1: Conflicting Observations
                if (
                    new_cand.entity_type == SemanticEntityType.OBSERVATION
                    and other_cand.entity_type == SemanticEntityType.OBSERVATION
                    and self._check_text_contradiction(
                        new_ent.get("content", ""), other_ent.get("content", "")
                    )
                ):
                    prop = ContradictionProposal(
                        proposal_id=f"prop_obs_{hashlib.sha256(f'{new_id}:{other_id}'.encode()).hexdigest()[:12]}",
                        kind=ContradictionKind.CONFLICTING_OBSERVATION,
                        subject_entity_id=new_id,
                        conflicting_entity_id=other_id,
                        proposed_action="flag_contradiction",
                        rationale="Direct semantic conflict detected between observations",
                        confidence=0.85,
                        created_at=now_iso,
                    )
                    proposals.append(prop)

                # Case 4: Stale Fact
                if (
                    new_cand.entity_type == SemanticEntityType.FACT
                    and other_cand.entity_type == SemanticEntityType.FACT
                ):
                    # Check validity expiry
                    valid_to = other_ent.get("provenance", {}).get("valid_to")
                    if valid_to and valid_to < now_iso:
                        prop = ContradictionProposal(
                            proposal_id=f"prop_stale_{hashlib.sha256(f'{new_id}:{other_id}'.encode()).hexdigest()[:12]}",
                            kind=ContradictionKind.STALE_FACT,
                            subject_entity_id=new_id,
                            conflicting_entity_id=other_id,
                            proposed_action="supersede",
                            rationale=f"Fact {other_id} valid_to expired ({valid_to}); new fact {new_id} observed",
                            confidence=0.9,
                            created_at=now_iso,
                        )
                        proposals.append(prop)

                # Case 5: Unresolved Contradiction (Opposing facts or assumptions)
                if (
                    new_cand.entity_type in (SemanticEntityType.FACT, SemanticEntityType.ASSUMPTION)
                    and other_cand.entity_type == new_cand.entity_type
                ):
                    stmt1 = new_ent.get("statement", "")
                    stmt2 = other_ent.get("statement", "")
                    if self._check_text_contradiction(stmt1, stmt2):
                        prop = ContradictionProposal(
                            proposal_id=f"prop_unres_{hashlib.sha256(f'{new_id}:{other_id}'.encode()).hexdigest()[:12]}",
                            kind=ContradictionKind.UNRESOLVED_CONTRADICTION,
                            subject_entity_id=new_id,
                            conflicting_entity_id=other_id,
                            proposed_action="review_required",
                            rationale=f"Unresolved semantic contradiction between {new_cand.entity_type.value}s",
                            confidence=0.8,
                            created_at=now_iso,
                        )
                        proposals.append(prop)

        # Deduplicate proposals by proposal_id
        unique_props: dict[str, ContradictionProposal] = {p.proposal_id: p for p in proposals}
        return list(unique_props.values())

    def _check_text_contradiction(self, text1: str, text2: str) -> bool:
        """Deterministic heuristic check for mutual contradiction between two statements."""
        t1 = text1.strip().lower()
        t2 = text2.strip().lower()
        if not t1 or not t2:
            return False

        # Direct negation pairs
        negation_pairs = [
            ("is required", "is not required"),
            ("enabled", "disabled"),
            ("passed", "failed"),
            ("supported", "unsupported"),
            ("true", "false"),
            ("valid", "invalid"),
            ("must be used", "must not be used"),
            ("operational", "down"),
            ("offline", "online"),
        ]
        for pos, neg in negation_pairs:
            if (pos in t1 and neg in t2) or (neg in t1 and pos in t2):
                # Ensure they share topic keywords
                words1 = set(re.findall(r"\w+", t1)) - {"is", "not", "the", "a", "an", "be", "to"}
                words2 = set(re.findall(r"\w+", t2)) - {"is", "not", "the", "a", "an", "be", "to"}
                if len(words1.intersection(words2)) >= 2:
                    return True
        return False

    def _validate_candidates(
        self, candidates: list[SemanticEntityCandidate]
    ) -> tuple[list[SemanticEntityCandidate], list[str]]:
        """Validate all candidate dictionaries against Pydantic models (matching Phase 1 JSON schema)."""
        valid: list[SemanticEntityCandidate] = []
        errors: list[str] = []

        for cand in candidates:
            model_cls = ENTITY_TYPE_TO_MODEL.get(cand.entity_type)
            if model_cls is None:
                errors.append(
                    f"Candidate {cand.entity_id}: unsupported entity type {cand.entity_type}"
                )
                continue

            try:
                # Validate entity payload
                validated = model_cls.model_validate(cand.entity)
                # Ensure dump matches clean dict
                clean_dump = validated.model_dump(exclude_none=True)
                cand.entity = clean_dump
                valid.append(cand)
            except Exception as e:
                errors.append(f"Candidate {cand.entity_id} failed schema validation: {e}")

        return valid, errors

    # -------------------------------------------------------------------------
    # Evaluation Harness (G3.7)
    # -------------------------------------------------------------------------

    def evaluate_dataset(self, dataset_path: Path | str) -> dict[str, Any]:
        """Run evaluation benchmark across a versioned test dataset.

        Computes precision, recall by entity type, false verified rate, duplicate rate,
        and contradiction detection rate.
        """
        path = Path(dataset_path)
        if not path.exists():
            raise FileNotFoundError(f"Evaluation dataset not found: {path}")

        with open(path, encoding="utf-8") as f:
            dataset = json.load(f)

        samples = dataset.get("samples", [])
        total_samples = len(samples)

        # Counts
        tp_by_type: dict[str, int] = {t.value: 0 for t in SemanticEntityType}
        fp_by_type: dict[str, int] = {t.value: 0 for t in SemanticEntityType}
        fn_by_type: dict[str, int] = {t.value: 0 for t in SemanticEntityType}

        total_verified_candidates = 0
        false_verified_candidates = 0
        total_duplicates_detected = 0
        total_raw_candidates = 0

        expected_contradictions_count = 0
        detected_contradictions_count = 0
        prompt_injection_test_count = 0
        prompt_injection_stopped_count = 0

        existing_knowledge: list[SemanticEntityCandidate] = []

        for sample in samples:
            input_type = sample.get("input_type")
            expected_entities = sample.get("expected_entities", [])
            expected_contradiction = sample.get("expected_contradiction")
            is_prompt_injection = sample.get("is_prompt_injection", False)

            if is_prompt_injection:
                prompt_injection_test_count += 1

            if expected_contradiction:
                expected_contradictions_count += 1

            # Compile sample
            if input_type == "structured_event":
                evt_dict = sample["input"]
                comp_result = self.compile_event(
                    evt_dict,
                    existing_candidates=existing_knowledge,
                )
            elif input_type == "unstructured_text":
                text = sample["input"]
                mock_out = sample.get("mock_model_output")
                provider: ExtractionProviderProtocol | None = None
                if mock_out is not None:

                    class _MockEvalProvider:
                        def __init__(self, output_items: list[dict[str, Any]]) -> None:
                            self._output = output_items

                        def extract_unstructured(
                            self, text: str, context: dict[str, Any] | None = None
                        ) -> list[dict[str, Any]]:
                            return self._output

                    provider = _MockEvalProvider(mock_out)

                comp_result = self.compile_unstructured(
                    project_id=sample.get("project_id", "prj_eval_test"),
                    text=text,
                    existing_candidates=existing_knowledge,
                    model_provider=provider,
                )
            else:
                continue

            total_raw_candidates += comp_result.metrics.get(
                "raw_candidate_count", len(comp_result.candidates)
            )
            total_duplicates_detected += comp_result.duplicate_count

            # Check prompt injection isolation (G3.6)
            if is_prompt_injection:
                # Any candidate generated from prompt injection must NOT be verified!
                has_escaped_verification = any(
                    c.verification_status == VerificationStatus.VERIFIED
                    for c in comp_result.candidates
                )
                if not has_escaped_verification and (
                    comp_result.prompt_injection_detected_count > 0 or not comp_result.candidates
                ):
                    prompt_injection_stopped_count += 1

            # Check false verified rate (G3.2 & G3.7)
            for cand in comp_result.candidates:
                if cand.verification_status == VerificationStatus.VERIFIED:
                    total_verified_candidates += 1
                    # If this candidate came from model extraction or untrusted injection, it's a critical failure!
                    if cand.source == "model_extraction" or is_prompt_injection:
                        false_verified_candidates += 1

            # Check entity type precision / recall
            extracted_types = [c.entity_type.value for c in comp_result.candidates]
            expected_types = [e.get("entity_type") for e in expected_entities]

            for t in expected_types:
                if t in extracted_types:
                    tp_by_type[t] = tp_by_type.get(t, 0) + 1
                    extracted_types.remove(t)
                else:
                    fn_by_type[t] = fn_by_type.get(t, 0) + 1

            for extra in extracted_types:
                fp_by_type[extra] = fp_by_type.get(extra, 0) + 1

            # Contradiction detection
            if expected_contradiction and any(
                p.kind.value == expected_contradiction for p in comp_result.contradiction_proposals
            ):
                detected_contradictions_count += 1

            # Add to rolling knowledge for subsequent contradiction checks
            existing_knowledge.extend(comp_result.candidates)

        # Compute metric percentages with honest zero-support reporting (G3.7)
        precision_by_type: dict[str, float | None] = {}
        recall_by_type: dict[str, float | None] = {}
        by_entity_type_counts: dict[str, dict[str, int]] = {}

        for t in SemanticEntityType:
            tp = tp_by_type[t.value]
            fp = fp_by_type[t.value]
            fn = fn_by_type[t.value]
            expected_count = tp + fn
            predicted_count = tp + fp
            by_entity_type_counts[t.value] = {
                "expected_count": expected_count,
                "predicted_count": predicted_count,
                "tp": tp,
                "fp": fp,
                "fn": fn,
            }

            if expected_count == 0 and predicted_count == 0:
                precision_by_type[t.value] = None
                recall_by_type[t.value] = None
            elif predicted_count == 0:
                precision_by_type[t.value] = None
                recall_by_type[t.value] = 0.0
            elif expected_count == 0:
                precision_by_type[t.value] = 0.0
                recall_by_type[t.value] = None
            else:
                precision_by_type[t.value] = round(tp / predicted_count, 4)
                recall_by_type[t.value] = round(tp / expected_count, 4)

        valid_precisions = [p for p in precision_by_type.values() if p is not None]
        valid_recalls = [r for r in recall_by_type.values() if r is not None]
        macro_precision = (
            round(sum(valid_precisions) / len(valid_precisions), 4) if valid_precisions else None
        )
        macro_recall = round(sum(valid_recalls) / len(valid_recalls), 4) if valid_recalls else None

        false_verified_rate = (
            round(false_verified_candidates / total_verified_candidates, 4)
            if total_verified_candidates > 0
            else 0.0
        )
        duplicate_rate = (
            round(total_duplicates_detected / total_raw_candidates, 4)
            if total_raw_candidates > 0
            else 0.0
        )
        contradiction_detection_rate = (
            round(detected_contradictions_count / expected_contradictions_count, 4)
            if expected_contradictions_count > 0
            else 1.0
        )
        prompt_injection_defense_rate = (
            round(prompt_injection_stopped_count / prompt_injection_test_count, 4)
            if prompt_injection_test_count > 0
            else 1.0
        )

        return {
            "dataset_version": dataset.get("version", "1.0.0"),
            "total_samples": total_samples,
            "metrics": {
                "precision_by_entity_type": precision_by_type,
                "recall_by_entity_type": recall_by_type,
                "macro_precision": macro_precision,
                "macro_recall": macro_recall,
                "false_verified_rate": false_verified_rate,
                "duplicate_rate": duplicate_rate,
                "contradiction_detection_rate": contradiction_detection_rate,
                "prompt_injection_defense_rate": prompt_injection_defense_rate,
            },
            "counts": {
                "by_entity_type": by_entity_type_counts,
                "total_verified_candidates": total_verified_candidates,
                "false_verified_candidates": false_verified_candidates,
                "total_duplicates_detected": total_duplicates_detected,
                "total_raw_candidates": total_raw_candidates,
                "expected_contradictions": expected_contradictions_count,
                "detected_contradictions": detected_contradictions_count,
                "prompt_injection_tests": prompt_injection_test_count,
                "prompt_injection_stopped": prompt_injection_stopped_count,
            },
        }


__all__ = [
    "PROJECT_EVENT_DISPATCH_REGISTRY",
    "CompilationResult",
    "EventSemanticDisposition",
    "ExtractionProviderProtocol",
    "SemanticCompiler",
    "VerifiedEventBatch",
    "detect_prompt_injection",
    "scrub_secrets",
]
