"""Validate POWER 3.1 frozen benchmark dataset integrity (E1 methodology).

Checks:
  - 200 base answerable queries, exactly 50/stratum
  - 20 no-answer queries (5 absent topics × 4 strata)
  - 8 QDD* distractor queries with primary + distractor doc
  - Atomic answers are literal substrings of primary documents
  - Absent topic tokens not present in corpus
  - Sparse qrels: no zero-relevance entries; no-answer queries absent from qrels
  - All document IDs reference existing corpus files
  - Hash consistency (byte-identical regeneration)
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

BENCHMARK_ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_V1 = BENCHMARK_ROOT / "dataset" / "v1"
CORPUS_DIR = DATASET_V1 / "corpus"
QUERIES_FILE = DATASET_V1 / "queries.jsonl"
QRELS_FILE = DATASET_V1 / "qrels.synthetic.jsonl"
ANSWERS_FILE = DATASET_V1 / "expected-answers.jsonl"
MANIFEST_FILE = DATASET_V1 / "corpus-manifest.json"
GUIDELINES_FILE = DATASET_V1 / "annotation-guidelines.md"

STRATA = {"ua_to_ua", "en_to_en", "ua_to_en", "en_to_ua"}
BASE_ANSWERABLE_PER_STRATUM = 50
N_ABSENT = 5
N_DISTRACTOR = 8

# Absent tokens that MUST NOT appear in corpus
ABSENT_TOKENS = {"TensorFlow", "S3", "React", "RabbitMQ", "Elasticsearch"}

QID_BASE_PATTERN = re.compile(r"^Q[UuEe][UuEe]\d{4}$")
QID_NOANSWER_PATTERN = re.compile(r"^QN[UuEe][UuEe]\d{4}$")
QID_DISTRACTOR_PATTERN = re.compile(r"^QDD\d{4}$")


class ValidationError(Exception):
    """Benchmark validation failure."""


def load_jsonl(path: Path) -> list[dict]:
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def check(condition: bool, message: str):
    if not condition:
        raise ValidationError(message)


def validate_queries(queries: list[dict]) -> None:
    qids: set[str] = set()
    base_per_stratum: dict[str, int] = dict.fromkeys(STRATA, 0)
    no_answer_per_stratum: dict[str, int] = dict.fromkeys(STRATA, 0)
    distractor_qids: set[str] = set()

    for q in queries:
        qid = q["query_id"]

        # Validate ID format
        is_base = bool(QID_BASE_PATTERN.match(qid))
        is_na = bool(QID_NOANSWER_PATTERN.match(qid))
        is_qdd = bool(QID_DISTRACTOR_PATTERN.match(qid))
        check(is_base or is_na or is_qdd, f"Invalid query_id format: {qid}")

        check(qid not in qids, f"Duplicate query_id: {qid}")
        qids.add(qid)

        check(q["stratum"] in STRATA, f"Invalid stratum {q['stratum']} in {qid}")
        check(q["language"] in ("uk", "en"), f"Invalid language in {qid}")
        check(q["target_language"] in ("uk", "en"), f"Invalid target_language in {qid}")

        lang_stratum = {
            ("uk", "uk"): "ua_to_ua",
            ("en", "en"): "en_to_en",
            ("uk", "en"): "ua_to_en",
            ("en", "uk"): "en_to_ua",
        }
        expected = lang_stratum.get((q["language"], q["target_language"]))
        check(expected == q["stratum"], f"Language/stratum mismatch in {qid}")

        if is_na:
            check(
                q["query_class"] == "no_answer",
                f"{qid} has no_answer pattern but class={q['query_class']}",
            )
            no_answer_per_stratum[q["stratum"]] += 1
        elif is_qdd:
            check(q["query_class"] != "no_answer", f"QDD query {qid} cannot be no_answer")
            distractor_qids.add(qid)
        else:
            check(
                q["query_class"] != "no_answer",
                f"{qid} has base pattern but is no_answer",
            )
            base_per_stratum[q["stratum"]] += 1

    # Exactly 50 base answerable per stratum
    for s in STRATA:
        check(
            base_per_stratum[s] == BASE_ANSWERABLE_PER_STRATUM,
            f"Stratum {s}: {base_per_stratum[s]} base answerable (need {BASE_ANSWERABLE_PER_STRATUM})",
        )

    # 20 no-answer = 5 absent × 4 strata
    for s in STRATA:
        check(
            no_answer_per_stratum[s] == N_ABSENT,
            f"Stratum {s}: {no_answer_per_stratum[s]} no-answer (need {N_ABSENT})",
        )

    # Exactly 8 QDD queries
    check(
        len(distractor_qids) == N_DISTRACTOR,
        f"Expected {N_DISTRACTOR} QDD queries, got {len(distractor_qids)}",
    )

    total_expected = 200 + (N_ABSENT * 4) + N_DISTRACTOR  # 228
    check(
        len(queries) == total_expected,
        f"Total queries {len(queries)} != {total_expected}",
    )


def validate_qrels(qrels: list[dict], query_ids: set[str], doc_ids: set[str]) -> None:
    pairs: set[tuple[str, str]] = set()
    no_answer_qids = {qid for qid in query_ids if qid.startswith("QN")}

    # No qrels entries for no-answer queries
    for qr in qrels:
        check(
            qr["query_id"] not in no_answer_qids,
            f"No-answer {qr['query_id']} has qrels entry",
        )

    for qr in qrels:
        qid = qr["query_id"]
        did = qr["document_id"]

        check(qid in query_ids, f"Qrels references unknown query_id: {qid}")
        check(did in doc_ids, f"Qrels references unknown document_id: {did}")

        pair = (qid, did)
        check(pair not in pairs, f"Duplicate qrels pair: {qid}/{did}")
        pairs.add(pair)

        check(
            0 <= qr["relevance"] <= 2,
            f"Invalid relevance {qr['relevance']} for {qid}/{did}",
        )
        check(-1.0 <= qr["utility"] <= 1.0, f"Invalid utility for {qid}/{did}")

        # Sparse: no zero-relevance entries
        check(qr["relevance"] > 0, f"Sparse violation: zero relevance for {qid}/{did}")

        if qr.get("distractor", False):
            check(
                qr["utility"] < 0,
                f"Distractor {qid}/{did} should have negative utility",
            )
            check(
                qr["relevance"] >= 2,
                f"Distractor {qid}/{did} should have relevance >= 2",
            )
        else:
            check(qr["utility"] >= 0, f"Non-distractor {qid}/{did} has negative utility")

    # Every base answerable query must have primary qrel
    for qid in query_ids:
        if qid.startswith("QN"):
            continue
        qid_qrels = [qr for qr in qrels if qr["query_id"] == qid]
        primaries = [
            qr for qr in qid_qrels if qr["relevance"] >= 2 and not qr.get("distractor", False)
        ]
        check(
            len(primaries) >= 1,
            f"Answerable {qid} has no primary (relevance>=2, non-distractor) qrel",
        )


def validate_corpus_manifest(manifest: dict) -> set[str]:
    doc_ids: set[str] = set()
    for entry in manifest["corpus"]["files"]:
        did = entry["document_id"]
        check(did not in doc_ids, f"Duplicate corpus document_id: {did}")
        doc_ids.add(did)

        file_path = CORPUS_DIR / did
        check(file_path.exists(), f"Corpus file missing: {did}")

        actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        check(actual_hash == entry["sha256"], f"SHA256 mismatch for {did}")

        # Language from doc_id suffix
        lang = "uk" if did.endswith("-ua.md") else "en"
        check(
            entry["language"] == lang,
            f"Language mismatch for {did}: manifest={entry['language']} expected={lang}",
        )

    return doc_ids


def validate_content_support(
    qrels: list[dict], answers: list[dict], corpus: dict[str, str]
) -> None:
    """Check atomic facts are substrings of primary documents."""
    for a in answers:
        if a["no_answer"]:
            continue
        qid = a["query_id"]
        primary_docs = [
            qr["document_id"]
            for qr in qrels
            if qr["query_id"] == qid and qr["relevance"] >= 2 and not qr.get("distractor", False)
        ]
        check(len(primary_docs) >= 1, f"{qid}: no primary document")
        for doc_id in primary_docs:
            content = corpus.get(doc_id, "")
            check(content, f"{qid}: primary doc {doc_id} not in corpus")
            for fact in a.get("atomic_facts", []):
                check(
                    fact.lower() in content.lower(),
                    f"{qid}: atomic fact not found in {doc_id}: {fact[:80]}",
                )


def validate_absent_topics(queries: list[dict], corpus: dict[str, str]) -> None:
    """Check absent topic tokens don't appear in corpus."""
    for q in queries:
        if q["query_class"] != "no_answer":
            continue
        q_lower = q["query"].lower()
        # Verify query mentions absent concepts not in corpus
        absent_found = any(token.lower() in q_lower for token in ABSENT_TOKENS)
        check(
            absent_found,
            f"No-answer query {q['query_id']} doesn't reference absent topic",
        )


