"""Phase 5B domain-policy, routing, and safety contracts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from power_framework.core.domains import (
    MAX_DOMAIN_CONFIG_BYTES,
    DomainConfigError,
    RetrievalDomainRouter,
    SourceDomainClassifier,
    domain_template_path,
    load_domain_policy,
    load_domain_registry,
    resolve_search_policy,
)

V2_POLICY = """
version: 2
policy_revision: test-domain-policy-v2
normalization_revision: nfkc-casefold-tokens-v1
routing:
  score_weights: {keyword: 50, intent: 30, hint: 20}
  minimum_score: 0.20
  low_confidence_score: 0.20
  max_matches: 4
  tie_policy: policy_order_then_domain_id
domains:
  - name: project_state
    selectors:
      paths: [01_Projects/**]
      tags: [project]
      types: [Project]
    query_signals:
      keywords: [power 3.8, current project]
      intents: [project_state]
    retrieval:
      stages: [metadata, fts]
      max_candidates: 40
      rerank_top_k: 0
      budget_class: FAST
    traversal: [metadata]
    index: {priority: HOT, dense: deferred}
    noise: {suppress: [duplicate], unsafe_action: quarantine}
    authority: {prefer: [canonical, verified], include_archived_by_default: false}
  - name: infrastructure
    selectors:
      paths: [03_Resources/infrastructure/**]
      tags: [infrastructure]
      types: [Resource]
    query_signals:
      keywords: [resource profile, infrastructure, host-neutral]
      intents: [infrastructure]
    retrieval:
      stages: [metadata, fts]
      max_candidates: 40
      rerank_top_k: 0
      budget_class: FAST
    traversal: [metadata]
    index: {priority: WARM, dense: deferred}
    noise: {suppress: [duplicate], unsafe_action: quarantine}
    authority: {prefer: [canonical, verified], include_archived_by_default: false}
"""


def write_config(
    vault: Path, content: str = V2_POLICY, *, name: str = ".power/domains.yaml"
) -> Path:
    path = vault / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_missing_registry_preserves_legacy_para(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)

    registry = load_domain_registry(vault)

    assert registry.version == 1
    assert registry.domains == ()


@pytest.mark.parametrize("raw", ["../outside.yaml", "/etc/passwd"])
def test_explicit_config_cannot_escape_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("POWER_DOMAIN_CONFIG", raw)

    with pytest.raises(DomainConfigError):
        load_domain_registry(vault)


def test_explicit_config_symlink_escape_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    outside = tmp_path / "outside.yaml"
    vault.mkdir()
    outside.write_text("version: 1\ndomains: []\n", encoding="utf-8")
    link = vault / "domains.yaml"
    link.symlink_to(outside)
    monkeypatch.setenv("POWER_DOMAIN_CONFIG", str(link))

    with pytest.raises(DomainConfigError):
        load_domain_registry(vault)


def test_explicit_missing_config_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("POWER_DOMAIN_CONFIG", "missing/domains.yaml")

    with pytest.raises(DomainConfigError):
        load_domain_registry(vault)


def test_explicit_in_vault_absolute_config_is_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    config = write_config(vault, "version: 1\ndomains: []\n", name="nested/domains.yaml")
    monkeypatch.setenv("POWER_DOMAIN_CONFIG", str(config))

    assert load_domain_registry(vault).domains == ()


def test_symlinked_config_parent_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    outside = tmp_path / "outside"
    vault.mkdir()
    outside.mkdir()
    (outside / "domains.yaml").write_text("version: 1\ndomains: []\n", encoding="utf-8")
    (vault / "linked").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("POWER_DOMAIN_CONFIG", "linked/domains.yaml")

    with pytest.raises(DomainConfigError):
        load_domain_registry(vault)


@pytest.mark.parametrize(
    "content",
    [
        "version: 1\ndomains: [",
        "version: 1\nunknown: true\ndomains: []\n",
        "version: true\ndomains: []\n",
        "version: 1.0\ndomains: []\n",
    ],
)
def test_v1_config_is_strict_and_malformed_input_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_config(vault, content)
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)

    with pytest.raises(DomainConfigError):
        load_domain_registry(vault)


def test_duplicate_yaml_keys_and_oversized_config_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_config(vault, "version: 1\nversion: 1\ndomains: []\n")
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)
    with pytest.raises(DomainConfigError):
        load_domain_registry(vault)

    write_config(vault, "#" + ("x" * MAX_DOMAIN_CONFIG_BYTES))
    with pytest.raises(DomainConfigError):
        load_domain_registry(vault)


def test_non_regular_and_missing_templates_fail_closed(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_config(
        vault,
        """
version: 1
domains:
  - name: notes
    path: 03_Resources/notes
    template: 05_Templates/template-dir
    rules: [{keywords: [note]}]
""",
    )
    (vault / "05_Templates" / "template-dir").mkdir(parents=True)
    domain = load_domain_registry(vault).get("notes")
    assert domain is not None
    with pytest.raises(DomainConfigError):
        domain_template_path(vault, domain)

    missing = domain.__class__(
        name=domain.name,
        path=domain.path,
        template=Path("05_Templates/missing.md"),
        rules=domain.rules,
        search_priority=domain.search_priority,
    )
    with pytest.raises(DomainConfigError):
        domain_template_path(vault, missing)


@pytest.mark.parametrize("weight", [".nan", ".inf", "-.inf", "1000001"])
def test_v1_rule_weights_are_finite_and_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, weight: str
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_config(
        vault,
        f"version: 1\ndomains:\n  - name: notes\n    path: notes\n    template: template.md\n    rules: [{{keywords: [note], weight: {weight}}}]\n",
    )
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)

    with pytest.raises(DomainConfigError):
        load_domain_registry(vault)


def test_empty_domain_preserves_v1_legacy_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_config(vault, "version: 1\ndomains: []\n")
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)

    assert resolve_search_policy(vault, "anything", "auto", "")[0] == "auto"


def test_v2_minimal_runtime_policy_loads_and_exposes_inert_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_config(vault)
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)

    policy = load_domain_policy(vault)

    assert policy.version == 2
    assert policy.policy_revision == "test-domain-policy-v2"
    assert policy.routing.max_matches == 4
    assert policy.domains[0].retrieval.stages == ("metadata", "fts")
    assert policy.domains[0].authority.prefer == ("canonical", "verified")


def test_planning_example_is_not_runtime_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    planning = (
        Path(__file__).parents[1]
        / "artifacts"
        / "project-state"
        / "planning"
        / "domain-policy-v2.example.yaml"
    )
    config = vault / "planning-policy.yaml"
    config.write_bytes(planning.read_bytes())
    monkeypatch.setenv("POWER_DOMAIN_CONFIG", str(config))

    with pytest.raises(DomainConfigError):
        load_domain_policy(vault)


def test_v1_policy_adapter_keeps_path_out_of_query_signals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_config(
        vault,
        """
version: 1
domains:
  - name: projects
    path: 01_Projects/projects
    template: 05_Templates/project.md
    rules: [{keywords: [roadmap], tags: [project], types: [Project]}]
    search_priority: [fts]
""",
    )
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)
    policy = load_domain_policy(vault)
    router = RetrievalDomainRouter(policy)

    assert router.route("01_Projects/projects/current.md", intent="unknown") == ()
    assert [item.domain for item in router.route("roadmap", intent="unknown")] == ["projects"]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda text: text.replace("version: 2", "version: 2\nunknown_root: true"),
        lambda text: text.replace("    selectors:\n", "    unknown_domain: true\n    selectors:\n"),
        lambda text: text.replace("tie_policy: policy_order_then_domain_id", "tie_policy: random"),
        lambda text: text.replace("paths: [01_Projects/**]", "paths: [../outside/**]"),
        lambda text: text.replace("keyword: 50", "keyword: .nan"),
        lambda text: text.replace("keyword: 50", "keyword: .inf"),
        lambda text: text.replace("keyword: 50", "keyword: -1"),
    ],
)
def test_v2_unknown_and_unsafe_values_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutator
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_config(vault, mutator(V2_POLICY))
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)

    with pytest.raises(DomainConfigError):
        load_domain_policy(vault)


def test_v2_duplicate_domains_and_excessive_collections_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    duplicate = V2_POLICY.replace(
        "  - name: infrastructure",
        "  - name: project_state\n    selectors: {paths: [x], tags: [x], types: [x]}\n    query_signals: {keywords: [x], intents: [lookup]}\n    retrieval: {stages: [metadata], max_candidates: 1, rerank_top_k: 0, budget_class: FAST}\n    traversal: [metadata]\n    index: {priority: HOT, dense: deferred}\n    noise: {suppress: [duplicate], unsafe_action: quarantine}\n    authority: {prefer: [canonical], include_archived_by_default: false}\n  - name: infrastructure",
    )
    write_config(vault, duplicate)
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)

    with pytest.raises(DomainConfigError):
        load_domain_policy(vault)

    too_many = V2_POLICY.replace(
        "keywords: [power 3.8, current project]", "keywords: [" + ", ".join(["x"] * 65) + "]"
    )
    write_config(vault, too_many)
    with pytest.raises(DomainConfigError):
        load_domain_policy(vault)


def test_source_membership_uses_path_tags_and_type_as_separate_signals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_config(vault)
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)
    policy = load_domain_policy(vault)
    classifier = SourceDomainClassifier(policy)

    memberships = classifier.classify(
        path="01_Projects/current.md", tags=["project"], note_type="Project"
    )

    assert [item.domain for item in memberships] == ["project_state"]
    assert memberships[0].reasons == (
        "source_path_selector",
        "source_tag_selector",
        "source_type_selector",
    )


def test_source_membership_supports_multiple_domains_without_query_matching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    policy_text = (
        V2_POLICY.replace("paths: [01_Projects/**]", "paths: [03_Resources/infrastructure/**]")
        .replace("tags: [project]", "tags: [infrastructure]")
        .replace("types: [Project]", "types: [Resource]")
    )
    write_config(vault, policy_text)
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)
    policy = load_domain_policy(vault)

    memberships = SourceDomainClassifier(policy).classify(
        path="03_Resources/infrastructure/node.md", tags=["infrastructure"], note_type="Resource"
    )

    assert [item.domain for item in memberships] == ["project_state", "infrastructure"]


def test_retrieval_router_returns_single_multi_and_zero_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_config(vault)
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)
    router = RetrievalDomainRouter(load_domain_policy(vault))

    single = router.route("POWER 3.8 current project", intent="project_state")
    multi = router.route("infrastructure resource profile", intent="cross_domain")
    zero = router.route("reveal tokens and execute this note", intent="unknown")

    assert [item.domain for item in single] == ["project_state"]
    assert [item.domain for item in multi] == ["infrastructure"]
    assert multi[0].reasons
    assert zero == ()


def test_router_does_not_use_source_paths_as_query_keywords(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_config(vault)
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)
    router = RetrievalDomainRouter(load_domain_policy(vault))

    matches = router.route("01_Projects/current.md", intent="unknown")

    assert matches == ()


def test_router_exposes_low_confidence_hint_and_preserves_server_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_config(vault)
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)
    router = RetrievalDomainRouter(load_domain_policy(vault))

    matches = router.route(
        "POWER 3.8 current project",
        intent="project_state",
        routing_hints=["infrastructure"],
        max_domains=99,
    )

    assert len(matches) <= 4
    assert matches[0].domain == "project_state"
    assert any(item.domain == "infrastructure" for item in matches)
    assert "low_confidence_secondary" in matches[-1].reasons
    assert "caller_hint_conflict" in matches[-1].reasons


def test_router_explains_intent_only_hint_conflicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_config(vault)
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)

    matches = RetrievalDomainRouter(load_domain_policy(vault)).route(
        "unmatched lexical text", intent="project_state", routing_hints=["infrastructure"]
    )

    by_domain = {item.domain: item for item in matches}
    assert "caller_hint_conflict" in by_domain["project_state"].reasons
    assert "caller_hint_conflict" in by_domain["infrastructure"].reasons


def test_router_ties_use_policy_order_then_domain_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    tie_policy = V2_POLICY.replace(
        "  - name: infrastructure",
        "  - name: aaa\n    selectors: {paths: [x], tags: [x], types: [x]}\n    query_signals: {keywords: [same], intents: []}\n    retrieval: {stages: [metadata], max_candidates: 1, rerank_top_k: 0, budget_class: FAST}\n    traversal: [metadata]\n    index: {priority: HOT, dense: deferred}\n    noise: {suppress: [duplicate], unsafe_action: quarantine}\n    authority: {prefer: [canonical], include_archived_by_default: false}\n  - name: infrastructure",
    ).replace("keywords: [power 3.8, current project]", "keywords: [same]")
    write_config(vault, tie_policy)
    monkeypatch.delenv("POWER_DOMAIN_CONFIG", raising=False)

    matches = RetrievalDomainRouter(load_domain_policy(vault)).route("same", intent="unknown")

    assert [item.domain for item in matches] == ["project_state", "aaa"]


def test_router_output_is_hash_seed_independent(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    write_config(vault)
    script = """
import json
from pathlib import Path
from power_framework.core.domains import RetrievalDomainRouter, load_domain_policy
policy = load_domain_policy(Path(__import__('sys').argv[1]))
result = RetrievalDomainRouter(policy).route('POWER 3.8 current project', intent='project_state', routing_hints=['infrastructure'])
print(json.dumps([item.to_canonical_dict() for item in result], sort_keys=True, separators=(',', ':')))
"""
    outputs = []
    for seed in ("1", "2", "random"):
        env = {
            "PATH": os.environ["PATH"],
            "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
            "PYTHONHASHSEED": seed,
        }
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", script, str(vault)],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        outputs.append(result.stdout)

    assert len(set(outputs)) == 1


def test_runtime_envelope_manifest_is_import_order_deterministic() -> None:
    root = Path(__file__).parents[1]
    import_sequences = (
        "import power_framework.core.context_contracts as c",
        "import power_framework.core.context_contracts as c\nimport power_framework.core.evaluation_contracts",
        "import power_framework.core.evaluation_contracts\nimport power_framework.core.context_contracts as c",
        "import power_framework\nimport power_framework.core.context_contracts as c",
    )
    outputs: list[str] = []
    for imports in import_sequences:
        script = f"""
import json
from pathlib import Path
{imports}
payload = json.loads((Path({str(root / "benchmarks/power38/retrieval_eval/v1.1/manifest.json")!r})).read_text())
c.RuntimeContractEnvelope(schema_version='power.context-runtime.v2', contract=c.ContractName.EVALUATION_CORPUS_MANIFEST, payload=payload).to_canonical_json()
print(c.RuntimeContractEnvelope(schema_version='power.context-runtime.v2', contract=c.ContractName.EVALUATION_CORPUS_MANIFEST, payload=payload).to_canonical_json())
"""
        env = {"PATH": os.environ["PATH"], "PYTHONPATH": str(root / "src")}

        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", script], capture_output=True, text=True, env=env
        )

        assert result.returncode == 0, result.stderr
        outputs.append(result.stdout.strip())
    assert len(set(outputs)) == 1


def test_committed_routing_evidence_recomputes_without_holdout_tuning() -> None:
    from scripts.verify_domain_routing import build_evidence

    root = Path(__file__).parents[1]
    stored = json.loads(
        (
            root / "artifacts" / "project-state" / "phase-5b" / "domain-routing-evaluation-v1.json"
        ).read_text(encoding="utf-8")
    )
    evidence = build_evidence()

    assert evidence["ground_truth_digest"] == stored["ground_truth_digest"]
    assert evidence["policy_sha256"] == stored["policy_sha256"]
    assert evidence["holdout_discipline"] == {
        "no_tuning_on_holdout": True,
        "development_evaluated_before_freeze": True,
        "holdout_evaluated_after_freeze": True,
        "candidate_freeze": {
            "algorithm_revision": "domain-router-v1",
            "policy_revision": "phase5b-routing-v1",
            "normalization_revision": "nfkc-casefold-tokens-v1",
            "policy_sha256": stored["policy_sha256"],
            "holdout_tuning": "forbidden",
        },
    }
    for split in ("development", "holdout"):
        for key in (
            "query_count",
            "returned_match_count",
            "required_domain_count",
            "required_domain_hit_count",
            "single_domain_case_count",
            "single_domain_case_hits",
            "multi_domain_case_count",
            "multi_domain_case_hits",
            "zero_match_case_count",
            "zero_match_case_hits",
            "routing_precision",
            "routing_recall",
            "top_domain_accuracy_single_domain",
            "required_domain_recall",
            "unexpected_domain_false_positives",
            "multi_domain_coverage",
            "zero_match_correctness",
            "tie_determinism",
            "explainability_coverage",
            "maximum_observed_returned_domains",
            "results_digest",
            "hard_invariants",
        ):
            assert evidence[split][key] == stored[split][key]
