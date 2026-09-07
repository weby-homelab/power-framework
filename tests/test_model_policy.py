"""Adversarial regression tests for the centralized model egress boundary."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from power_framework.core import model_policy
from power_framework.core.egress import EgressDeniedError, EgressOperation
from power_framework.experimental import embeddings, reranker


def _files(tmp_path: Path, *, mismatch: bool = False) -> tuple[dict[str, str], dict[str, str]]:
    paths: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for filename, content in (
        ("model.onnx", b"synthetic model"),
        ("tokenizer.json", b'{"synthetic":true}'),
    ):
        path = tmp_path / filename
        path.write_bytes(b"tampered" if mismatch and filename == "model.onnx" else content)
        paths[filename] = str(path)
        hashes[filename] = hashlib.sha256(content).hexdigest()
    return paths, hashes


def _acquire_kwargs(repo: str, revision: str, hashes: dict[str, str]) -> dict[str, object]:
    return {
        "operation": EgressOperation.EMBEDDINGS,
        "repo": repo,
        "revision": revision,
        "provider": "bge-m3-onnx",
        "required_files": ("model.onnx", "tokenizer.json"),
        "canonical_repo": repo,
        "canonical_revision": revision,
        "canonical_provider": "bge-m3-onnx",
        "canonical_license": "MIT",
        "canonical_hashes": hashes,
    }


def _fake_hub(calls: list[str], paths: dict[str, str], *, failure: bool = False) -> ModuleType:
    module = ModuleType("huggingface_hub")

    def download(_repo: str, filename: str, **_kwargs: object) -> str:
        calls.append(filename)
        if failure:
            raise RuntimeError("synthetic download failure")
        return paths[filename]

    module.hf_hub_download = download  # type: ignore[attr-defined]
    return module


@pytest.mark.parametrize("policy", [None, "deny"])
def test_default_or_explicit_deny_rejects_before_hf_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, policy: str | None
) -> None:
    """No HF network-capable function is called when the cache is incomplete."""
    _paths, hashes = _files(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(calls, _paths))
    if policy is None:
        monkeypatch.delenv("POWER_EGRESS_POLICY", raising=False)
    else:
        monkeypatch.setenv("POWER_EGRESS_POLICY", policy)

    with pytest.raises(EgressDeniedError, match="POWER_EGRESS_POLICY=deny"):
        model_policy.acquire_model_files(**_acquire_kwargs("org/model", "a" * 40, hashes))
    assert calls == []


@pytest.mark.parametrize("offline_name", model_policy.MODEL_OFFLINE_ENV_VARS)
def test_any_offline_flag_wins_over_allow_public_before_hf_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline_name: str
) -> None:
    """POWER and maintained HF offline flags all force deterministic cache-only behavior."""
    _paths, hashes = _files(tmp_path)
    calls: list[str] = []
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
    monkeypatch.setenv(offline_name, "1")
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(calls, _paths))

    with pytest.raises(model_policy.ModelOfflineError, match="model_offline_cache_missing"):
        model_policy.acquire_model_files(**_acquire_kwargs("org/model", "a" * 40, hashes))
    assert calls == []


def test_unapproved_hf_endpoint_is_rejected_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _paths, hashes = _files(tmp_path)
    calls: list[str] = []
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
    monkeypatch.setenv("HF_ENDPOINT", "https://attacker.example")
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(calls, _paths))

    with pytest.raises(model_policy.ModelApprovalError, match="model_endpoint_not_approved"):
        model_policy.acquire_model_files(**_acquire_kwargs("org/model", "a" * 40, hashes))
    assert calls == []


def test_complete_cached_canonical_model_works_under_deny_without_hf_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A verified local canonical snapshot does not need egress authorization."""
    paths, hashes = _files(tmp_path)
    calls: list[str] = []
    monkeypatch.setenv("POWER_EGRESS_POLICY", "deny")
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: paths)
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(calls, paths))

    result = model_policy.acquire_model_files(**_acquire_kwargs("org/model", "a" * 40, hashes))

    assert result == paths
    assert calls == []


