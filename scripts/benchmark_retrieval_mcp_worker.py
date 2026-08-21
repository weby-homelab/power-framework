#!/usr/bin/env python3
"""Benchmark-only MCP worker that attaches a content-free timing receipt."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from time import perf_counter

from power_framework.core import application
from power_framework.core.benchmark_resources import resource_snapshot
from power_framework.core.timing import collect_timings
from power_framework.mcp import power_server

_original_search = power_server.search_vault
_original_format = application.format_untrusted_search_envelope
_last_receipt = None


def _timed_search(*args: object, **kwargs: object):
    global _last_receipt
    with collect_timings() as receipt:
        results = _original_search(*args, **kwargs)
    _last_receipt = receipt
    return results


def _format_with_receipt(*args: object, **kwargs: object) -> str:
    if _last_receipt is None:
        raise RuntimeError("timing receipt was not produced by search")
    started = perf_counter()
    serialized = _original_format(*args, **kwargs)
    _last_receipt.add("mcp_result_materialization", (perf_counter() - started) * 1000)
    payload = json.loads(serialized)
    timing_payload = _last_receipt.as_dict()
    payload["timings_ms"] = timing_payload["components_ms"]
    timing_payload["resources"] = resource_snapshot(include_gpu=False)
    Path(os.environ["POWER_BENCHMARK_RECEIPT"]).write_text(
        json.dumps(timing_payload, sort_keys=True), encoding="utf-8"
    )
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


power_server.search_vault = _timed_search
application.format_untrusted_search_envelope = _format_with_receipt


if __name__ == "__main__":
    # Keep the official SDK v2 stdio channel free of benchmark chatter; the
    # content-free receipt is written to the explicit side-channel path.
    sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    power_server.run()