def validate_empty_corpus_absent_tokens(corpus: dict[str, str]) -> None:
    """Ensure corpus contains none of the absent tokens."""
    all_text = " ".join(corpus.values()).lower()
    for token in ABSENT_TOKENS:
        check(
            token.lower() not in all_text,
            f"Absent token '{token}' found in corpus",
        )


def validate_qdd_queries(qrels: list[dict], query_ids: set[str]) -> None:
    """Every QDD query must have exactly 1 primary + 1 distractor."""
    qdd_qids = {qid for qid in query_ids if qid.startswith("QDD")}
    for qid in qdd_qids:
        qid_qrels = [qr for qr in qrels if qr["query_id"] == qid]
        primaries = [qr for qr in qid_qrels if not qr.get("distractor", False)]
        distractors = [qr for qr in qid_qrels if qr.get("distractor", False)]
        check(len(primaries) >= 1, f"{qid}: no primary qrel")
        check(len(distractors) >= 1, f"{qid}: no distractor qrel")
        for p in primaries:
            check(p["relevance"] >= 2, f"{qid}: primary relevance < 2")
        for d in distractors:
            check(d["relevance"] >= 2, f"{qid}: distractor relevance < 2")
            check(d["utility"] < 0, f"{qid}: distractor should have negative utility")


