"""Paired OR-vs-AND comparison, deterministic conclusion and report generation.

Everything in this module is deterministic and testable. The conclusion logic
deliberately refuses to declare a winner from a single slightly higher metric:
a global winner requires agreement across the primary retrieval metrics
(nDCG@5, Recall@10, MRR@5, zero-result rate), and AND can never be declared
preferred when it materially worsens candidate recall or the zero-result rate
(RAG candidate-retrieval policy).
"""

from __future__ import annotations

import csv
import statistics
from typing import TYPE_CHECKING, Any

from bootstrap import paired_bootstrap_ci, win_tie_counts
from metrics import metric_names

if TYPE_CHECKING:
    from pathlib import Path

PRIMARY_METRICS = ("ndcg@5", "recall@10", "mrr@5", "zero_result")
# Metrics where a HIGHER value is better.
HIGHER_IS_BETTER = {
    "ndcg@5",
    "ndcg@10",
    "recall@5",
    "recall@10",
    "mrr@5",
    "mrr@10",
    "precision@5",
    "precision@10",
    "hit_rate@5",
    "hit_rate@10",
}
# Absolute mean-delta below which a difference is treated as practically null.
PRACTICAL_DELTA = 0.02
MIN_SAMPLE_FOR_INFERENCE = 20
ZERO_RESULT_AND_BLOCK_POINTS = 0.05
CONCLUSIONS = (
    "OR preferred",
    "AND preferred",
    "no clear winner",
    "insufficient evidence",
)


def _favor_and_for_metric(metric: str, delta: float) -> int:
    """Return +1 (favors AND), -1 (favors OR) or 0 (neutral) for one metric."""
    abs_delta = abs(delta)
    if abs_delta < PRACTICAL_DELTA:
        return 0
    if metric == "zero_result":
        return 1 if delta <= -PRACTICAL_DELTA else -1
    if metric in HIGHER_IS_BETTER:
        return 1 if delta >= PRACTICAL_DELTA else -1
    return 0


