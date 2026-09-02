#!/usr/bin/env python3
"""Verify the exact provenance policy emitted by ``gh attestation verify``."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

if TYPE_CHECKING:
    from scripts.release_bindings import (
        required_git_object,
        required_positive_integer,
        required_repository,
        required_text,
    )
else:
    try:
        from scripts.release_bindings import (
            required_git_object,
            required_positive_integer,
            required_repository,
            required_text,
        )
    except ModuleNotFoundError:  # pragma: no cover - package import path in tests/tools.
        from release_bindings import (
            required_git_object,
            required_positive_integer,
            required_repository,
            required_text,
        )

PREDICATE_TYPE = "https://slsa.dev/provenance/v1"
RUN_ID_RE = re.compile(r"/actions/runs/(\d+)(?:/|$)")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
WORKFLOW_PATH_RE = re.compile(r"^\.github/workflows/[A-Za-z0-9_.-]+$")
MAX_INPUT_BYTES = 20 * 1024 * 1024


def _walk(value: Any) -> Iterator[Any]:
    """Yield every JSON node without interpreting any node as executable data."""
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _dicts(value: Any) -> Iterator[dict[str, Any]]:
    for node in _walk(value):
        if isinstance(node, dict):
            yield node


def _sha256(value: Any, label: str) -> str:
    text = required_text(value, label)
    if text.startswith("sha256:"):
        text = text.removeprefix("sha256:")
    if SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _normalize_repository(value: Any, label: str) -> str:
    text = required_text(value, label).strip().rstrip("/")
    for prefix in (
        "git+https://github.com/",
        "git://github.com/",
        "https://github.com/",
        "http://github.com/",
        "github.com/",
    ):
        if text.startswith(prefix):
            text = text.removeprefix(prefix)
            break
    text = text.removesuffix(".git").strip("/")
    return required_repository(text, label)


def _repository_in_uri(value: Any, repository: str) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip().removesuffix(".git")
    return text == repository or f"github.com/{repository}" in text


def _workflow_nodes(payload: Any) -> list[dict[str, Any]]:
    """Return workflow identity objects from the GitHub SLSA statement."""
    nodes: list[dict[str, Any]] = []
    for node in _dicts(payload):
        workflow = node.get("workflow")
        if isinstance(workflow, dict):
            nodes.append(workflow)
        if (
            isinstance(node.get("repository"), str)
            and isinstance(node.get("path"), str)
            and isinstance(node.get("ref"), str)
            and node["path"].startswith(".github/workflows/")
        ):
            nodes.append(node)
    return nodes


def _attestation_units(payload: Any) -> Iterator[dict[str, Any]]:
    """Yield paired attestation results without crossing a discovered unit boundary."""
    if isinstance(payload, dict):
        if isinstance(payload.get("attestation"), dict) and isinstance(
            payload.get("verificationResult"), dict
        ):
            yield payload
            return
        for child in payload.values():
            yield from _attestation_units(child)
    elif isinstance(payload, list):
        for child in payload:
            yield from _attestation_units(child)


def _attestation_parts(
    unit: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    attestation = unit.get("attestation")
    verification = unit.get("verificationResult")
    if not isinstance(attestation, dict) or not isinstance(verification, dict):
        return None
    statement = verification.get("statement")
    signature = verification.get("signature")
    certificate = signature.get("certificate") if isinstance(signature, dict) else None
    if not isinstance(statement, dict):
        statement = attestation.get("decodedMaterial")
    if not isinstance(certificate, dict):
        certificate = verification.get("certificate")
    if not isinstance(statement, dict) or not isinstance(certificate, dict):
        return None
    if not isinstance(statement.get("subject"), list) or not isinstance(
        statement.get("predicateType"), str
    ):
        return None
    return statement, certificate


def _subject_entries(statement: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for subject in statement["subject"]:
        if not isinstance(subject, dict) or not isinstance(subject.get("name"), str):
            continue
        digest = subject.get("digest")
        if not isinstance(digest, dict):
            continue
        for algorithm, value in digest.items():
            if algorithm == "sha256" and isinstance(value, str):
                entries.append({"name": subject["name"], "sha256": value})
    return entries


def _workflow_revisions(
    workflows: list[dict[str, Any]],
    statement: dict[str, Any],
    certificate: dict[str, Any],
    repository: str,
) -> set[str]:
    revisions: set[str] = set()

    def add(value: Any) -> None:
        if not isinstance(value, str):
            return
        candidate = value.removeprefix("sha1:")
        if re.fullmatch(r"[0-9a-f]{40}", candidate):
            revisions.add(candidate)

    for workflow in workflows:
        for key in ("sha", "commit", "revision", "sourceRevision", "source_revision"):
            add(workflow.get(key))

    for key in (
        "sourceRepositoryDigest",
        "githubWorkflowSHA",
        "sourceRevision",
        "source_revision",
    ):
        add(certificate.get(key))

    for node in _dicts(statement):
        config_source = node.get("configSource")
        if isinstance(config_source, dict):
            for key in ("sha", "commit", "revision", "sourceRevision", "source_revision"):
                add(config_source.get(key))
            digest = config_source.get("digest")
            if isinstance(digest, dict):
                for value in digest.values():
                    add(value)

        dependencies = node.get("resolvedDependencies")
        if isinstance(dependencies, list):
            for dependency in dependencies:
                if not isinstance(dependency, dict) or not _repository_in_uri(
                    dependency.get("uri"), repository
                ):
                    continue
                digest = dependency.get("digest")
                if isinstance(digest, dict):
                    for value in digest.values():
                        add(value)
                for key in ("sha", "commit", "revision", "sourceRevision", "source_revision"):
                    add(dependency.get(key))

        for key in ("sourceRevision", "source_revision", "workflowRevision", "workflow_revision"):
            add(node.get(key))
    return revisions


def _invocation_run_ids(payload: Any) -> set[str]:
    run_ids: set[str] = set()
    for node in _dicts(payload):
        for key, value in node.items():
            if not isinstance(value, str | int):
                continue
            text = str(value)
            if key in {"invocationId", "invocation_id", "runInvocationURI", "runInvocationUri"}:
                match = RUN_ID_RE.search(text)
                if match:
                    run_ids.add(match.group(1))
            elif key in {"runId", "run_id", "workflow_run_id", "workflowRunId"}:
                if re.fullmatch(r"[1-9][0-9]*", text):
                    run_ids.add(text)
    return run_ids


def _workflow_match(
    workflows: list[dict[str, Any]],
    *,
    repository: str,
    workflow: str,
    event: str,
    ref: str,
) -> bool:
    for candidate in workflows:
        try:
            candidate_repository = _normalize_repository(
                candidate.get("repository"), "attestation workflow repository"
            )
        except ValueError:
            continue
        candidate_path = candidate.get("path")
        candidate_event = candidate.get("event", candidate.get("event_name"))
        if (
            candidate_repository == repository
            and candidate_path == workflow
            and candidate_event == event
            and candidate.get("ref") == ref
        ):
            return True
    return False


def _certificate_match(
    certificates: list[dict[str, Any]],
    *,
    expected_san: str,
    repository: str,
    event: str,
    ref: str,
) -> bool:
    """Match the Fulcio certificate summary emitted by gh attestation verify."""
    for certificate in certificates:
        if certificate.get("subjectAlternativeName") != expected_san:
            continue
        repository_value = certificate.get(
            "sourceRepositoryURI", certificate.get("githubWorkflowRepository")
        )
        try:
            certificate_repository = _normalize_repository(
                repository_value, "attestation source repository"
            )
        except ValueError:
            continue
        signer_uri = certificate.get("buildSignerURI", expected_san)
        if signer_uri != expected_san:
            continue
        certificate_ref = certificate.get(
            "sourceRepositoryRef", certificate.get("githubWorkflowRef")
        )
        certificate_event = certificate.get(
            "buildTrigger", certificate.get("githubWorkflowTrigger")
        )
        if (
            certificate_repository == repository
            and certificate_ref == ref
            and certificate_event == event
        ):
            return True
    return False


def verify_attestation_payload(
    payload: Any,
    *,
    subject_name: str,
    subject_digest: str,
    predicate_type: str,
    repository: str,
    workflow: str,
    source_revision: str,
    event: str,
    ref: str,
    run_id: str,
) -> dict[str, Any]:
    """Return a sanitized policy result or fail closed on any missing binding."""
    subject_name = required_text(subject_name, "attestation subject name")
    expected_digest = _sha256(subject_digest, "expected attestation subject digest")
    predicate_type = required_text(predicate_type, "attestation predicate type")
    repository = _normalize_repository(repository, "expected attestation repository")
    workflow = required_text(workflow, "expected signer workflow")
    if WORKFLOW_PATH_RE.fullmatch(workflow) is None:
        raise ValueError("expected signer workflow must be a .github/workflows path")
    source_revision = required_git_object(source_revision, "expected source revision")
    event = required_text(event, "expected workflow event")
    ref = required_text(ref, "expected workflow ref")
    run_id = required_positive_integer(run_id, "expected workflow run ID")

    expected_san = f"https://github.com/{repository}/{workflow}@{ref}"
    matching: list[dict[str, Any]] = []
    for unit in _attestation_units(payload):
        parts = _attestation_parts(unit)
        if parts is None:
            continue
        statement, certificate = parts
        workflows = _workflow_nodes(statement)
        workflow_bound = _workflow_match(
            workflows,
            repository=repository,
            workflow=workflow,
            event=event,
            ref=ref,
        ) or _certificate_match(
            [certificate],
            expected_san=expected_san,
            repository=repository,
            event=event,
            ref=ref,
        )
        if not workflow_bound:
            continue
        if certificate.get("subjectAlternativeName") != expected_san:
            continue
        revisions = _workflow_revisions(workflows, statement, certificate, repository)
        if source_revision not in revisions:
            continue
        run_ids = _invocation_run_ids(statement) | _invocation_run_ids(certificate)
        if run_id not in run_ids:
            continue

        if statement["predicateType"] != predicate_type:
            continue
        subjects = _subject_entries(statement)
        if not any(
            entry["name"] == subject_name and entry["sha256"] == expected_digest
            for entry in subjects
        ):
            continue
        matching.append(
            {
                "predicate_type": statement["predicateType"],
                "subjects": subjects,
            }
        )

    if not matching:
        raise ValueError(
            "no attestation satisfied exact subject, predicate, signer, source, event, ref, and run bindings"
        )

    return {
        "schema_version": "power.attestation.policy.v1",
        "status": "verified",
        "subject": {"name": subject_name, "sha256": expected_digest},
        "predicate_type": predicate_type,
        "signer": {"repository": repository, "workflow": workflow, "certificate_san": expected_san},
        "source_revision": source_revision,
        "workflow": {"event": event, "ref": ref, "run_id": run_id},
        "matching_attestation_count": len(matching),
        "matching_subjects": matching,
    }


def verify_attestation_file(
    input_path: Path,
    *,
    subject_name: str,
    subject_digest: str,
    predicate_type: str,
    repository: str,
    workflow: str,
    source_revision: str,
    event: str,
    ref: str,
    run_id: str,
) -> dict[str, Any]:
    """Load one bounded regular JSON file and apply the exact policy."""
    if input_path.is_symlink() or not input_path.is_file():
        raise ValueError(f"attestation output is not a regular file: {input_path}")
    if input_path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("attestation output exceeds the bounded input size")
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("attestation output is not valid JSON") from exc
    return verify_attestation_payload(
        payload,
        subject_name=subject_name,
        subject_digest=subject_digest,
        predicate_type=predicate_type,
        repository=repository,
        workflow=workflow,
        source_revision=source_revision,
        event=event,
        ref=ref,
        run_id=run_id,
    )


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    if path.is_symlink():
        raise ValueError(f"attestation policy output must not be a symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--subject-name", required=True)
    parser.add_argument("--subject-digest", required=True)
    parser.add_argument("--predicate-type", default=PREDICATE_TYPE)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)

    try:
        result = verify_attestation_file(
            args.input,
            subject_name=args.subject_name,
            subject_digest=args.subject_digest,
            predicate_type=args.predicate_type,
            repository=args.repository,
            workflow=args.workflow,
            source_revision=args.source_revision,
            event=args.event,
            ref=args.ref,
            run_id=args.run_id,
        )
        _write_json_atomically(args.output, result)
    except (OSError, ValueError) as exc:
        print(f"attestation policy failed closed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
