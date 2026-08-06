"""Ground-truth loading, independence guard and query classification.

The canonical OR-vs-AND comparison may only consume qrels read from a curated,
frozen fixture that carries an explicit independence declaration. Building
qrels from a lexical rule such as ``all(term in document ...)`` is forbidden:
it is an AND-like rule and would make the comparison circular (evaluation
leakage). Every loader in this module fails closed.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from power_framework.core.searcher import FTS_STOPWORDS

if TYPE_CHECKING:
    from pathlib import Path

QUERY_LANGUAGE_RE = re.compile(r"[а-яєіїґ]", re.IGNORECASE)
_HYPHEN_RE = re.compile(r"-")
_PHRASE_RE = re.compile(r'"([^"]+)"|(\S+)')

TERM_AND_RULE_NAME = "all(query_terms in document)"


class GroundTruthIndependenceError(ValueError):
    """Raised when qrels provenance does not prove independence from retrieval."""


@dataclass(frozen=True)
class QueryRecord:
    """One frozen query with derived classification fields."""

    query_id: str
    query: str
    language: str
    stratum: str
    query_class: str
    term_count: int
    has_phrase: bool
    has_hyphen: bool


@dataclass(frozen=True)
class GroundTruth:
    """Frozen queries + graded relevance map with provenance binding."""

    queries: dict[str, QueryRecord]
    qrels: dict[str, dict[str, int]]
    provenance: dict[str, Any]
    provenance_sha256: str
    queries_sha256: str
    qrels_sha256: str


@dataclass
class EnvVarSnapshot:
    """Snapshot/restore of a single environment variable (scoped context)."""

    name: str
    previous: str | None = None
    present: bool = False

    def snapshot(self) -> EnvVarSnapshot:
        self.previous = os.environ.get(self.name)
        self.present = self.name in os.environ
        return self

    def restore(self) -> None:
        if self.present:
            assert self.previous is not None
            os.environ[self.name] = self.previous
        else:
            os.environ.pop(self.name, None)


@contextlib.contextmanager
def fts_operator_env(operator: str) -> Any:
    """Set POWER_FTS_OPERATOR inside a scoped context and restore afterwards.

    This is the ONLY sanctioned way a benchmark variant switches the FTS
    operator. It guarantees an OR run can never leak its operator into an AND
    run (and vice versa) through a stale process environment.
    """
    snapshot = EnvVarSnapshot("POWER_FTS_OPERATOR").snapshot()
    try:
        os.environ["POWER_FTS_OPERATOR"] = operator
        yield
    finally:
        snapshot.restore()


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row is not an object at {path}:{line_number}")
            rows.append(value)
    return rows


def extract_fts_terms(query: str) -> list[str]:
    """Mirror the POWER FTS term extraction for classification only.

    Phrase and hyphenated tokens are kept quoted exactly like ``_fts_search``
    does; plain tokens keep the prefix-wildcard form after stopword filtering.
    This function is used ONLY to classify queries (term counts), never to
    build relevance judgments.
    """
    clean_query = re.sub(
        r'[^\w\s"а-яєіїґ\'-]',
        " ",
        query,
        flags=re.IGNORECASE,
    )
    terms: list[str] = []
    for match in re.finditer(_PHRASE_RE, clean_query):
        phrase = match.group(1)
        word = match.group(2)
        if phrase:
            terms.append(f'"{phrase.strip()}"')
        elif word:
            token = word.strip()
            if "-" in token or token.casefold() not in FTS_STOPWORDS:
                terms.append(f'"{token}"' if "-" in token else f"{token}*")
    return terms


def classify_query(query_id: str, row: dict[str, Any]) -> QueryRecord:
    """Derive stable, deterministic query classification fields."""
    query = str(row["query"])
    stratum = str(row.get("stratum", ""))
    query_class = str(row.get("query_class", "conceptual"))
    language = "uk" if QUERY_LANGUAGE_RE.search(query) else "en"
    terms = extract_fts_terms(query)
    return QueryRecord(
        query_id=query_id,
        query=query,
        language=language,
        stratum=stratum,
        query_class=query_class,
        term_count=len(terms),
        has_phrase=any(t.startswith('"') for t in terms),
        has_hyphen=any("-" in t for t in terms),
    )


def load_queries(queries_path: Path) -> dict[str, QueryRecord]:
    """Load and validate a frozen query fixture into classified records."""
    rows = _load_jsonl(queries_path)
    records: dict[str, QueryRecord] = {}
    for row in rows:
        query_id = str(row.get("query_id", ""))
        if not query_id or not str(row.get("query", "")).strip():
            raise ValueError(f"invalid query row: {queries_path}: {row!r}")
        if query_id in records:
            raise ValueError(f"duplicate query_id {query_id!r} in {queries_path}")
        records[query_id] = classify_query(query_id, row)
    return records


def _load_provenance(provenance_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GroundTruthIndependenceError(
            f"qrels provenance cannot be read: {provenance_path}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise GroundTruthIndependenceError("qrels provenance must be a JSON object")
    return data


def assert_independent_provenance(provenance: dict[str, Any]) -> None:
    """Fail closed unless the qrels are declared independent of retrieval.

    A qrels set built from FTS output, from a lexical term-AND rule, or from
    OR/AND operator runs cannot be used as canonical evidence for an operator
    comparison (circular evaluation). Any missing or false declaration raises.
    """
    declaration = provenance.get("independence_declaration")
    if not isinstance(declaration, dict):
        raise GroundTruthIndependenceError("qrels provenance is missing independence_declaration")
    required_flags = (
        "not_derived_from_fts",
        "not_derived_from_lexical_term_and",
        "not_derived_from_or_and_operator_runs",
    )
    for flag in required_flags:
        if declaration.get(flag) is not True:
            raise GroundTruthIndependenceError(
                f"qrels provenance declares independence flag {flag!r} != true; "
                "cannot be used as canonical OR-vs-AND ground truth"
            )
    if declaration.get("human_judged") is not True and "human_judged" not in declaration:
        # Synthetic/machine-assigned qrels are still operator-independent and
        # usable as development evidence, but the caller must know they are
        # NOT human judgments. This is surfaced via the provenance, not rejected.
        raise GroundTruthIndependenceError(
            "qrels provenance must declare human_judged explicitly (true/false)"
        )


def load_qrels(qrels_path: Path, provenance_path: Path | None = None) -> dict[str, dict[str, int]]:
    """Load graded relevance judgments from a curated fixture.

    ``provenance_path`` is mandatory for canonical comparison: the guard
    rejects qrels whose provenance cannot prove independence from retrieval.
    """
    if provenance_path is None:
        raise GroundTruthIndependenceError(
            "canonical OR-vs-AND comparison requires an explicit qrels provenance file"
        )
    provenance = _load_provenance(provenance_path)
    assert_independent_provenance(provenance)
    qrels: dict[str, dict[str, int]] = {}
    for row in _load_jsonl(qrels_path):
        query_id = str(row.get("query_id", ""))
        document_id = str(row.get("document_id", ""))
        relevance = row.get("relevance")
        if not query_id or not document_id:
            raise ValueError(f"invalid qrel row: {qrels_path}: {row!r}")
        if not isinstance(relevance, int) or relevance < 0 or relevance > 3:
            raise ValueError(f"unsupported relevance grade in {qrels_path}: {row!r}")
        if row.get("distractor", False):
            # Distractors are graded 2 in the synthetic fixture by design but
            # they are NOT targets: a distractor in the top-K is a failure, not
            # a hit. The canonical comparison therefore treats them as
            # non-relevant for ranking metrics. (Recall/nDCG use only targets.)
            continue
        bucket = qrels.setdefault(query_id, {})
        if document_id in bucket:
            raise ValueError(f"duplicate qrel for {query_id}/{document_id}")
        bucket[document_id] = relevance
    return qrels


def load_ground_truth(
    queries_path: Path,
    qrels_path: Path,
    provenance_path: Path,
) -> GroundTruth:
    """Load the full frozen ground truth with provenance binding."""
    queries = load_queries(queries_path)
    qrels = load_qrels(qrels_path, provenance_path)
    query_ids = set(queries)
    qrel_ids = set(qrels)
    if qrel_ids - query_ids:
        unknown = sorted(qrel_ids - query_ids)[:10]
        raise ValueError(f"qrels reference unknown query IDs: {unknown}")
    if not qrel_ids:
        raise ValueError("qrels contain no target judgments")
    return GroundTruth(
        queries=queries,
        qrels=qrels,
        provenance=_load_provenance(provenance_path),
        provenance_sha256=_sha256_file(provenance_path),
        queries_sha256=_sha256_file(queries_path),
        qrels_sha256=_sha256_file(qrels_path),
    )


def term_and_rule_matches(terms: list[str], document_text: str) -> bool:
    """The forbidden lexical rule, kept ONLY to demonstrate its bias in tests.

    Relevance must never be derived from ``all(query_terms in document)``:
    this AND-like rule silently redefines relevance for partial matches that
    human judges would still call relevant (see the alpha/beta/gamma bias
    test). Canonical qrels must come from a curated fixture instead.
    """
    lower = document_text.lower()
    return all(term in lower for term in terms)
