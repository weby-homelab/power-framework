"""Regression tests for the exact future attestation provenance policy."""

from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.verify_attestation_provenance import verify_attestation_payload

REPOSITORY = "weby-homelab/power-framework"
WORKFLOW = ".github/workflows/release.yml"
REVISION = "a" * 40
RUN_ID = "12345"
WHEEL_DIGEST = "b" * 64


def _payload() -> dict[str, object]:
    return {
        "attestation": {
            "decodedMaterial": {
                "subject": [
                    {
                        "name": "power_framework-3.7.10-py3-none-any.whl",
                        "digest": {"sha256": WHEEL_DIGEST},
                    }
                ],
                "predicateType": "https://slsa.dev/provenance/v1",
                "predicate": {
                    "buildDefinition": {
                        "externalParameters": {
                            "workflow": {
                                "repository": REPOSITORY,
                                "path": WORKFLOW,
                                "ref": "refs/heads/main",
                                "event": "workflow_dispatch",
                            }
                        },
                        "resolvedDependencies": [
                            {
                                "uri": f"git+https://github.com/{REPOSITORY}@refs/heads/main",
                                "digest": {"sha1": REVISION},
                            }
                        ],
                    },
                    "runDetails": {
                        "metadata": {
                            "invocationId": (
                                f"https://github.com/{REPOSITORY}/actions/runs/{RUN_ID}/attempts/1"
                            )
                        }
                    },
                },
            }
        },
        "verificationResult": {
            "certificate": {
                "subjectAlternativeName": (
                    f"https://github.com/{REPOSITORY}/{WORKFLOW}@refs/heads/main"
                ),
                "sourceRepositoryURI": f"https://github.com/{REPOSITORY}",
                "sourceRepositoryDigest": REVISION,
                "sourceRepositoryRef": "refs/heads/main",
                "buildTrigger": "workflow_dispatch",
                "buildSignerURI": (f"https://github.com/{REPOSITORY}/{WORKFLOW}@refs/heads/main"),
                "runInvocationURI": (
                    f"https://github.com/{REPOSITORY}/actions/runs/{RUN_ID}/attempts/1"
                ),
            }
        },
    }


def _verify(payload: dict[str, object]) -> dict[str, object]:
    return verify_attestation_payload(
        payload,
        subject_name="power_framework-3.7.10-py3-none-any.whl",
        subject_digest=WHEEL_DIGEST,
        predicate_type="https://slsa.dev/provenance/v1",
        repository=REPOSITORY,
        workflow=WORKFLOW,
        source_revision=REVISION,
        event="workflow_dispatch",
        ref="refs/heads/main",
        run_id=RUN_ID,
    )


def test_exact_attestation_policy_returns_sanitized_summary() -> None:
    result = _verify(_payload())

    assert result["status"] == "verified"
    assert result["subject"] == {
        "name": "power_framework-3.7.10-py3-none-any.whl",
        "sha256": WHEEL_DIGEST,
    }
    assert result["signer"] == {
        "repository": REPOSITORY,
        "workflow": WORKFLOW,
        "certificate_san": f"https://github.com/{REPOSITORY}/{WORKFLOW}@refs/heads/main",
    }
    assert result["workflow"] == {
        "event": "workflow_dispatch",
        "ref": "refs/heads/main",
        "run_id": RUN_ID,
    }


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("subject_digest", "c" * 64),
        ("predicate_type", "https://example.invalid/predicate"),
        ("source_revision", "d" * 40),
        ("run_id", "12346"),
    ],
)
def test_attestation_policy_rejects_binding_mismatch(path: str, value: str) -> None:
    payload = deepcopy(_payload())
    kwargs = {
        "subject_name": "power_framework-3.7.10-py3-none-any.whl",
        "subject_digest": WHEEL_DIGEST,
        "predicate_type": "https://slsa.dev/provenance/v1",
        "repository": REPOSITORY,
        "workflow": WORKFLOW,
        "source_revision": REVISION,
        "event": "workflow_dispatch",
        "ref": "refs/heads/main",
        "run_id": RUN_ID,
    }
    kwargs[path] = value

    with pytest.raises(ValueError, match="no attestation satisfied"):
        verify_attestation_payload(payload, **kwargs)


def test_attestation_policy_requires_exact_signer_san() -> None:
    payload = _payload()
    verification_result = payload["verificationResult"]
    assert isinstance(verification_result, dict)
    certificate = verification_result["certificate"]
    assert isinstance(certificate, dict)
    certificate["subjectAlternativeName"] = (
        "https://github.com/other/repository/workflow.yml@refs/heads/main"
    )

    with pytest.raises(ValueError, match="no attestation satisfied"):
        _verify(payload)


def test_attestation_policy_accepts_gh_certificate_summary_shape() -> None:
    payload = _payload()
    attestation = payload["attestation"]
    assert isinstance(attestation, dict)
    decoded = attestation["decodedMaterial"]
    assert isinstance(decoded, dict)
    predicate = decoded["predicate"]
    assert isinstance(predicate, dict)
    build_definition = predicate["buildDefinition"]
    assert isinstance(build_definition, dict)
    external_parameters = build_definition["externalParameters"]
    assert isinstance(external_parameters, dict)
    del external_parameters["workflow"]

    result = _verify(payload)
    assert result["matching_attestation_count"] == 1
