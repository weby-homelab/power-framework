# Real-vault retrieval receipt

`scripts/benchmark_retrieval_latency.py` produces a content-free latency
receipt. It records query-set hash, verified index identity, execution-shape
timings, sanitized provider binding, peak RSS, optional NVIDIA device memory,
and execution errors. It never writes query text, note content, snippets, paths, or
the doctor report's vault path to the receipt.

Peak RSS is recorded per execution shape. NVIDIA telemetry is sampled only at
benchmark run start/end so `nvidia-smi` latency cannot contaminate MCP or query
timings; it is explicitly device-wide and may include unrelated processes.

The normal benchmark remains diagnostic. For the roadmap's real-vault dense
evidence gate, require both an immutable generation and an actual provider
session:

```bash
python scripts/benchmark_retrieval_latency.py \
  --vault /path/to/isolated-real-vault \
  --fixture /path/to/frozen-query-fixture \
  --modes semantic hybrid reranked \
  --rounds 5 \
  --cold-rounds 3 \
  --query-limit 10 \
  --probe-provider \
  --require-provider-binding \
  --require-immutable-generation \
  --output /tmp/power-real-vault-retrieval.json
```

The command exits non-zero if the generation is not verified immutable, the
provider probe does not create a session with an active provider, or any
execution shape records an error. `gpu_memory_used_bytes` is an optional
device-wide `nvidia-smi` reading; `null` means that the host does not expose
that telemetry and is not silently treated as zero.

This receipt is evidence infrastructure, not acceptance by itself. The
real-vault gate still requires an exact source snapshot, enough repeated
samples for p50/p95, cold/warm/process/MCP controls, resource readings, and
`content_free=true`. Synthetic fixtures and CPU feasibility runs remain
diagnostic only; they do not justify an ANN or reranker quality claim.
