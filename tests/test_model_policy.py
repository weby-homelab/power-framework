"""Adversarial regression tests for the centralized model egress boundary."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from pathlib import Path
from types import ModuleType

import pytest

from power_framework.core import model_policy
from power_framework.core.egress import EgressDeniedError, EgressOperation
from power_framework.experimental import embeddings, reranker


@pytest.fixture(autouse=True)
def isolate_model_policy_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep model-policy assertions independent of shell and CI environment state."""
    assert model_policy.MODEL_OFFLINE_ENV_VARS == (
        "POWER_MODEL_OFFLINE",
        "HF_HUB_OFFLINE",
        "TRANSFORMERS_OFFLINE",
    )
    for name in model_policy.MODEL_OFFLINE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    for name in (
        "HF_ENDPOINT",
        "POWER_EGRESS_POLICY",
        "POWER_ALLOW_UNVERIFIED_MODELS",
        "POWER_ALLOW_NONCOMMERCIAL_MODELS",
        "POWER_EMBED_PROVIDER",
        "POWER_RERANKER",
        "POWER_BGE_M3_ONNX_REPO",
        "POWER_BGE_M3_ONNX_REVISION",
        "POWER_BGE_RERANKER_ONNX_REPO",
        "POWER_BGE_RERANKER_ONNX_REVISION",
        "POWER_QWEN3_RERANKER_MODEL",
        "POWER_JINA_RERANKER_MODEL",
        "POWER_QWEN3_EMBED_MODEL",
        "POWER_OLLAMA_EMBED_MODEL",
        "POWER_EMBEDDING_MODEL",
        "POWER_COLBERT_MODEL",
        model_policy.ALLOW_CUSTOM_MODELS_ENV,
        model_policy.MODEL_APPROVAL_ENV,
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(embeddings, "EMBED_PROVIDER", "bge-m3")
    monkeypatch.setattr(embeddings, "QWEN3_EMBED_MODEL", "n24q02m/Qwen3-Embedding-0.6B-ONNX")
    monkeypatch.setattr(embeddings, "OLLAMA_EMBED_MODEL", "qwen3-embedding:0.6b")
    monkeypatch.setattr(
        embeddings,
        "FASTEMBED_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    monkeypatch.setattr(embeddings, "BGE_M3_ONNX_REPO", embeddings.BGE_M3_PINNED_REPO)
    monkeypatch.setattr(embeddings, "BGE_M3_ONNX_REVISION", embeddings.BGE_M3_PINNED_REVISION)
    monkeypatch.setattr(reranker, "BGE_RERANKER_ONNX_REPO", reranker.BGE_RERANKER_PINNED_REPO)
    monkeypatch.setattr(
        reranker, "BGE_RERANKER_ONNX_REVISION", reranker.BGE_RERANKER_PINNED_REVISION
    )
    monkeypatch.setattr(reranker, "QWEN3_RERANKER_MODEL", "n24q02m/Qwen3-Reranker-0.6B-ONNX")
    from power_framework.experimental import colbert_reranker

    monkeypatch.setattr(colbert_reranker, "COLBERT_DEFAULT_MODEL", "colbert-ir/colbertv2.0")


def _files(tmp_path: Path, *, mismatch: bool = False) -> tuple[dict[str, str], dict[str, str]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
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


def test_hf_acquisition_binds_the_validated_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The downloader must receive the same endpoint that policy validated."""
    paths, hashes = _files(tmp_path)
    calls: list[dict[str, object]] = []
    module = ModuleType("huggingface_hub")

    def download(_repo: str, filename: str, **kwargs: object) -> str:
        calls.append(kwargs)
        return paths[filename]

    module.hf_hub_download = download  # type: ignore[attr-defined]
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
    monkeypatch.setenv("HF_ENDPOINT", "https://huggingface.co")
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)

    result = model_policy.acquire_model_files(**_acquire_kwargs("org/model", "a" * 40, hashes))

    assert result == paths
    assert calls == [
        {
            "revision": "a" * 40,
            "local_files_only": False,
            "endpoint": "https://huggingface.co",
        },
        {
            "revision": "a" * 40,
            "local_files_only": False,
            "endpoint": "https://huggingface.co",
        },
    ]


def test_model_acquisition_cannot_be_interleaved_by_constructor_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A constructor-local environment window cannot contaminate an active download."""
    paths, hashes = _files(tmp_path)
    download_started = threading.Event()
    release_download = threading.Event()
    constructor_entered = threading.Event()
    observed_flags: list[tuple[str | None, ...]] = []
    errors: list[Exception] = []
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
    monkeypatch.setattr(model_policy, "_cached_model_files", lambda _spec: {})

    module = ModuleType("huggingface_hub")

    def download(_repo: str, filename: str, **_kwargs: object) -> str:
        download_started.set()
        if not release_download.wait(5):
            raise AssertionError("download release was not signalled")
        observed_flags.append(
            tuple(
                os.getenv(name)
                for name in ("POWER_MODEL_OFFLINE", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
            )
        )
        return paths[filename]

    module.hf_hub_download = download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)

    def acquire() -> None:
        try:
            model_policy.acquire_model_files(**_acquire_kwargs("org/model", "a" * 40, hashes))
        except Exception as exc:  # pragma: no cover - assertion below reports the failure
            errors.append(exc)

    acquisition_thread = threading.Thread(target=acquire)
    acquisition_thread.start()
    assert download_started.wait(5)

    def enter_constructor_window() -> None:
        with model_policy.force_model_offline():
            constructor_entered.set()

    constructor_thread = threading.Thread(target=enter_constructor_window)
    constructor_thread.start()
    assert not constructor_entered.wait(0.1)

    release_download.set()
    acquisition_thread.join(timeout=5)
    constructor_thread.join(timeout=5)

    assert not acquisition_thread.is_alive()
    assert not constructor_thread.is_alive()
    assert not errors
    assert observed_flags == [(None, None, None), (None, None, None)]
    assert constructor_entered.is_set()


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

    prepared.release()
    assert not staging.exists()
    prepared.close()


def test_prepare_external_model_releases_staging_when_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed hardlink and copy fallback must not leave a staging tree behind."""
    snapshot = tmp_path / "snapshot"
    paths, hashes = _files(snapshot)
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

    staging = tmp_path / "power-model-copy-failure"

    def make_staging(**_kwargs: str) -> str:
        staging.mkdir()
        return str(staging)

    def fail_link(_source: Path, _destination: Path) -> None:
        raise OSError("synthetic hardlink failure")

    def fail_copy(_source: Path, _destination: Path) -> None:
        raise OSError("synthetic copy failure")

    monkeypatch.setattr(model_policy.tempfile, "mkdtemp", make_staging)
    monkeypatch.setattr(model_policy.os, "link", fail_link)
    monkeypatch.setattr(model_policy.shutil, "copyfile", fail_copy)

    with pytest.raises(model_policy.ModelIntegrityError, match="isolated_model_snapshot_failed"):
        model_policy.prepare_external_model(
            operation=EgressOperation.EMBEDDINGS,
            provider="test-external",
            model_reference=f"{repo}@{revision}",
        )

    assert not staging.exists()


def test_prepare_external_model_preserves_staging_cleanup_failure_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A staging tamper error remains visible and retains the preparation cause."""
    paths, hashes = _files(tmp_path / "snapshot")
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

    staging = tmp_path / "power-model-tampered"

    def make_staging(**_kwargs: str) -> str:
        staging.mkdir()
        return str(staging)

    def fail_link(_source: Path, _destination: Path) -> None:
        raise OSError("synthetic preparation failure")

    def fail_copy(_source: Path, _destination: Path) -> None:
        raise OSError("synthetic copy failure")

    def fail_release(_prepared: model_policy.PreparedModel) -> None:
        raise model_policy.ModelIntegrityError("synthetic staging tamper")

    monkeypatch.setattr(model_policy.tempfile, "mkdtemp", make_staging)
    monkeypatch.setattr(model_policy.os, "link", fail_link)
    monkeypatch.setattr(model_policy.shutil, "copyfile", fail_copy)
    monkeypatch.setattr(model_policy.PreparedModel, "release", fail_release)

    with pytest.raises(
        model_policy.ModelIntegrityError, match="synthetic staging tamper"
    ) as exc_info:
        model_policy.prepare_external_model(
            operation=EgressOperation.EMBEDDINGS,
            provider="test-external",
            model_reference=f"{repo}@{revision}",
        )

    assert isinstance(exc_info.value.__cause__, OSError)
    assert str(exc_info.value.__cause__) == "synthetic copy failure"
    assert staging.exists()


def test_prepare_external_model_releases_staging_when_staged_hash_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A post-copy verification failure must release the owned staging tree."""
    snapshot = tmp_path / "snapshot"
    paths, hashes = _files(snapshot)
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

    staging = tmp_path / "power-model-hash-failure"

    def make_staging(**_kwargs: str) -> str:
        staging.mkdir()
        return str(staging)

    original_verify = model_policy.verify_model_files
    verify_calls = 0

    def fail_staged_verify(spec: model_policy.ApprovedModel, candidate: dict[str, str]):
        nonlocal verify_calls
        verify_calls += 1
        if verify_calls == 2:
            raise model_policy.ModelIntegrityError("synthetic staged hash failure")
        return original_verify(spec, candidate)

    monkeypatch.setattr(model_policy.tempfile, "mkdtemp", make_staging)
    monkeypatch.setattr(model_policy, "verify_model_files", fail_staged_verify)

    with pytest.raises(model_policy.ModelIntegrityError, match="isolated_model_snapshot_failed"):
        model_policy.prepare_external_model(
            operation=EgressOperation.EMBEDDINGS,
            provider="test-external",
            model_reference=f"{repo}@{revision}",
        )

    assert verify_calls == 2
    assert not staging.exists()


def test_constructor_local_offline_state_does_not_block_concurrent_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A delegated constructor's temporary flags cannot become another request's policy."""
    delegated_snapshot = tmp_path / "delegated-snapshot"
    delegated_paths, delegated_hashes = _files(delegated_snapshot)
    delegated_repo = "custom/delegated"
    delegated_revision = "b" * 40
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-public")
    monkeypatch.setenv(model_policy.ALLOW_CUSTOM_MODELS_ENV, "1")
    monkeypatch.setenv(
        model_policy.MODEL_APPROVAL_ENV,
        json.dumps(
            {
                "operation": "embeddings",
                "provider": "fastembed-embedding",
                "license": "MIT",
                "repo": delegated_repo,
                "revision": delegated_revision,
                "files": delegated_hashes,
            }
        ),
    )

    remote_snapshot = tmp_path / "remote-snapshot"
    remote_paths, remote_hashes = _files(remote_snapshot)
    remote_calls: list[str] = []
    monkeypatch.setattr(
        model_policy,
        "_cached_model_files",
        lambda spec: delegated_paths if spec.repo == delegated_repo else {},
    )
    monkeypatch.setitem(sys.modules, "huggingface_hub", _fake_hub(remote_calls, remote_paths))

    constructor_started = threading.Event()
    release_constructor = threading.Event()
    acquisition_started = threading.Event()
    acquisition_checked = threading.Event()
    offline_check_started = threading.Event()
    constructor_errors: list[Exception] = []
    acquisition_errors: list[Exception] = []
    acquisition_result: list[dict[str, str]] = []

    class BlockingEmbedding:
        def __init__(self, **_kwargs: object) -> None:
            constructor_started.set()
            if not release_constructor.wait(5):
                raise AssertionError("constructor release was not signalled")

    fastembed = ModuleType("fastembed")
    fastembed.TextEmbedding = BlockingEmbedding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastembed", fastembed)

    original_model_offline = model_policy.model_offline

    def observe_model_offline() -> bool:
        offline_check_started.set()
        return original_model_offline()

    monkeypatch.setattr(model_policy, "model_offline", observe_model_offline)
    manager = embeddings.FastEmbedManager(f"{delegated_repo}@{delegated_revision}")

    def construct_delegated() -> None:
        try:
            manager._lazy_init()
        except Exception as exc:  # pragma: no cover - assertion below reports the failure
            constructor_errors.append(exc)

    def acquire_remote() -> None:
        acquisition_started.set()
        try:
            acquisition_result.append(
                model_policy.acquire_model_files(
                    operation=EgressOperation.EMBEDDINGS,
                    repo="remote/model",
                    revision="a" * 40,
                    provider="bge-m3-onnx",
                    required_files=("model.onnx", "tokenizer.json"),
                    canonical_repo="remote/model",
                    canonical_revision="a" * 40,
                    canonical_provider="bge-m3-onnx",
                    canonical_license="MIT",
                    canonical_hashes=remote_hashes,
                )
            )
        except Exception as exc:  # pragma: no cover - assertion below reports the failure
            acquisition_errors.append(exc)

    constructor_thread = threading.Thread(target=construct_delegated)
    constructor_thread.start()
    assert constructor_started.wait(5)

    original_cached = model_policy._cached_model_files

    def observe_acquisition_cache(spec: model_policy.ApprovedModel) -> dict[str, str]:
        if spec.repo != delegated_repo:
            acquisition_checked.set()
        return original_cached(spec) if spec.repo == delegated_repo else {}

    monkeypatch.setattr(model_policy, "_cached_model_files", observe_acquisition_cache)
    acquisition_thread = threading.Thread(target=acquire_remote)
    acquisition_thread.start()
    assert acquisition_started.wait(5)
    assert not acquisition_errors
    assert acquisition_thread.is_alive()
    assert not acquisition_checked.is_set()
    assert not offline_check_started.is_set()

    release_constructor.set()
    constructor_thread.join(timeout=5)
    acquisition_thread.join(timeout=5)

    assert not constructor_thread.is_alive()
    assert not acquisition_thread.is_alive()
    assert not constructor_errors
    assert not acquisition_errors
    assert acquisition_result == [remote_paths]
    assert remote_calls == ["model.onnx", "tokenizer.json"]

    monkeypatch.setenv("POWER_MODEL_OFFLINE", "1")
    with pytest.raises(model_policy.ModelOfflineError, match="model_offline_cache_missing"):
        model_policy.acquire_model_files(
            operation=EgressOperation.EMBEDDINGS,
            repo="remote/model",
            revision="a" * 40,
            provider="bge-m3-onnx",
            required_files=("model.onnx", "tokenizer.json"),
            canonical_repo="remote/model",
            canonical_revision="a" * 40,
            canonical_provider="bge-m3-onnx",
            canonical_license="MIT",
            canonical_hashes=remote_hashes,
        )
    assert remote_calls == ["model.onnx", "tokenizer.json"]
    manager.close()
