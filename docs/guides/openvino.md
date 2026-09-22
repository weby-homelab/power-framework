# Intel iGPU with OpenVINO

The canonical BGE-M3 embedder and BGE reranker share OpenVINO provider selection.
This enables Intel GPU execution when the runtime, drivers and container device
permissions support it. It does not establish a speedup or a memory bound.

## Installation

Use a separate environment and a Python version for which an
`onnxruntime-openvino` wheel exists on your platform. POWER supports Python 3.13–3.14;
check wheel availability before replacing a working environment. On Linux/LXC,
the operator must expose `/dev/dri` and install compatible Intel GPU drivers.
See the [official OpenVINO EP requirements and options](https://onnxruntime.ai/docs/execution-providers/OpenVINO-ExecutionProvider.html).

Example from a source checkout in a new environment:

```bash
python3.13 -m venv .venv-openvino
. .venv-openvino/bin/activate
python -m pip install . tokenizers 'huggingface-hub>=1.30.0,<1.31.0' 'numpy>=1.24.0,<2.5' onnxruntime-openvino
python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

Install exactly one ORT distribution: `onnxruntime-openvino` replaces stock
`onnxruntime`, `onnxruntime-gpu`, or `onnxruntime-directml`; these packages share
the `onnxruntime` import namespace. Do not combine them in one environment.
The `semantic`, `rerank`, and `gpu` extras install other ORT distributions;
do not add those extras to this environment or run a sync that restores them.
The direct BGE reranker does not require FastEmbed.

## Configuration

| Variable | Meaning |
| --- | --- |
| `POWER_EMBED_DEVICE=openvino` | Require OpenVINO for embeddings. |
| `POWER_RERANKER_DEVICE=openvino` | Require OpenVINO for reranking; unset inherits embedding mode. |
| `POWER_EMBED_DEVICE_TYPE=GPU` | OpenVINO target; defaults to `GPU`. `GPU.0`, `GPU.1`, or an intentional `CPU` target can be supplied. |
| `POWER_RERANKER_DEVICE_TYPE` | Override OpenVINO target for reranking; unset inherits embedding type. |

Empty device types fail validation. Other target strings are passed to OpenVINO
for validation. `POWER_EMBED_DEVICE_ID` does not affect OpenVINO.
`auto` selects CUDA → ROCm → OpenVINO → DirectML → CPU and permits fallback.
Explicit `openvino` fails with `requested_onnx_provider_unavailable` when the EP
is absent, or `requested_onnx_provider_not_bound` if session creation falls back
to another EP. `device_type=CPU` still binds the OpenVINO EP intentionally.
Provider binding proves which EP loaded; it does not prove every graph node ran
on the GPU, since unsupported nodes may execute through the CPU fallback EP.

For explicit modes POWER disables ORT's session-level retry on inference failure;
`auto` keeps that retry enabled. After successful inference `active_provider`
reflects the current session binding, including a CPU fallback during inference.
This does not disable per-node CPU execution for unsupported accelerator operators.

Detect support in the actual Python environment, not from the CPU brand or OS
alone: inspect `platform.platform()`, `platform.machine()`, `onnxruntime.__version__`
and `onnxruntime.get_available_providers()`. A compiled EP still needs a real
model probe: driver, `/dev/dri` permissions and model compatibility can prevent
binding. With a CPU-only ORT build, both `auto` and `cpu` retain the CPU path;
an OpenVINO target variable alone does not enable an absent EP.

POWER retains `enable_cpu_mem_arena=False`, bounded `intra_op_num_threads`,
and `inter_op_num_threads=1` on both sessions. OpenVINO receives `device_type`
only, without CUDA/ROCm arena or device ordinal options. Hardware compatibility
with those session settings must be verified by the probes below.

## Cache-only acceptance

Use previously verified, complete local model snapshots. These commands deny
downloads and do not rebuild or mutate the vault:

```bash
export POWER_EGRESS_POLICY=deny POWER_MODEL_OFFLINE=1
export POWER_EMBED_DEVICE=openvino POWER_RERANKER_DEVICE=openvino
export POWER_EMBED_DEVICE_TYPE=GPU
power doctor /path/to/vault --probe-provider --json
python - <<'PY'
import math
from power_framework.core.embeddings import BGEM3OnnxManager
from power_framework.core.reranker import BGEM3Reranker

embedder = BGEM3OnnxManager()
vector = embedder.embed('Перевірка Intel GPU')
assert embedder.active_provider == 'OpenVINOExecutionProvider'
assert len(vector) == 1024 and all(math.isfinite(x) for x in vector)
reranker = BGEM3Reranker()
scores = reranker.rerank('Intel GPU', ['Intel graphics acceleration'])
assert reranker.active_provider == 'OpenVINOExecutionProvider'
assert len(scores) == 1 and all(math.isfinite(x) for x in scores)
print(embedder.active_provider, len(vector), reranker.active_provider, scores)
PY
```

Doctor needs `--probe-provider`: discovery alone does not bind a model session.
Check `embedding.bound_provider` in its JSON. A missing cached model is a separate
failure from a missing or unusable EP.

For issue #471, a full-sync benchmark remains an operator-approved live gate.
On a fixed vault snapshot record duration, peak RSS, swap, indexed note/chunk
counts, exclusions and semantic retrieval without fallback. Compare against a
CPU run of the same snapshot and settings: target duration <8.5 hours and RAM
<7000 MB. The issue's historical 3624-note coverage target applies only to that
snapshot; do not assert it for a vault whose contents have changed. Offline
mock tests cannot establish this hardware or performance acceptance.
