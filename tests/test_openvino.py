"""Offline provider and manager contracts; these do not prove Intel GPU execution."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from power_framework.experimental import embeddings, reranker

OPENVINO = "OpenVINOExecutionProvider"
CPU = "CPUExecutionProvider"


@pytest.fixture(autouse=True)
def clean_devices(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "POWER_EMBED_DEVICE",
        "POWER_RERANKER_DEVICE",
        "POWER_EMBED_DEVICE_TYPE",
        "POWER_RERANKER_DEVICE_TYPE",
        "POWER_EMBED_DEVICE_ID",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("env_var", ["POWER_EMBED_DEVICE", "POWER_RERANKER_DEVICE"])
@pytest.mark.parametrize("mode", ["openvino", "auto"])
@pytest.mark.parametrize("device_type", [None, "GPU.0", "CPU"])
def test_openvino_options(monkeypatch, env_var, mode, device_type):
    monkeypatch.setenv(env_var, mode)
    # OpenVINO must never parse the CUDA/ROCm device ordinal.
    monkeypatch.setenv("POWER_EMBED_DEVICE_ID", "not-an-ordinal")
    if device_type is not None:
        monkeypatch.setenv("POWER_EMBED_DEVICE_TYPE", device_type)
    ort = SimpleNamespace(get_available_providers=lambda: [CPU, OPENVINO])
    assert embeddings.select_onnx_providers(ort, env_var) == [
        (OPENVINO, {"device_type": device_type or "GPU"}),
        (CPU, {"arena_extend_strategy": "kSameAsRequested"}),
    ]


def test_reranker_inherits_mode_but_can_override_device_type(monkeypatch):
    monkeypatch.setenv("POWER_EMBED_DEVICE", " OpenVINO ")
    monkeypatch.setenv("POWER_EMBED_DEVICE_TYPE", "GPU.0")
    monkeypatch.setenv("POWER_RERANKER_DEVICE_TYPE", "CPU")
    ort = SimpleNamespace(get_available_providers=lambda: [CPU, OPENVINO])
    assert embeddings.select_onnx_providers(ort)[0] == (OPENVINO, {"device_type": "GPU.0"})
    assert embeddings.select_onnx_providers(ort, "POWER_RERANKER_DEVICE")[0] == (
        OPENVINO,
        {"device_type": "CPU"},
    )


@pytest.mark.parametrize("env_var", ["POWER_EMBED_DEVICE", "POWER_RERANKER_DEVICE"])
def test_explicit_openvino_fails_closed(monkeypatch, env_var):
    monkeypatch.setenv(env_var, "openvino")
    ort = SimpleNamespace(get_available_providers=lambda: [CPU])
    with pytest.raises(RuntimeError, match=f"requested_onnx_provider_unavailable:{OPENVINO}"):
        embeddings.select_onnx_providers(ort, env_var)
    ort.get_available_providers = lambda: [CPU, OPENVINO]
    providers = embeddings.select_onnx_providers(ort, env_var)
    session = SimpleNamespace(get_providers=lambda: [CPU])
    with pytest.raises(RuntimeError, match=f"requested_onnx_provider_not_bound:{OPENVINO}"):
        embeddings.verify_bound_provider(session, providers, env_var)
    monkeypatch.setenv(env_var, "bogus")
    with pytest.raises(ValueError, match=f"invalid_{env_var.lower()}:bogus"):
        embeddings.select_onnx_providers(ort, env_var)


@pytest.mark.parametrize("preferred", ["CUDAExecutionProvider", "ROCMExecutionProvider", OPENVINO])
def test_auto_priority(monkeypatch, preferred):
    available = [CPU, "DmlExecutionProvider", OPENVINO, preferred]
    ort = SimpleNamespace(get_available_providers=lambda: available)
    assert embeddings.select_onnx_providers(ort)[0][0] == preferred


def test_openvino_case_insensitive_provider_and_empty_type(monkeypatch):
    monkeypatch.setenv("POWER_EMBED_DEVICE", "openvino")
    ort = SimpleNamespace(get_available_providers=lambda: [CPU, OPENVINO.lower()])
    providers = embeddings.select_onnx_providers(ort)
    assert providers[0] == (OPENVINO.lower(), {"device_type": "GPU"})
    session = SimpleNamespace(get_providers=lambda: [OPENVINO, CPU])
    assert embeddings.verify_bound_provider(session, providers, "POWER_EMBED_DEVICE") == OPENVINO
    monkeypatch.setenv("POWER_EMBED_DEVICE_TYPE", " ")
    with pytest.raises(ValueError, match="invalid_power_embed_device_type:empty"):
        embeddings.select_onnx_providers(ort)


@pytest.mark.parametrize("kind", ["embedding", "reranker"])
@pytest.mark.parametrize(
    ("mode", "bound", "runtime_failure"),
    [
        ("openvino", OPENVINO, False),
        ("openvino", CPU, False),
        ("openvino", OPENVINO, True),
        ("auto", OPENVINO, False),
        ("auto", CPU, False),
        ("auto", OPENVINO, True),
        ("cpu", CPU, False),
    ],
)
def test_managers_create_and_verify_openvino_session(
    monkeypatch, kind, mode, bound, runtime_failure
):
    """Exercise real lazy-init, inference, options and cleanup with runtime doubles."""
    import numpy as np

    module = embeddings if kind == "embedding" else reranker
    monkeypatch.setattr(
        module,
        "acquire_model_files",
        lambda **kwargs: {
            "model.onnx": "model.onnx",
            "onnx/model.onnx": "model.onnx",
            "tokenizer.json": "tokenizer.json",
        },
    )
    monkeypatch.setenv("POWER_EMBED_DEVICE", mode)
    monkeypatch.setenv("POWER_RERANKER_DEVICE", mode)
    monkeypatch.setenv("POWER_EMBED_NUM_THREADS", "1")
    calls = []

    class Session:
        def __init__(self, path, *, providers, sess_options):
            calls.append(providers)
            self.bound = bound
            self.fallback_enabled = True
            if mode == "cpu":
                assert providers == [(CPU, {"arena_extend_strategy": "kSameAsRequested"})]
            else:
                assert providers[0] == (OPENVINO, {"device_type": "GPU"})
            assert sess_options.enable_cpu_mem_arena is False
            assert sess_options.intra_op_num_threads >= 1
            assert sess_options.inter_op_num_threads == 1

        def get_providers(self):
            return [self.bound, CPU] if self.bound == OPENVINO else [CPU]

        def disable_fallback(self):
            self.fallback_enabled = False

        def get_inputs(self):
            return [SimpleNamespace(name="input_ids"), SimpleNamespace(name="attention_mask")]

        def run(self, outputs, inputs):
            if runtime_failure and self.bound == OPENVINO:
                if not self.fallback_enabled:
                    raise RuntimeError("synthetic EP failure")
                self.bound = CPU
            width = 1024 if kind == "embedding" else 1
            return [np.ones((len(inputs["input_ids"]), width), dtype=np.float32)]

    class Tokenizer:
        @staticmethod
        def from_file(path):
            return Tokenizer()

        def enable_truncation(self, **kwargs):
            pass

        def enable_padding(self):
            pass

        def token_to_id(self, token):
            return 0

        def encode_batch(self, texts):
            return [
                SimpleNamespace(ids=[1, 2], attention_mask=[1, 1], type_ids=[0, 0]) for _ in texts
            ]

    monkeypatch.setitem(
        sys.modules,
        "onnxruntime",
        SimpleNamespace(
            SessionOptions=SimpleNamespace,
            InferenceSession=Session,
            get_available_providers=lambda: [CPU, OPENVINO],
        ),
    )
    monkeypatch.setitem(sys.modules, "tokenizers", SimpleNamespace(Tokenizer=Tokenizer))
    manager = embeddings.BGEM3OnnxManager() if kind == "embedding" else reranker.BGEM3Reranker()
    if mode == "openvino" and (bound == CPU or runtime_failure):
        error = (
            f"requested_onnx_provider_not_bound:{OPENVINO}"
            if bound == CPU
            else "synthetic EP failure"
        )
        with pytest.raises(RuntimeError, match=error):
            manager._lazy_init()
        assert manager._session is None
        assert manager.active_provider is None
    else:
        result = manager.embed("probe") if kind == "embedding" else manager.rerank("q", ["doc"])
        assert len(result) == (1024 if kind == "embedding" else 1)
        assert manager.active_provider == (CPU if runtime_failure else bound)
    assert len(calls) == 1


@pytest.mark.parametrize("mode", ["auto", "cpu"])
def test_cpu_only_install_ignores_openvino_configuration(monkeypatch, mode):
    monkeypatch.setenv("POWER_EMBED_DEVICE", mode)
    monkeypatch.setenv("POWER_EMBED_DEVICE_TYPE", " ")
    ort = SimpleNamespace(get_available_providers=lambda: ["AzureExecutionProvider", CPU])
    assert embeddings.select_onnx_providers(ort) == [
        (CPU, {"arena_extend_strategy": "kSameAsRequested"}),
    ]