def validate_hash_consistency(
    queries: list[dict], qrels: list[dict], answers: list[dict], manifest: dict
) -> None:
    queries_hash = hashlib.sha256(
        json.dumps(queries, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    check(
        queries_hash == manifest["queries"]["hash_sha256"],
        "Queries hash mismatch",
    )

    qrels_hash = hashlib.sha256(
        json.dumps(qrels, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    check(
        qrels_hash == manifest["qrels"]["hash_sha256"],
        "Qrels hash mismatch",
    )

    answers_hash = hashlib.sha256(
        json.dumps(answers, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    check(
        answers_hash == manifest["expected_answers"]["hash_sha256"],
        "Answers hash mismatch",
    )

    corpus_text = json.dumps(manifest["corpus"]["files"], sort_keys=True)
    corpus_hash = hashlib.sha256(corpus_text.encode()).hexdigest()
    check(corpus_hash == manifest["corpus"]["hash_sha256"], "Corpus hash mismatch")


def validate_expected_answers(answers: list[dict], query_ids: set[str], doc_ids: set[str]) -> None:
    for a in answers:
        qid = a["query_id"]
        check(qid in query_ids, f"Answer references unknown query_id: {qid}")
        check(isinstance(a["no_answer"], bool), f"no_answer must be bool in {qid}")

        if a["no_answer"]:
            check(len(a["citation_document_ids"]) == 0, f"No-answer {qid} has citations")
        else:
            check(
                len(a.get("atomic_facts", [])) >= 1,
                f"Answerable {qid} has no atomic_facts",
            )
            check(
                len(a.get("citation_document_ids", [])) >= 1,
                f"Answerable {qid} has no citations",
            )

        for cid in a.get("citation_document_ids", []):
            check(cid in doc_ids, f"Answer {qid} cites unknown doc: {cid}")


def validate_scope_disclaimer(manifest: dict) -> None:
    limitations = manifest.get("scope_and_limitations", [])
    combined = " ".join(limitations).lower()
    check("synthetic" in combined, "Missing SYNTHETIC disclaimer")
    check("not human" in combined, "Missing 'not human annotation' disclaimer")


def validate_required_files() -> None:
    required = [
        QUERIES_FILE,
        QRELS_FILE,
        ANSWERS_FILE,
        MANIFEST_FILE,
        GUIDELINES_FILE,
    ]
    for f in required:
        check(f.exists(), f"Required file missing: {f.name}")


def main() -> int:
    errors: list[str] = []

    def run_check(name: str, fn, *args, **kwargs) -> None:
        nonlocal errors
        try:
            fn(*args, **kwargs)
            print(f"  [PASS] {name}")
        except ValidationError as e:
            errors.append(str(e))
            print(f"  [FAIL] {name}: {e}")

    print("POWER 3.1 Dataset Validator (E1)\n")

    run_check("Required files", validate_required_files)

    try:
        manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        print("  [PASS] Manifest loaded")
    except Exception as e:
        print(f"  [FAIL] Manifest load: {e}")
        return 1

    run_check("Scope disclaimer", validate_scope_disclaimer, manifest)

    try:
        queries = load_jsonl(QUERIES_FILE)
        print(f"  [PASS] Loaded {len(queries)} queries")
    except Exception as e:
        print(f"  [FAIL] Queries load: {e}")
        return 1

    try:
        qrels = load_jsonl(QRELS_FILE)
        print(f"  [PASS] Loaded {len(qrels)} qrels")
    except Exception as e:
        print(f"  [FAIL] Qrels load: {e}")
        return 1

    try:
        answers = load_jsonl(ANSWERS_FILE)
        print(f"  [PASS] Loaded {len(answers)} expected answers")
    except Exception as e:
        print(f"  [FAIL] Answers load: {e}")
        return 1

    try:
        corpus = {f.name: f.read_text(encoding="utf-8") for f in CORPUS_DIR.glob("*.md")}
        print(f"  [PASS] Loaded {len(corpus)} corpus documents")
    except Exception as e:
        errors.append(f"Corpus load: {e}")
        return 1

    run_check("Query validation", validate_queries, queries)
    run_check("Corpus manifest", validate_corpus_manifest, manifest)

    doc_ids = {e["document_id"] for e in manifest["corpus"]["files"]}
    query_ids = {q["query_id"] for q in queries}

    run_check("Qrels validation", validate_qrels, qrels, query_ids, doc_ids)
    run_check("Expected answers", validate_expected_answers, answers, query_ids, doc_ids)
    run_check("Content support", validate_content_support, qrels, answers, corpus)
    run_check("Absent topics", validate_absent_topics, queries, corpus)
    run_check("Absent tokens not in corpus", validate_empty_corpus_absent_tokens, corpus)
    run_check("QDD distractor queries", validate_qdd_queries, qrels, query_ids)
    run_check("Hash consistency", validate_hash_consistency, queries, qrels, answers, manifest)

    if errors:
        print(f"\nFAILED ({len(errors)} errors):")
        for err in errors:
            print(f"  - {err}")
        return 1

    answerable = sum(1 for q in queries if q["query_class"] != "no_answer")
    no_answer = sum(1 for q in queries if q["query_class"] == "no_answer")
    print("\nALL VALIDATIONS PASSED")
    print(f"  Queries: {len(queries)} ({answerable} answerable, {no_answer} no-answer)")
    print(f"  Corpus: {len(doc_ids)} documents")
    print(f"  Qrels: {len(qrels)} sparse entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