def derive_conclusion(
    metrics: dict[str, dict[str, Any]],
    sample_size: int,
) -> dict[str, Any]:
    """Deterministic global conclusion from primary-metric agreement.

    Policy: a global winner needs at least 3 of 4 primary metrics to favor the
    same operator (beyond the practical delta), and AND is blocked whenever it
    worsens candidate recall or raises the zero-result rate materially.
    """
    if sample_size < MIN_SAMPLE_FOR_INFERENCE:
        return {
            "label": "insufficient evidence",
            "rationale": (
                f"sample size {sample_size} < {MIN_SAMPLE_FOR_INFERENCE}; "
                "no statistical or practical significance is claimed"
            ),
        }

    votes: dict[str, int] = {"and": 0, "or": 0, "neutral": 0}
    details: dict[str, dict[str, str | float]] = {}
    for metric in PRIMARY_METRICS:
        row = metrics[metric]
        delta = float(row["delta_and_minus_or"])
        vote = _favor_and_for_metric(metric, delta)
        vote_label = "and" if vote > 0 else "or" if vote < 0 else "neutral"
        details[metric] = {"delta": delta, "vote": vote_label}
        votes[vote_label] += 1

    zero_delta = float(metrics["zero_result"]["delta_and_minus_or"])
    recall_delta = float(metrics["recall@10"]["delta_and_minus_or"])

    if votes["and"] >= 3:
        and_blocked = zero_delta > ZERO_RESULT_AND_BLOCK_POINTS or recall_delta < 0.0
        if and_blocked:
            return {
                "label": "no clear winner",
                "rationale": (
                    f"AND leads on {votes['and']}/4 primary metrics but is blocked: "
                    f"zero-result delta {zero_delta:+.3f} or recall@10 delta {recall_delta:+.3f} "
                    "does not support an AND default for RAG candidate retrieval"
                ),
                "votes": votes,
                "details": details,
            }
        return {
            "label": "AND preferred",
            "rationale": (
                f"AND favors {votes['and']}/4 primary metrics without a recall or "
                "zero-result penalty"
            ),
            "votes": votes,
            "details": details,
        }

    if votes["or"] >= 3:
        return {
            "label": "OR preferred",
            "rationale": f"OR favors {votes['or']}/4 primary metrics",
            "votes": votes,
            "details": details,
        }

    return {
        "label": "no clear winner",
        "rationale": (
            f"primary-metric votes: AND {votes['and']}, OR {votes['or']}, "
            f"neutral {votes['neutral']}; differences are within the practical delta"
        ),
        "votes": votes,
        "details": details,
    }


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    if n % 2:
        return float(ordered[n // 2])
    return (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0


def compare_paired_rows(
    or_rows: list[dict[str, Any]],
    and_rows: list[dict[str, Any]],
    seed: int,
    n_resamples: int,
) -> dict[str, Any]:
    """Full per-metric paired comparison over matched per-query rows."""
    if len(or_rows) != len(and_rows):
        raise ValueError("OR and AND runs must contain the same queries (paired design)")
    names = metric_names()
    comparison: dict[str, Any] = {}
    or_scores_by_metric: dict[str, list[float]] = {name: [] for name in names}
    and_scores_by_metric: dict[str, list[float]] = {name: [] for name in names}
    for or_row, and_row in zip(or_rows, and_rows, strict=True):
        for name in names:
            or_scores_by_metric[name].append(float(or_row[name]))
            and_scores_by_metric[name].append(float(and_row[name]))

    for name in names:
        or_values = or_scores_by_metric[name]
        and_values = and_scores_by_metric[name]
        bootstrap = paired_bootstrap_ci(and_values, or_values, n_resamples=n_resamples, seed=seed)
        wins = win_tie_counts(and_values, or_values)
        comparison[name] = {
            "or_mean": round(statistics.fmean(or_values), 6) if or_values else 0.0,
            "and_mean": round(statistics.fmean(and_values), 6) if and_values else 0.0,
            "or_median": _median(or_values),
            "and_median": _median(and_values),
            "delta_and_minus_or": round(bootstrap["mean_delta"], 6),
            "ci95": [bootstrap["ci_lower"], bootstrap["ci_upper"]],
            "bootstrap_resamples": bootstrap["n_resamples"],
            "bootstrap_seed": bootstrap["seed"],
            "n": bootstrap["n"],
            **wins,
        }

    conclusion = derive_conclusion(comparison, len(or_rows))
    return {"metrics": comparison, "conclusion": conclusion}


def summarize_groups(
    or_rows: list[dict[str, Any]],
    and_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Per-group means for the pre-registered query classes."""

    def _group_key(row: dict[str, Any]) -> str:
        if row["query_term_count"] >= 4:
            return "long_queries"
        return "short_queries"

    {"all": list(range(len(or_rows)))}
    members: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for _index, (or_row, and_row) in enumerate(zip(or_rows, and_rows, strict=True)):
        for group_name in (
            "all",
            str(or_row["query_language"]),
            str(or_row["stratum"]),
            _group_key(or_row),
        ):
            members.setdefault(group_name, []).append((or_row, and_row))

    summary: dict[str, dict[str, Any]] = {}
    for group_name, pairs in members.items():
        if not pairs:
            continue
        metrics: dict[str, Any] = {}
        for metric in PRIMARY_METRICS:
            or_values = [float(or_row[metric]) for or_row, _ in pairs]
            and_values = [float(and_row[metric]) for _, and_row in pairs]
            bootstrap = paired_bootstrap_ci(and_values, or_values, n_resamples=1000, seed=20260801)
            metrics[metric] = {
                "or_mean": round(statistics.fmean(or_values), 6),
                "and_mean": round(statistics.fmean(and_values), 6),
                "delta_and_minus_or": round(bootstrap["mean_delta"], 6),
                "ci95": [bootstrap["ci_lower"], bootstrap["ci_upper"]],
                "n": len(pairs),
            }
        summary[group_name] = {
            "n": len(pairs),
            "metrics": metrics,
            "zero_result_or": round(
                sum(float(or_row["zero_result"]) for or_row, _ in pairs) / len(pairs), 6
            ),
            "zero_result_and": round(
                sum(float(and_row["zero_result"]) for _, and_row in pairs) / len(pairs),
                6,
            ),
        }
    return summary


def write_per_query_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        raise ValueError("no per-query rows to write")
    fieldnames = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary_csv(
    comparison: dict[str, Any],
    groups: dict[str, dict[str, Any]],
    path: Path,
) -> None:
    rows: list[dict[str, str]] = []
    for metric, values in comparison["metrics"].items():
        rows.append(
            {
                "group": "all",
                "metric": metric,
                "or_mean": str(values["or_mean"]),
                "and_mean": str(values["and_mean"]),
                "delta_and_minus_or": str(values["delta_and_minus_or"]),
                "ci95_lower": str(values["ci95"][0]),
                "ci95_upper": str(values["ci95"][1]),
                "and_wins": str(values["and_wins"]),
                "or_wins": str(values["or_wins"]),
                "ties": str(values["ties"]),
            }
        )
    for group_name, group in groups.items():
        if group_name == "all":
            continue
        for metric, values in group["metrics"].items():
            rows.append(
                {
                    "group": group_name,
                    "metric": metric,
                    "or_mean": str(values["or_mean"]),
                    "and_mean": str(values["and_mean"]),
                    "delta_and_minus_or": str(values["delta_and_minus_or"]),
                    "ci95_lower": str(values["ci95"][0]),
                    "ci95_upper": str(values["ci95"][1]),
                    "and_wins": "",
                    "or_wins": "",
                    "ties": "",
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "group",
                "metric",
                "or_mean",
                "and_mean",
                "delta_and_minus_or",
                "ci95_lower",
                "ci95_upper",
                "and_wins",
                "or_wins",
                "ties",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def build_report_markdown(
    comparison: dict[str, Any],
    groups: dict[str, dict[str, Any]],
    per_query_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    newly_lost_queries: list[dict[str, Any]],
    examples_or_wins: list[dict[str, Any]],
    examples_and_wins: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> str:
    """Human-readable report following the canonical §18 structure."""
    metrics_table = comparison["metrics"]
    lines: list[str] = []
    lines.append("# POWER FTS Operator A/B Benchmark")
    lines.append("")
    lines.append("## Purpose")
    lines.append("")
    lines.append(
        "Compare SQLite FTS5 boolean operators OR and AND on the same corpus, "
        "query set, qrels, tokenizer, BM25 weighting and index; the only "
        "independent variable is `POWER_FTS_OPERATOR`."
    )
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "Paired A/B: every query is evaluated under both operators with identical "
        "preprocessing (quoted phrases, prefix wildcards, stopword filtering, "
        "hyphenated identifier quoting), identical BM25 weights and one immutable "
        "FTS index (synced once before both variants). Environment is switched with "
        "a scoped `POWER_FTS_OPERATOR` context; provenance is recorded in "
        "`manifest.json`."
    )
    lines.append("")
    lines.append("## Ground truth provenance")
    lines.append("")
    lines.append(
        f"Qrels: `{manifest['qrels_path']}` (sha256 `{manifest['qrels_sha256'][:12]}...`). "
        f"Provenance: `{manifest['provenance_path']}` (sha256 "
        f"`{manifest['provenance_sha256'][:12]}...`). The qrels are assigned by topic "
        "membership (synthetic-generator-v1, rubric 1.0), not by FTS output, not by "
        "any lexical term-AND rule, and not by OR/AND operator runs. They are "
        "SYNTHETIC development evidence; they are not human judgments and not a "
        "production-quality certification."
    )
    lines.append("")
    lines.append("## Corpus")
    lines.append("")
    lines.append(
        f"- Snapshot: `{manifest['corpus_path']}` (hash `{manifest['corpus_snapshot_hash']}`)"
    )
    lines.append(f"- Documents: {manifest['corpus_document_count']}")
    lines.append("")
    lines.append("## Query set")
    lines.append("")
    lines.append(f"- Total queries: {manifest['query_count']}")
    for label in ("ua", "en"):
        count = sum(1 for row in per_query_rows if row["query_language"] == label)
        lines.append(f"- {label.upper()}: {count}")
    for stratum in ("ua_to_ua", "en_to_en", "ua_to_en", "en_to_ua"):
        count = sum(1 for row in per_query_rows if row["stratum"] == stratum)
        lines.append(f"- {stratum}: {count}")
    lines.append(
        f"- Multi-term (>= 2 meaningful FTS terms): "
        f"{sum(1 for row in per_query_rows if row['query_term_count'] >= 2)}"
    )
    lines.append("")
    lines.append("## Fixed variables")
    lines.append("")
    lines.append(
        "tokenizer (unicode61), query preprocessing, stopwords, BM25 weights "
        f"{manifest['bm25_weights']}, max_results={manifest['top_k']}, "
        "query expansion (deterministic local synonyms), index generation (single "
        "sync), Python/SQLite runtime. See `manifest.json`."
    )
    lines.append("")
    lines.append("## Independent variable")
    lines.append("")
    lines.append("`POWER_FTS_OPERATOR`: `OR` (variant `fts_or`) vs `AND` (variant `fts_and`).")
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append(
        "nDCG@5/10, Recall@5/10, MRR@5/10, Precision@5/10, HitRate@5/10, "
        "zero-result rate, result counts, per-query deltas, wins/ties, paired "
        "bootstrap 95% CI."
    )
    lines.append("")
    lines.append("## Overall results")
    lines.append("")
    lines.append("| Metric | OR | AND | Δ AND-OR | Winner |")
    lines.append("|--------|----:|----:|---------:|--------|")
    for metric in metric_names():
        values = metrics_table[metric]
        delta = values["delta_and_minus_or"]
        winner = "tie" if abs(delta) < 0.02 else ("AND" if delta > 0 else "OR")
        lines.append(
            f"| {metric} | {values['or_mean']:.4f} | {values['and_mean']:.4f} "
            f"| {delta:+.4f} | {winner} |"
        )
    lines.append("")
    lines.append("## Zero-result analysis")
    lines.append("")
    zero_or = metrics_table["zero_result"]
    lines.append(
        f"- OR zero-result rate: {zero_or['or_mean']:.4f} "
        f"(mean result count {metrics_table['result_count']['or_mean']:.2f}, "
        f"median {metrics_table['result_count']['or_median']:.2f})"
    )
    lines.append(
        f"- AND zero-result rate: {zero_or['and_mean']:.4f} "
        f"(mean result count {metrics_table['result_count']['and_mean']:.2f}, "
        f"median {metrics_table['result_count']['and_median']:.2f})"
    )
    lines.append(f"- Absolute zero-result difference: {zero_or['delta_and_minus_or']:+.4f}")
    lines.append("")
    lines.append(
        f"- Queries newly lost by AND (OR found relevant docs, AND returned zero): "
        f"{len(newly_lost_queries)}"
    )
    lines.extend(
        f"  - {lost['query_id']} (`{lost['query']}`) — OR relevant hits@10: "
        f"{lost['or_relevant_hits@10']}, AND: 0"
        for lost in newly_lost_queries[:10]
    )
    lines.append("")
    lines.append("## OR wins / AND wins / ties")
    lines.append("")
    lines.append("| Metric | AND wins | OR wins | Ties |")
    lines.append("|--------|---------:|--------:|-----:|")
    for metric in ("ndcg@5", "ndcg@10", "recall@5", "recall@10", "mrr@5", "mrr@10"):
        values = metrics_table[metric]
        lines.append(
            f"| {metric} | {values['and_wins']} | {values['or_wins']} | {values['ties']} |"
        )
    lines.append("")
    lines.append("## Paired bootstrap (10,000 resamples, fixed seed)")
    lines.append("")
    lines.append("| Metric | Δ AND-OR | 95% CI |")
    lines.append("|--------|---------:|--------|")
    for metric in ("ndcg@5", "recall@5", "recall@10", "mrr@5"):
        values = metrics_table[metric]
        ci = values["ci95"]
        ci_text = f"[{ci[0]:+.4f}, {ci[1]:+.4f}]" if ci[0] is not None else "insufficient sample"
        lines.append(f"| {metric} | {values['delta_and_minus_or']:+.4f} | {ci_text} |")
    lines.append("")
    lines.append("## Query-class results")
    lines.append("")
    lines.append("| Group | n | Recall@10 OR | Recall@10 AND | Δ | Zero% OR | Zero% AND |")
    lines.append("|-------|--:|-------------:|--------------:|--:|---------:|----------:|")
    for group_name, group in groups.items():
        metrics = group["metrics"]
        lines.append(
            f"| {group_name} | {group['n']} | "
            f"{metrics['recall@10']['or_mean']:.4f} | "
            f"{metrics['recall@10']['and_mean']:.4f} | "
            f"{metrics['recall@10']['delta_and_minus_or']:+.4f} | "
            f"{group['zero_result_or']:.4f} | {group['zero_result_and']:.4f} |"
        )
    lines.append("")
    lines.append("## Example queries where OR wins")
    lines.append("")
    lines.extend(
        f"- {example['query_id']} (`{example['query']}`): Recall@10 OR "
        f"{example['or_recall@10']:.2f} vs AND {example['and_recall@10']:.2f}"
        for example in examples_or_wins[:10]
    )
    lines.append("")
    lines.append("## Example queries where AND wins")
    lines.append("")
    lines.extend(
        f"- {example['query_id']} (`{example['query']}`): Recall@10 OR "
        f"{example['or_recall@10']:.2f} vs AND {example['and_recall@10']:.2f}"
        for example in examples_and_wins[:10]
    )
    lines.append("")
    lines.append("## Failure analysis")
    lines.append("")
    if failures:
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("No query-level failures.")
    lines.append("")
    lines.append("## Conclusion")
    lines.append("")
    conclusion = comparison["conclusion"]
    lines.append(f"**{conclusion['label']}** — {conclusion['rationale']}")
    lines.append("")
    lines.append("## Limitations")
    lines.append("")
    lines.append(
        "- Synthetic corpus (100 generated documents, 50 bilingual topics); "
        "relevance is rule-assigned by topic membership, not human judgments."
    )
    lines.append(
        "- The canonical human M2 qrels are private and were not used; results are "
        "development evidence only and are not a production-quality certification."
    )
    lines.append(
        "- The query set has no single-term queries (OR == AND there by construction), "
        "so the comparison concentrates on multi-term behavior."
    )
    lines.append(
        f"- Commit: {manifest['git_commit']}; POWER {manifest['power_version']}; "
        f"Python {manifest['python_version']}; SQLite {manifest['sqlite_version']}"
    )
    lines.append("")
    return "\n".join(lines)
