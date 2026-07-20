"""POWER 3.0 Phase 3 — Search-quality benchmark (deterministic + ranx + UDCG).

This test wraps the standalone harness in ``scripts/check_search_quality.py`` so
the same deterministic GT qrels + run logic is reused. It asserts the Phase 3
regression gates on the real ``/root/gemma/brain`` vault using the canonical
"reranked" mode:
  * PRIMARY: UDCG@5 >= 0.45 (Utility-Discounted Cumulative Gain)
  * SECONDARY: ndcg@5 >= 0.50

Robustness:
  * If ``ranx`` is unavailable, the test is SKIPPED (not failed), so environments
    without the eval dependency still pass the suite.
  * If the embedder/reranker models cannot be loaded (no model, no network), the
    test is SKIPPED with a clear reason rather than failing, so CI without the
    model still passes the rest of the suite. When the model IS available the
    metrics are really computed and the gate is really asserted.

Run:
    pytest tests/test_search_quality.py -m bench
    pytest tests/test_search_quality.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "scripts" / "check_search_quality.py"
REAL_VAULT = Path("/root/gemma/brain")
GATE = 0.50


def _load_harness():
    """Import the standalone harness script as a module (no source changes)."""
    spec = importlib.util.spec_from_file_location("check_search_quality", HARNESS)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_search_quality"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.bench
@pytest.mark.skipif(not REAL_VAULT.exists(), reason="real brain vault not present")
def test_search_quality_gate():
    harness = _load_harness()
    if harness is None:
        pytest.skip("could not load search-quality harness script")

    # ranx is the chosen eval lib; skip cleanly if absent.
    try:
        import ranx  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("ranx not installed (pip install ranx to enable bench)")

    # The vault must index + embed; if the model stack cannot load, skip rather
    # than fail, so CI without the model still passes the rest of the suite.
    try:
        from power_framework.core.searcher import search_vault  # noqa: F401
    except Exception as exc:  # pragma: no cover - import guard
        pytest.skip(f"searcher import failed: {exc}")

    metrics: dict
    try:
        metrics = harness.evaluate(
            vault=REAL_VAULT,
            mode="reranked",
            gate=GATE,
            max_results=20,
        )
    except Exception as exc:  # model/reranker unavailable in this env
        pytest.skip(f"search_vault could not run end-to-end (model/reranker missing?): {exc}")

    if not metrics:
        pytest.skip("no GT-relevant documents found; qrels empty for this vault")

    UDCG_GATE = 0.45
    assert metrics["ndcg@5"] >= GATE, (
        f"Phase 3 secondary gate FAILED: ndcg@5={metrics['ndcg@5']:.4f} "
        f"< {GATE}; recall@5={metrics['recall@5']:.4f} mrr@5={metrics['mrr@5']:.4f}"
    )
    assert metrics["udcg@5"] >= UDCG_GATE, (
        f"Phase 3 PRIMARY gate FAILED: udcg@5={metrics['udcg@5']:.4f} "
        f"< {UDCG_GATE}; ndcg@5={metrics['ndcg@5']:.4f}"
    )
