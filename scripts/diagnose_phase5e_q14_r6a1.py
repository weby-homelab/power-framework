#!/usr/bin/env python3
"""Forensic q14 trace for the exposed v1.4 corpus only.

This diagnostic is not an admission runner.  It reads one historical v1.4
query/GT row, builds the production-faithful synthetic fixture through the
existing services, and records bounded traces from test wrappers.  It never
reads or executes v1.5 and never modifies production observability.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
_SCRIPTS_DIR = Path(__file__).resolve().parent

for _path in (_SRC_DIR, _SCRIPTS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from benchmark_phase5e_r6 import setup_production_fixtures  # noqa: E402
from benchmark_phase5e_shadow import _sha256_file, setup_benchmark_vault  # noqa: E402
from phase5e_concept_mapping_r6 import build_alias_to_concept, load_manifest  # noqa: E402

from power_framework.core.application import ApplicationService, RequestContext  # noqa: E402
from power_framework.core.context_contracts import canonical_sha256  # noqa: E402
from power_framework.core.decision_service import DecisionService  # noqa: E402
from power_framework.core.evaluation_contracts import load_bounded_json  # noqa: E402
from power_framework.core.principal import Principal  # noqa: E402
from power_framework.core.retrieval_planner import (  # noqa: E402
    _canonical_eligibility,
    _meaningful_tokens,
)
from power_framework.core.searcher import search_vault  # noqa: E402
from power_framework.core.state_service import ProjectStateService  # noqa: E402
from power_framework.core.task_service import TaskService  # noqa: E402


def _read_jsonl_row(path: Path, query_id: str) -> dict[str, Any]:
    from power_framework.core.utils import read_file_bytes_no_follow

    data = read_file_bytes_no_follow(path, max_bytes=4 * 1024 * 1024)
    for raw_line in data.splitlines():
        if not raw_line.strip():
            continue
        row = json.loads(raw_line.decode("utf-8"))
        if row.get("query_id") == query_id:
            return row
    raise ValueError(f"historical row {query_id} not found")


class DecisionTrace:
    def __init__(self, service: DecisionService) -> None:
        self.service = service
        self.list_calls = 0
        self.records: list[dict[str, Any]] = []

    def list_decisions(self, **kwargs: Any) -> list[Any]:
        self.list_calls += 1
        records = self.service.list_decisions(**kwargs)
        self.records = [
            {
                "decision_id": str(getattr(record, "decision_id", "")),
                "status": str(getattr(record, "status", "")),
                "title": str(getattr(record, "title", "")),
                "description": str(getattr(record, "description", "")),
                "task_id": str(getattr(record, "task_id", "")),
            }
            for record in records
        ]
        return records

    def __getattr__(self, name: str) -> Any:
        return getattr(self.service, name)


def diagnose(*, corpus: Path, manifest_path: Path, query_id: str) -> dict[str, Any]:
    corpus_manifest = load_bounded_json(corpus / "manifest.json")
    if (
        not isinstance(corpus_manifest, dict)
        or corpus_manifest.get("evaluation_revision") != "v1.4"
    ):
        raise ValueError("q14 diagnostic accepts the historical v1.4 corpus only")
    query_row = _read_jsonl_row(corpus / "queries.holdout.jsonl", query_id)
    gt_row = _read_jsonl_row(corpus / "ground_truth.holdout.jsonl", query_id)
    manifest = load_manifest(manifest_path)
    alias_lookup = build_alias_to_concept(manifest)
    search_calls: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="power-r6a1-q14-") as temp_dir:
        vault = Path(temp_dir) / "vault"
        setup_benchmark_vault(vault, corpus)
        receipts = setup_production_fixtures(vault, manifest)
        task_service = TaskService(vault)
        decision_service = DecisionService(vault, task_service=task_service)
        decision_trace = DecisionTrace(decision_service)
        project_state_service = ProjectStateService(
            vault,
            task_service=task_service,
            decision_service=decision_service,
        )

        app_for_sync = ApplicationService(
            vault,
            task_service=task_service,
            decision_service=decision_service,
            project_state_service=project_state_service,
        )
        sync_context = RequestContext(principal=Principal.local_cli(), authority="apply")
        sync_result = app_for_sync.sync_vault(
            fts_only=True,
            allow_partial=True,
            context=sync_context,
        )
        if sync_result.status != "ok":
            raise RuntimeError(
                f"historical q14 diagnostic sync failed: {sync_result.degraded_reason}"
            )

        def search_trace(vault_dir: Path, query: str, **kwargs: Any) -> list[Any]:
            mode = str(kwargs.get("mode", "auto"))
            results = search_vault(
                vault_dir,
                query,
                allow_search_db_override=False,
                **kwargs,
            )
            search_calls.append(
                {
                    "mode": mode,
                    "query": query,
                    "result_count": len(results),
                    "source_ids": [str(getattr(result, "rel_path", "")) for result in results],
                }
            )
            return results

        app = ApplicationService(
            vault,
            search_fn=search_trace,
            task_service=task_service,
            decision_service=decision_trace,
            project_state_service=project_state_service,
        )
        output = app.compile_context(
            query=str(query_row["query"]),
            intent=str(query_row["intent"]),
            budget_class="FAST",
        )
        items = output.data.get("items", [])
        decision_eligibility = []
        for record in decision_trace.records:
            match_text = (
                f"{record['decision_id']} {record['title']} "
                f"{record['description']} {record['status']}"
            )
            eligibility = _canonical_eligibility(
                str(query_row["query"]), record["decision_id"], match_text
            )
            decision_eligibility.append(
                {
                    "decision_id": record["decision_id"],
                    "status": record["status"],
                    "matched_tokens": list(eligibility.matched),
                    "strength": (
                        "strong"
                        if eligibility.eligible_strong
                        else "weak"
                        if eligibility.eligible_weak
                        else "none"
                    ),
                    "admitted": any(
                        str(item.get("source_id", "")) == f"decision:{record['decision_id']}"
                        for item in items
                    ),
                }
            )
        fts_calls = [call for call in search_calls if call["mode"] == "fts"]
        final_ids = [str(item.get("source_id", "")) for item in items]
        expected_winner = gt_row.get("expected_authority_winner")
        expected_concept = (
            alias_lookup.get(str(expected_winner)) if expected_winner is not None else None
        )
        normalized_final = [alias_lookup.get(item, item) for item in final_ids]
        canonical_admitted = bool(expected_concept and expected_concept in normalized_final)
        canonical_pending = any(record["status"] == "pending" for record in decision_trace.records)
        fast_capability_mismatch = "резолюція" in str(query_row["query"]).casefold() and not any(
            "резолюц" in record["description"].casefold() for record in decision_trace.records
        )
        evaluation_semantics_defect = canonical_pending and any(
            marker in str(query_row["query"]).casefold()
            for marker in ("остаточно", "затвердж", "final", "approved")
        )
        return {
            "schema_version": "power.phase5e-q14-diagnostic.r6a1.v1",
            "historical_revision": "v1.4",
            "query_id": query_id,
            "query_intent": query_row["intent"],
            "query_meaningful_tokens": sorted(_meaningful_tokens(str(query_row["query"]))),
            "decision_service": {
                "consulted": decision_trace.list_calls > 0,
                "list_calls": decision_trace.list_calls,
                "records": decision_trace.records,
            },
            "decision_canonical_eligibility": decision_eligibility,
            "fts": fts_calls,
            "packing": {
                "item_count": len(items),
                "source_ids": final_ids,
                "canonical_admitted": canonical_admitted,
                "normalized_concepts": normalized_final,
            },
            "capability_assessment": {
                "fast_cross_language_paraphrase_guaranteed": False,
                "fast_capability_mismatch": fast_capability_mismatch,
            },
            "source_semantics": {
                "decision_status": [record["status"] for record in decision_trace.records],
                "terminal_status_proven": False,
                "evaluation_semantics_defect": evaluation_semantics_defect,
            },
            "root_disposition": "MIXED"
            if fast_capability_mismatch and evaluation_semantics_defect
            else "FAST_CAPABILITY_MISMATCH_ONLY"
            if fast_capability_mismatch
            else "EVALUATION_SEMANTICS_DEFECT_ONLY"
            if evaluation_semantics_defect
            else "NO_PRODUCTION_RUNTIME_DEFECT_PROVEN",
            "production_runtime_defect_proven": False,
            "final_output": output.data,
            "fixture_receipts": receipts,
            "runtime": {
                "runner": "diagnose_phase5e_q14_r6a1",
                "corpus_manifest_digest": canonical_sha256(corpus_manifest),
                "manifest_sha256": _sha256_file(manifest_path),
                "production_runtime_changed": False,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--fixture-manifest", type=Path, required=True)
    parser.add_argument("--query-id", default="p38-ho-q14")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(
        corpus=args.corpus.resolve(),
        manifest_path=args.fixture_manifest.resolve(),
        query_id=args.query_id,
    )
    args.output.resolve().write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"q14 diagnostic written to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