def test_custom_model_requires_explicit_approval_and_old_bypass_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A legacy boolean cannot authorize an unpinned custom model."""
    paths, hashes = _files(tmp_path)
    calls: list[str] = []
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
    monkeypatch.setenv("POWER_ALLOW_UNVERIFIED_MODELS", "1")
    monkeypatch.delenv(model_policy.ALLOW_CUSTOM_MODELS_ENV, raising=False)
    monkeypatch.delenv(model_policy.MODEL_APPROVAL_ENV, raising=False)
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(calls, paths))

    with pytest.raises(model_policy.ModelApprovalError, match="custom_model_requires_approval"):
        model_policy.acquire_model_files(
            operation=EgressOperation.EMBEDDINGS,
            repo="custom/model",
            revision="b" * 40,
            provider="bge-m3-onnx",
            required_files=("model.onnx", "tokenizer.json"),
            canonical_repo="org/canonical",
            canonical_revision="a" * 40,
            canonical_provider="bge-m3-onnx",
            canonical_license="MIT",
            canonical_hashes=hashes,
        )
    assert calls == []


def test_custom_model_without_immutable_revision_is_rejected_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, hashes = _files(tmp_path)
    calls: list[str] = []
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
    monkeypatch.setenv(model_policy.ALLOW_CUSTOM_MODELS_ENV, "1")
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(calls, paths))

    with pytest.raises(model_policy.ModelApprovalError, match="immutable_model_revision_required"):
        model_policy.acquire_model_files(
            operation=EgressOperation.EMBEDDINGS,
            repo="custom/model",
            revision="main",
            provider="bge-m3-onnx",
            required_files=("model.onnx", "tokenizer.json"),
            canonical_repo="org/canonical",
            canonical_revision="a" * 40,
            canonical_provider="bge-m3-onnx",
            canonical_license="MIT",
            canonical_hashes=hashes,
        )
    assert calls == []


def test_custom_model_without_complete_hash_manifest_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, hashes = _files(tmp_path)
    calls: list[str] = []
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
    monkeypatch.setenv(model_policy.ALLOW_CUSTOM_MODELS_ENV, "1")
    monkeypatch.setenv(
        model_policy.MODEL_APPROVAL_ENV,
        json.dumps(
            {
                "repo": "custom/model",
                "revision": "b" * 40,
                "operation": "embeddings",
                "provider": "bge-m3-onnx",
                "license": "MIT",
                "files": {"model.onnx": hashes["model.onnx"]},
            }
        ),
    )
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(calls, paths))

    with pytest.raises(model_policy.ModelIntegrityError, match="complete_model_file_manifest"):
        model_policy.acquire_model_files(
            operation=EgressOperation.EMBEDDINGS,
            repo="custom/model",
            revision="b" * 40,
            provider="bge-m3-onnx",
            required_files=("model.onnx", "tokenizer.json"),
            canonical_repo="org/canonical",
            canonical_revision="a" * 40,
            canonical_provider="bge-m3-onnx",
            canonical_license="MIT",
            canonical_hashes=hashes,
        )
    assert calls == []


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("operation", "reranking", "custom_model_operation_not_approved"),
        ("provider", "other-loader", "custom_model_provider_not_approved"),
        ("license", "", "model_license_required"),
        ("license", "Apache-2.0", "custom_model_license_not_approved"),
    ],
)
def test_custom_approval_is_bound_to_operation_provider_and_license(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
    error: str,
) -> None:
    paths, hashes = _files(tmp_path)
    calls: list[str] = []
    repo = "custom/model"
    revision = "b" * 40
    approval: dict[str, object] = {
        "operation": "embeddings",
        "provider": "bge-m3-onnx",
        "license": "MIT",
        "repo": repo,
        "revision": revision,
        "files": hashes,
    }
    approval[field] = value
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
    monkeypatch.setenv(model_policy.ALLOW_CUSTOM_MODELS_ENV, "1")
    monkeypatch.setenv(model_policy.MODEL_APPROVAL_ENV, json.dumps(approval))
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(calls, paths))

    with pytest.raises(model_policy.ModelApprovalError, match=error):
        model_policy.acquire_model_files(
            operation=EgressOperation.EMBEDDINGS,
            repo=repo,
            revision=revision,
            provider="bge-m3-onnx",
            required_files=("model.onnx", "tokenizer.json"),
            canonical_repo="org/canonical",
            canonical_revision="a" * 40,
            canonical_provider="bge-m3-onnx",
            canonical_license="MIT",
            canonical_hashes=hashes,
        )
    assert calls == []


def test_approved_immutable_custom_model_downloads_and_verifies_all_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, hashes = _files(tmp_path)
    calls: list[str] = []
    repo = "custom/model"
    revision = "b" * 40
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
    monkeypatch.setenv(model_policy.ALLOW_CUSTOM_MODELS_ENV, "1")
    monkeypatch.setenv(
        model_policy.MODEL_APPROVAL_ENV,
        json.dumps(
            {
                "operation": "embeddings",
                "provider": "bge-m3-onnx",
                "license": "MIT",
                "repo": repo,
                "revision": revision,
                "files": hashes,
            }
        ),
    )
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(calls, paths))

    result = model_policy.acquire_model_files(
        operation=EgressOperation.EMBEDDINGS,
        repo=repo,
        revision=revision,
        provider="bge-m3-onnx",
        required_files=("model.onnx", "tokenizer.json"),
        canonical_repo="org/canonical",
        canonical_revision="a" * 40,
        canonical_provider="bge-m3-onnx",
        canonical_license="MIT",
        canonical_hashes=hashes,
    )

    assert result == paths
    assert calls == ["model.onnx", "tokenizer.json"]


def test_custom_model_hash_mismatch_fails_closed_before_returning_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, hashes = _files(tmp_path, mismatch=True)
    calls: list[str] = []
    repo = "custom/model"
    revision = "b" * 40
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
    monkeypatch.setenv(model_policy.ALLOW_CUSTOM_MODELS_ENV, "1")
    monkeypatch.setenv(
        model_policy.MODEL_APPROVAL_ENV,
        json.dumps(
            {
                "operation": "embeddings",
                "provider": "bge-m3-onnx",
                "license": "MIT",
                "repo": repo,
                "revision": revision,
                "files": hashes,
            }
        ),
    )
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(calls, paths))

    with pytest.raises(
        model_policy.ModelIntegrityError, match=r"model_sha256_mismatch:model\.onnx"
    ):
        model_policy.acquire_model_files(
            operation=EgressOperation.EMBEDDINGS,
            repo=repo,
            revision=revision,
            provider="bge-m3-onnx",
            required_files=("model.onnx", "tokenizer.json"),
            canonical_repo="org/canonical",
            canonical_revision="a" * 40,
            canonical_provider="bge-m3-onnx",
            canonical_license="MIT",
            canonical_hashes=hashes,
        )
    assert calls == ["model.onnx", "tokenizer.json"]


def test_download_exception_does_not_trigger_a_second_network_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _paths, hashes = _files(tmp_path)
    calls: list[str] = []
    repo = "custom/model"
    revision = "b" * 40
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
    monkeypatch.setenv(model_policy.ALLOW_CUSTOM_MODELS_ENV, "1")
    monkeypatch.setenv(
        model_policy.MODEL_APPROVAL_ENV,
        json.dumps(
            {
                "operation": "embeddings",
                "provider": "bge-m3-onnx",
                "license": "MIT",
                "repo": repo,
                "revision": revision,
                "files": hashes,
            }
        ),
    )
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(calls, {}, failure=True))

    with pytest.raises(RuntimeError, match="synthetic download failure"):
        model_policy.acquire_model_files(
            operation=EgressOperation.EMBEDDINGS,
            repo=repo,
            revision=revision,
            provider="bge-m3-onnx",
            required_files=("model.onnx", "tokenizer.json"),
            canonical_repo="org/canonical",
            canonical_revision="a" * 40,
            canonical_provider="bge-m3-onnx",
            canonical_license="MIT",
            canonical_hashes=hashes,
        )
    assert calls == ["model.onnx"]


def test_complete_cached_canonical_reranker_works_under_deny_without_hf_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = {
        "onnx/model.onnx": b"synthetic reranker model",
        "onnx/model.onnx_data": b"synthetic reranker sidecar",
        "tokenizer.json": b'{"synthetic":true}',
    }
    paths: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for filename, content in files.items():
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        paths[filename] = str(path)
        hashes[filename] = hashlib.sha256(content).hexdigest()
    calls: list[str] = []
    monkeypatch.setenv("POWER_EGRESS_POLICY", "deny")
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: paths)
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(calls, paths))

    result = model_policy.acquire_model_files(
        operation=EgressOperation.RERANKING,
        repo="org/reranker",
        revision="c" * 40,
        provider="bge-reranker-v2-m3-onnx",
        required_files=tuple(files),
        canonical_repo="org/reranker",
        canonical_revision="c" * 40,
        canonical_provider="bge-reranker-v2-m3-onnx",
        canonical_license="Apache-2.0",
        canonical_hashes=hashes,
    )

    assert result == paths
    assert calls == []


def test_direct_embedding_and_reranker_loaders_honor_default_deny_before_hf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.delenv("POWER_EGRESS_POLICY", raising=False)
    monkeypatch.delenv("POWER_MODEL_OFFLINE", raising=False)
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(calls, {}))

    with pytest.raises(EgressDeniedError):
        embeddings.BGEM3OnnxManager().embed("synthetic query")
    with pytest.raises(EgressDeniedError):
        reranker.BGEM3Reranker().rerank("synthetic query", ["synthetic document"])
    assert calls == []


def test_reranker_honors_power_model_offline_even_with_allow_public(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
    monkeypatch.setenv("POWER_MODEL_OFFLINE", "1")
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(calls, {}))

    with pytest.raises(model_policy.ModelOfflineError):
        reranker.BGEM3Reranker().rerank("synthetic query", ["synthetic document"])
    assert calls == []


def test_fastembed_and_qwen_constructors_cannot_bypass_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor_calls: list[str] = []

    class FakeEmbedding:
        def __init__(self, **_kwargs: object) -> None:
            constructor_calls.append("embedding")

    fastembed = ModuleType("fastembed")
    fastembed.TextEmbedding = FakeEmbedding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastembed", fastembed)

    with pytest.raises(model_policy.ModelApprovalError, match="immutable_model_revision_required"):
        embeddings.FastEmbedManager(model_name="custom/model")._lazy_init()

    qwen = ModuleType("qwen3_embed")
    qwen.TextEmbedding = FakeEmbedding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "qwen3_embed", qwen)
    with pytest.raises(model_policy.ModelApprovalError, match="immutable_model_revision_required"):
        embeddings.Qwen3EmbeddingManager(model_name="custom/qwen-model")._lazy_init()

    assert constructor_calls == []


def test_colbert_constructor_cannot_bypass_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from power_framework.experimental.colbert_reranker import ColBERTLateInteractionReranker

    monkeypatch.setenv("POWER_RERANKER", "colbert")
    monkeypatch.setattr(
        "power_framework.experimental.colbert_reranker._available_ram_gb", lambda: 16.0
    )
    reranker_instance = ColBERTLateInteractionReranker(model_name="custom/colbert-model")

    with pytest.raises(model_policy.ModelApprovalError, match="immutable_model_revision_required"):
        reranker_instance._lazy_init()


def test_approved_external_loader_receives_verified_local_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    paths, hashes = _files(snapshot)
    (snapshot / "unapproved-config.py").write_text(
        "synthetic unapproved material", encoding="utf-8"
    )
    repo = "custom/model"
    revision = "b" * 40
    monkeypatch.setenv("POWER_EGRESS_POLICY", "deny")
    monkeypatch.setenv(model_policy.ALLOW_CUSTOM_MODELS_ENV, "1")
    monkeypatch.setenv(
        model_policy.MODEL_APPROVAL_ENV,
        json.dumps(
            {
                "operation": "embeddings",
                "provider": "test-external",
                "license": "MIT",
                "repo": repo,
                "revision": revision,
                "files": hashes,
            }
        ),
    )
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: paths)

    prepared = model_policy.prepare_external_model(
        operation=EgressOperation.EMBEDDINGS,
        provider="test-external",
        model_reference=f"{repo}@{revision}",
    )

    staging = Path(prepared.local_reference)
    assert staging != snapshot
    assert staging.is_dir()
    assert set(prepared.files) == set(paths)
    assert all(Path(path).is_relative_to(staging) for path in prepared.files.values())
    assert {Path(path).relative_to(staging).as_posix() for path in prepared.files.values()} == set(
        paths
    )
    assert not (staging / "unapproved-config.py").exists()
