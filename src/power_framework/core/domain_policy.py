"""POWER 3.8 Phase 5B Domain Policy v2 and pure routing primitives."""

from __future__ import annotations

import fnmatch
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .domains import (
    _CONTROL_CHARACTERS,
    _SLUG_RE,
    MAX_DOMAINS,
    MAX_POLICY_LIST,
    MAX_POLICY_TEXT,
    MAX_QUERY_INTENTS,
    MAX_QUERY_KEYWORDS,
    MAX_ROUTER_MATCHES,
    MAX_SELECTOR_VALUES,
    DomainConfigError,
    DomainRegistry,
    _check_keys,
    _domain_config_path_info,
    _load_yaml,
    _vault_root,
    load_domain_registry,
)

if TYPE_CHECKING:
    from .context_contracts import DomainMatch, QueryIntent, RetrievalBudget

_TOKEN_RE = re.compile(r"[^\W_]+(?:['\u2019\-][^\W_]+)*", re.UNICODE)
_POLICY_REVISION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_ALLOWED_QUERY_INTENTS = frozenset(
    {
        "lookup",
        "project_state",
        "decision",
        "task",
        "code",
        "infrastructure",
        "research",
        "governance",
        "conversation",
        "log",
        "cross_domain",
        "unknown",
    }
)
_ALLOWED_RETRIEVAL_STAGES = frozenset(
    {
        "metadata",
        "fts",
        "tf",
        "semantic",
        "rerank",
        "graph_assisted",
        "temporal",
        "noise_gate",
        "project_state",
        "decisions",
        "tasks",
        "lexical_match",
        "dense_match",
        "candidate_fusion",
        "session_metadata",
        "extracted_entities",
        "summary",
        "relevant_turns",
        "time_range",
        "structured_fields",
    }
)
_ALLOWED_TRAVERSAL_STAGES = frozenset(
    {
        *_ALLOWED_RETRIEVAL_STAGES,
        "semantic_entities",
        "event_history",
        "documentation_fallback",
        "citation_or_relation_expansion",
        "raw_transcript_fallback",
    }
)
_ALLOWED_BUDGET_CLASSES = frozenset({"FAST", "BALANCED", "DEEP"})
_ALLOWED_INDEX_PRIORITIES = frozenset({"HOT", "WARM", "COLD"})
_ALLOWED_DENSE_POLICIES = frozenset({"eager", "batched", "deferred", "on_demand"})
_ALLOWED_NOISE_ACTIONS = frozenset({"include", "downrank", "exclude_from_retrieval", "quarantine"})
_ALLOWED_NOISE_RULES = frozenset(
    {
        "superseded",
        "trivial",
        "duplicate",
        "low_information_density",
        "stale",
        "heartbeat",
        "tool_boilerplate",
        "temporary_progress",
        "repeated_system_prompt",
        "status_spam",
        "generated_catalog",
    }
)
_ALLOWED_AUTHORITY_VALUES = frozenset(
    {"canonical", "verified", "curated", "proposed", "raw", "unknown"}
)


def _normalize_policy_text(value: str, *, max_length: int) -> str:
    if not isinstance(value, str):
        raise DomainConfigError("domain policy text must be a string")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if (
        _CONTROL_CHARACTERS.search(normalized)
        or any(unicodedata.category(char) == "Cf" for char in normalized)
        or len(normalized) > max_length
    ):
        raise DomainConfigError("domain policy text is invalid or unbounded")
    return " ".join(normalized.split())


def _bounded_tuple(value: object, *, field: str, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, tuple) or len(value) > maximum:
        raise DomainConfigError(f"{field} must be a bounded tuple")
    if any(not isinstance(item, str) or not item or len(item) > MAX_POLICY_TEXT for item in value):
        raise DomainConfigError(f"{field} contains invalid text")
    if len(value) != len(set(value)):
        raise DomainConfigError(f"{field} contains duplicate values")
    return value


_V2_ROOT_FIELDS = frozenset(
    {"version", "policy_revision", "normalization_revision", "routing", "domains"}
)
_V2_DOMAIN_FIELDS = frozenset(
    {"name", "selectors", "query_signals", "retrieval", "traversal", "index", "noise", "authority"}
)
_V2_SELECTOR_FIELDS = frozenset({"paths", "tags", "types"})
_V2_QUERY_SIGNAL_FIELDS = frozenset({"keywords", "intents"})
_V2_ROUTING_FIELDS = frozenset(
    {"score_weights", "minimum_score", "low_confidence_score", "max_matches", "tie_policy"}
)
_V2_RETRIEVAL_FIELDS = frozenset(
    {"stages", "max_candidates", "rerank_top_k", "budget_class", "escalation"}
)
_V2_ESCALATION_FIELDS = frozenset({"budget_class", "stages"})
_V2_INDEX_FIELDS = frozenset({"priority", "dense"})
_V2_NOISE_FIELDS = frozenset({"suppress", "unsafe_action"})
_V2_AUTHORITY_FIELDS = frozenset({"prefer", "raw_capture_default", "include_archived_by_default"})


@dataclass(frozen=True)
class DomainSourceSelectors:
    paths: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        paths = _bounded_tuple(
            self.paths, field="source selector paths", maximum=MAX_SELECTOR_VALUES
        )
        _bounded_tuple(self.tags, field="source selector tags", maximum=MAX_SELECTOR_VALUES)
        _bounded_tuple(self.types, field="source selector types", maximum=MAX_SELECTOR_VALUES)
        if not paths and not self.tags and not self.types:
            raise DomainConfigError("source selectors cannot be empty")
        for path in paths:
            _policy_path_pattern(path, "source selector path")


@dataclass(frozen=True)
class DomainQuerySignals:
    keywords: tuple[str, ...] = ()
    intents: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _bounded_tuple(self.keywords, field="query keywords", maximum=MAX_QUERY_KEYWORDS)
        intents = _bounded_tuple(self.intents, field="query intents", maximum=MAX_QUERY_INTENTS)
        if any(intent not in _ALLOWED_QUERY_INTENTS for intent in intents):
            raise DomainConfigError("query intent is invalid")


@dataclass(frozen=True)
class DomainEscalationPolicy:
    budget_class: str
    stages: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.budget_class not in _ALLOWED_BUDGET_CLASSES:
            raise DomainConfigError("escalation budget class is invalid")
        stages = _bounded_tuple(self.stages, field="escalation stages", maximum=MAX_POLICY_LIST)
        if any(stage not in _ALLOWED_RETRIEVAL_STAGES for stage in stages):
            raise DomainConfigError("escalation stage is invalid")


@dataclass(frozen=True)
class DomainRetrievalPolicy:
    stages: tuple[str, ...]
    max_candidates: int
    rerank_top_k: int
    budget_class: str
    escalation: DomainEscalationPolicy | None = None

    def __post_init__(self) -> None:
        stages = _bounded_tuple(self.stages, field="retrieval stages", maximum=MAX_POLICY_LIST)
        if any(stage not in _ALLOWED_RETRIEVAL_STAGES for stage in stages):
            raise DomainConfigError("retrieval stage is invalid")
        if self.budget_class not in _ALLOWED_BUDGET_CLASSES:
            raise DomainConfigError("retrieval budget class is invalid")
        if type(self.max_candidates) is not int or not 1 <= self.max_candidates <= 10_000:
            raise DomainConfigError("retrieval candidate bound is invalid")
        if type(self.rerank_top_k) is not int or not 0 <= self.rerank_top_k <= self.max_candidates:
            raise DomainConfigError("retrieval rerank bound is invalid")


@dataclass(frozen=True)
class DomainTraversalPolicy:
    stages: tuple[str, ...]

    def __post_init__(self) -> None:
        stages = _bounded_tuple(self.stages, field="traversal stages", maximum=MAX_POLICY_LIST)
        if any(stage not in _ALLOWED_TRAVERSAL_STAGES for stage in stages):
            raise DomainConfigError("traversal stage is invalid")


@dataclass(frozen=True)
class DomainIndexPolicy:
    priority: str
    dense: str

    def __post_init__(self) -> None:
        if (
            self.priority not in _ALLOWED_INDEX_PRIORITIES
            or self.dense not in _ALLOWED_DENSE_POLICIES
        ):
            raise DomainConfigError("index policy is invalid")


@dataclass(frozen=True)
class DomainNoisePolicy:
    suppress: tuple[str, ...]
    unsafe_action: str

    def __post_init__(self) -> None:
        suppress = _bounded_tuple(self.suppress, field="noise rules", maximum=MAX_POLICY_LIST)
        if (
            any(item not in _ALLOWED_NOISE_RULES for item in suppress)
            or self.unsafe_action not in _ALLOWED_NOISE_ACTIONS
        ):
            raise DomainConfigError("noise policy is invalid")


@dataclass(frozen=True)
class DomainAuthorityPolicy:
    prefer: tuple[str, ...]
    raw_capture_default: str | None = None
    include_archived_by_default: bool | None = None

    def __post_init__(self) -> None:
        prefer = _bounded_tuple(self.prefer, field="authority preferences", maximum=MAX_POLICY_LIST)
        if any(item not in _ALLOWED_AUTHORITY_VALUES for item in prefer):
            raise DomainConfigError("authority preference is invalid")
        if self.raw_capture_default is not None and self.raw_capture_default != "RAW_ONLY":
            raise DomainConfigError("raw capture default is invalid")
        if (
            self.include_archived_by_default is not None
            and type(self.include_archived_by_default) is not bool
        ):
            raise DomainConfigError("archive default must be boolean")


@dataclass(frozen=True)
class DomainPolicySpec:
    name: str
    selectors: DomainSourceSelectors
    query_signals: DomainQuerySignals
    retrieval: DomainRetrievalPolicy
    traversal: DomainTraversalPolicy
    index: DomainIndexPolicy
    noise: DomainNoisePolicy
    authority: DomainAuthorityPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _SLUG_RE.fullmatch(self.name):
            raise DomainConfigError("domain policy ID is invalid")


@dataclass(frozen=True)
class DomainRoutingPolicy:
    keyword_weight: int
    intent_weight: int
    hint_weight: int
    minimum_score: float
    low_confidence_score: float
    max_matches: int
    tie_policy: str

    def __post_init__(self) -> None:
        weights = (self.keyword_weight, self.intent_weight, self.hint_weight)
        if any(type(weight) is not int or not 0 <= weight <= 100 for weight in weights):
            raise DomainConfigError("score weights must be bounded integers")
        if sum(weights) != 100:
            raise DomainConfigError("score weights must sum to 100")
        if not all(
            math.isfinite(value) and 0.0 <= value <= 1.0
            for value in (self.minimum_score, self.low_confidence_score)
        ):
            raise DomainConfigError("routing thresholds must be finite probabilities")
        if self.low_confidence_score > self.minimum_score:
            raise DomainConfigError("low-confidence threshold cannot exceed minimum")
        if type(self.max_matches) is not int or not 1 <= self.max_matches <= MAX_ROUTER_MATCHES:
            raise DomainConfigError("routing maximum is outside the structural cap")
        if self.tie_policy != "policy_order_then_domain_id":
            raise DomainConfigError("unsupported routing tie policy")

    @property
    def score_weights(self) -> dict[str, int]:
        return {
            "keyword": self.keyword_weight,
            "intent": self.intent_weight,
            "hint": self.hint_weight,
        }


@dataclass(frozen=True)
class DomainPolicyRegistry:
    version: int
    policy_revision: str
    normalization_revision: str
    routing: DomainRoutingPolicy
    domains: tuple[DomainPolicySpec, ...]

    def __post_init__(self) -> None:
        if self.version not in {1, 2} or len(self.domains) > MAX_DOMAINS:
            raise DomainConfigError("domain policy registry is outside its structural bounds")
        if any(not isinstance(domain, DomainPolicySpec) for domain in self.domains):
            raise DomainConfigError("domain policy registry contains invalid domain objects")
        if len({domain.name for domain in self.domains}) != len(self.domains):
            raise DomainConfigError("domain policy registry contains duplicate IDs")
        if not isinstance(self.policy_revision, str) or not _POLICY_REVISION_RE.fullmatch(
            self.policy_revision
        ):
            raise DomainConfigError("domain policy revision is invalid")
        if not isinstance(self.normalization_revision, str) or not _POLICY_REVISION_RE.fullmatch(
            self.normalization_revision
        ):
            raise DomainConfigError("normalization revision is invalid")

    def get(self, name: str) -> DomainPolicySpec | None:
        needle = name.casefold()
        return next((domain for domain in self.domains if domain.name == needle), None)


@dataclass(frozen=True)
class SourceDomainMembership:
    domain: str
    reasons: tuple[str, ...]


def _bounded_string_list(
    value: object,
    *,
    field: str,
    max_items: int,
    max_length: int = MAX_POLICY_TEXT,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if value is None and allow_empty:
        return ()
    if not isinstance(value, list) or len(value) > max_items:
        raise DomainConfigError(f"{field} must be a bounded list of strings")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise DomainConfigError(f"{field} must contain strings")
        normalized = _normalize_policy_text(item, max_length=max_length).casefold()
        if not normalized or normalized in seen:
            raise DomainConfigError(f"{field} contains an empty or duplicate value")
        seen.add(normalized)
        result.append(normalized)
    if not result and not allow_empty:
        raise DomainConfigError(f"{field} must contain a value")
    return tuple(result)


def _bounded_integer(value: object, *, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise DomainConfigError(f"{field} must be a bounded integer")
    return value


def _parse_probability(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainConfigError(f"{field} must be a finite probability")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise DomainConfigError(f"{field} must be a finite probability") from exc
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise DomainConfigError(f"{field} must be a finite probability")
    return result


def _policy_path_pattern(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainConfigError(f"{field} must be a non-empty relative glob")
    text = _normalize_policy_text(value, max_length=MAX_POLICY_TEXT).casefold()
    path = Path(text)
    if (
        path.is_absolute()
        or "\\" in text
        or _WINDOWS_DRIVE.match(text)
        or "://" in text
        or text.casefold().startswith(("file:", "http:", "https:"))
        or any(part in {"..", ""} for part in path.parts)
    ):
        raise DomainConfigError(f"{field} must be a safe vault-relative glob")
    return path.as_posix()


def _parse_source_selectors(raw: object, domain_name: str) -> DomainSourceSelectors:
    fields = _check_keys(raw, _V2_SELECTOR_FIELDS, f"domain {domain_name} selectors")
    raw_paths = fields.get("paths", [])
    if not isinstance(raw_paths, list) or len(raw_paths) > MAX_SELECTOR_VALUES:
        raise DomainConfigError(f"domain {domain_name} selector paths must be bounded")
    paths = tuple(
        _policy_path_pattern(item, f"domain {domain_name} selector path") for item in raw_paths
    )
    tags = _bounded_string_list(
        fields.get("tags", []),
        field=f"domain {domain_name} selector tags",
        max_items=MAX_SELECTOR_VALUES,
        allow_empty=True,
    )
    types = _bounded_string_list(
        fields.get("types", []),
        field=f"domain {domain_name} selector types",
        max_items=MAX_SELECTOR_VALUES,
        allow_empty=True,
    )
    if not (paths or tags or types) or len(set(paths)) != len(paths):
        raise DomainConfigError(f"domain {domain_name} source selectors are invalid")
    return DomainSourceSelectors(paths=paths, tags=tags, types=types)


def _parse_query_signals(raw: object, domain_name: str) -> DomainQuerySignals:
    fields = _check_keys(raw, _V2_QUERY_SIGNAL_FIELDS, f"domain {domain_name} query_signals")
    keywords = _bounded_string_list(
        fields.get("keywords", []),
        field=f"domain {domain_name} query keywords",
        max_items=MAX_QUERY_KEYWORDS,
        allow_empty=True,
    )
    intents = _bounded_string_list(
        fields.get("intents", []),
        field=f"domain {domain_name} query intents",
        max_items=MAX_QUERY_INTENTS,
        allow_empty=True,
    )
    if any(intent not in _ALLOWED_QUERY_INTENTS for intent in intents):
        raise DomainConfigError(f"domain {domain_name} query intent is invalid")
    return DomainQuerySignals(keywords=keywords, intents=intents)


def _parse_routing_policy(raw: object) -> DomainRoutingPolicy:
    fields = _check_keys(raw, _V2_ROUTING_FIELDS, "domain routing policy")
    weights = _check_keys(
        fields.get("score_weights"), frozenset({"keyword", "intent", "hint"}), "score_weights"
    )
    parsed = {
        name: _bounded_integer(value, field=f"score_weights.{name}", minimum=0, maximum=100)
        for name, value in weights.items()
    }
    if set(parsed) != {"keyword", "intent", "hint"} or sum(parsed.values()) != 100:
        raise DomainConfigError("score weights must be bounded integers summing to 100")
    minimum = _parse_probability(fields.get("minimum_score"), "minimum_score")
    low = _parse_probability(fields.get("low_confidence_score"), "low_confidence_score")
    if low > minimum:
        raise DomainConfigError("low_confidence_score cannot exceed minimum_score")
    maximum = _bounded_integer(
        fields.get("max_matches"), field="max_matches", minimum=1, maximum=MAX_ROUTER_MATCHES
    )
    if fields.get("tie_policy") != "policy_order_then_domain_id":
        raise DomainConfigError("tie_policy is not supported")
    return DomainRoutingPolicy(
        parsed["keyword"],
        parsed["intent"],
        parsed["hint"],
        minimum,
        low,
        maximum,
        "policy_order_then_domain_id",
    )


def _parse_retrieval_policy(raw: object, domain_name: str) -> DomainRetrievalPolicy:
    fields = _check_keys(raw, _V2_RETRIEVAL_FIELDS, f"domain {domain_name} retrieval")
    stages = _bounded_string_list(
        fields.get("stages"),
        field=f"domain {domain_name} retrieval stages",
        max_items=MAX_POLICY_LIST,
    )
    if any(stage not in _ALLOWED_RETRIEVAL_STAGES for stage in stages):
        raise DomainConfigError(f"domain {domain_name} retrieval stage is invalid")
    maximum = _bounded_integer(
        fields.get("max_candidates"),
        field=f"domain {domain_name} max_candidates",
        minimum=1,
        maximum=10_000,
    )
    rerank = _bounded_integer(
        fields.get("rerank_top_k"),
        field=f"domain {domain_name} rerank_top_k",
        minimum=0,
        maximum=maximum,
    )
    budget = fields.get("budget_class")
    if budget not in _ALLOWED_BUDGET_CLASSES:
        raise DomainConfigError(f"domain {domain_name} budget class is invalid")
    escalation_raw = fields.get("escalation")
    escalation = None
    if escalation_raw is not None:
        escalation_fields = _check_keys(
            escalation_raw, _V2_ESCALATION_FIELDS, f"domain {domain_name} escalation"
        )
        escalation_budget = escalation_fields.get("budget_class")
        if escalation_budget not in _ALLOWED_BUDGET_CLASSES:
            raise DomainConfigError(f"domain {domain_name} escalation budget class is invalid")
        escalation_stages = _bounded_string_list(
            escalation_fields.get("stages"),
            field=f"domain {domain_name} escalation stages",
            max_items=MAX_POLICY_LIST,
        )
        if any(stage not in _ALLOWED_RETRIEVAL_STAGES for stage in escalation_stages):
            raise DomainConfigError(f"domain {domain_name} escalation stage is invalid")
        escalation = DomainEscalationPolicy(escalation_budget, escalation_stages)
    return DomainRetrievalPolicy(stages, maximum, rerank, budget, escalation)


def _parse_v2_domain(raw: object) -> DomainPolicySpec:
    fields = _check_keys(raw, _V2_DOMAIN_FIELDS, "domain")
    name = fields.get("name")
    if not isinstance(name, str) or not _SLUG_RE.fullmatch(name.strip().casefold()):
        raise DomainConfigError("domain name must be a lowercase slug")
    name = name.strip().casefold()
    selectors = _parse_source_selectors(fields.get("selectors"), name)
    signals = _parse_query_signals(fields.get("query_signals"), name)
    retrieval = _parse_retrieval_policy(fields.get("retrieval"), name)
    traversal = _bounded_string_list(
        fields.get("traversal"), field=f"domain {name} traversal", max_items=MAX_POLICY_LIST
    )
    if any(stage not in _ALLOWED_TRAVERSAL_STAGES for stage in traversal):
        raise DomainConfigError(f"domain {name} traversal declaration is invalid")
    index = _check_keys(fields.get("index"), _V2_INDEX_FIELDS, f"domain {name} index")
    priority, dense = index.get("priority"), index.get("dense")
    if priority not in _ALLOWED_INDEX_PRIORITIES or dense not in _ALLOWED_DENSE_POLICIES:
        raise DomainConfigError(f"domain {name} index policy is invalid")
    noise = _check_keys(fields.get("noise"), _V2_NOISE_FIELDS, f"domain {name} noise")
    suppress = _bounded_string_list(
        noise.get("suppress"), field=f"domain {name} noise suppress", max_items=MAX_POLICY_LIST
    )
    unsafe_action = noise.get("unsafe_action")
    if (
        any(item not in _ALLOWED_NOISE_RULES for item in suppress)
        or unsafe_action not in _ALLOWED_NOISE_ACTIONS
    ):
        raise DomainConfigError(f"domain {name} noise policy is invalid")
    authority = _check_keys(
        fields.get("authority"), _V2_AUTHORITY_FIELDS, f"domain {name} authority"
    )
    prefer = _bounded_string_list(
        authority.get("prefer"), field=f"domain {name} authority prefer", max_items=MAX_POLICY_LIST
    )
    if any(item not in _ALLOWED_AUTHORITY_VALUES for item in prefer):
        raise DomainConfigError(f"domain {name} authority value is invalid")
    raw_capture = authority.get("raw_capture_default")
    if raw_capture is not None and raw_capture != "RAW_ONLY":
        raise DomainConfigError(f"domain {name} raw capture policy is invalid")
    archived = authority.get("include_archived_by_default")
    if archived is not None and type(archived) is not bool:
        raise DomainConfigError(f"domain {name} archive default must be boolean")
    return DomainPolicySpec(
        name,
        selectors,
        signals,
        retrieval,
        DomainTraversalPolicy(traversal),
        DomainIndexPolicy(priority, dense),
        DomainNoisePolicy(suppress, unsafe_action),
        DomainAuthorityPolicy(prefer, raw_capture, archived),
    )


def _parse_v2_policy(raw: object) -> DomainPolicyRegistry:
    fields = _check_keys(raw, _V2_ROOT_FIELDS, "domain policy")
    if type(fields.get("version")) is not int or fields.get("version") != 2:
        raise DomainConfigError("domain policy version must be 2")
    revision, normalization = fields.get("policy_revision"), fields.get("normalization_revision")
    if (
        not isinstance(revision, str)
        or not _POLICY_REVISION_RE.fullmatch(revision.strip().casefold())
        or not isinstance(normalization, str)
        or not _POLICY_REVISION_RE.fullmatch(normalization.strip().casefold())
    ):
        raise DomainConfigError("domain policy revisions are invalid")
    entries = fields.get("domains")
    if not isinstance(entries, list) or not 0 < len(entries) <= MAX_DOMAINS:
        raise DomainConfigError("domain policy domains must be bounded and non-empty")
    domains = tuple(_parse_v2_domain(entry) for entry in entries)
    if len({domain.name for domain in domains}) != len(domains):
        raise DomainConfigError("domain policy contains duplicate IDs")
    return DomainPolicyRegistry(
        2,
        revision.strip().casefold(),
        normalization.strip().casefold(),
        _parse_routing_policy(fields.get("routing")),
        domains,
    )


def _default_v1_routing() -> DomainRoutingPolicy:
    return DomainRoutingPolicy(
        50, 30, 20, 0.30, 0.20, MAX_ROUTER_MATCHES, "policy_order_then_domain_id"
    )


def _adapt_v1_registry(registry: DomainRegistry) -> DomainPolicyRegistry:
    domains: list[DomainPolicySpec] = []
    for domain in registry.domains:
        tags: list[str] = []
        types: list[str] = []
        keywords: list[str] = []
        for rule in domain.rules:
            for values, target in (
                (rule.tags, tags),
                (rule.types, types),
                (rule.keywords, keywords),
            ):
                for value in values:
                    if value not in target:
                        target.append(value)
        domains.append(
            DomainPolicySpec(
                domain.name,
                DomainSourceSelectors(
                    (f"{domain.path.as_posix().casefold()}/**",), tuple(tags), tuple(types)
                ),
                DomainQuerySignals(tuple(keywords), ()),
                DomainRetrievalPolicy(("metadata", "fts"), 40, 0, "FAST"),
                DomainTraversalPolicy(("metadata",)),
                DomainIndexPolicy("WARM", "deferred"),
                DomainNoisePolicy(("duplicate",), "quarantine"),
                DomainAuthorityPolicy(("canonical", "verified")),
            )
        )
    return DomainPolicyRegistry(
        1, "v1-adapter", "nfkc-casefold-tokens-v1", _default_v1_routing(), tuple(domains)
    )


def load_domain_policy(vault_dir: Path) -> DomainPolicyRegistry:
    """Load strict v2 policy or an explicit read-only adapter for v1."""
    root = _vault_root(vault_dir)
    config_path, explicit = _domain_config_path_info(root)
    if not config_path.exists():
        if explicit:
            raise DomainConfigError("explicit domain policy is missing")
        return DomainPolicyRegistry(
            1, "v1-empty", "nfkc-casefold-tokens-v1", _default_v1_routing(), ()
        )
    raw = _load_yaml(config_path, label="domain policy", root=root)
    if not isinstance(raw, dict) or type(raw.get("version")) is not int:
        raise DomainConfigError("domain policy version must be an integer")
    if raw["version"] == 1:
        return _adapt_v1_registry(load_domain_registry(root))
    if raw["version"] == 2:
        return _parse_v2_policy(raw)
    raise DomainConfigError("unsupported domain policy version")


def _normalize_query_text(value: str) -> str:
    if not isinstance(value, str):
        raise DomainConfigError("router query must be text")
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = "".join(
        " " if unicodedata.category(char) in {"Cc", "Cf"} else char for char in normalized
    )
    normalized = " ".join(normalized.split())
    if not normalized or len(normalized) > 2048:
        raise DomainConfigError("router query is empty or unbounded")
    return normalized


def _query_tokens(value: str) -> tuple[str, ...]:
    return tuple(_TOKEN_RE.findall(_normalize_query_text(value)))


def _contains_phrase(query_tokens: tuple[str, ...], phrase: str) -> bool:
    phrase_tokens = _query_tokens(phrase)
    width = len(phrase_tokens)
    return (
        bool(phrase_tokens)
        and width <= len(query_tokens)
        and any(
            query_tokens[i : i + width] == phrase_tokens
            for i in range(len(query_tokens) - width + 1)
        )
    )


def _normalize_source_path(value: str) -> str:
    if not isinstance(value, str):
        raise DomainConfigError("source path must be text")
    normalized = unicodedata.normalize("NFKC", value).strip()
    path = Path(normalized)
    if (
        not normalized
        or len(normalized) > 1024
        or path.is_absolute()
        or "\\" in normalized
        or _CONTROL_CHARACTERS.search(normalized)
        or _WINDOWS_DRIVE.match(normalized)
        or "://" in normalized
        or any(part in {"..", ""} for part in path.parts)
    ):
        raise DomainConfigError("source path must be a safe relative path")
    return path.as_posix().casefold()


def _normalize_source_values(values: Any, *, field: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if (
        isinstance(values, (str, bytes))
        or not isinstance(values, Sequence)
        or len(values) > MAX_SELECTOR_VALUES
    ):
        raise DomainConfigError(f"source {field} is unbounded")
    normalized = set()
    for value in values:
        if not isinstance(value, str):
            raise DomainConfigError(f"source {field} must contain strings")
        item = _normalize_policy_text(value, max_length=MAX_POLICY_TEXT).casefold()
        if item:
            normalized.add(item)
    return tuple(sorted(normalized))


class SourceDomainClassifier:
    """Classify source metadata without consuming query text."""

    def __init__(self, policy: DomainPolicyRegistry) -> None:
        self._policy = policy

    def classify(
        self,
        source: Any = None,
        *,
        path: str | None = None,
        tags: Sequence[str] = (),
        note_type: str = "",
    ) -> tuple[SourceDomainMembership, ...]:
        if source is not None:
            if path is not None or tags or note_type:
                raise DomainConfigError("source object cannot be combined with source fields")
            if isinstance(source, Mapping):
                path, tags, note_type = (
                    source.get("path", source.get("rel_path")),
                    source.get("tags", ()),
                    source.get("note_type", source.get("type", "")),
                )
            else:
                path, tags, note_type = (
                    getattr(source, "path", getattr(source, "rel_path", None)),
                    getattr(source, "tags", ()),
                    getattr(source, "note_type", getattr(source, "type", "")),
                )
        if path is None or not isinstance(note_type, str):
            raise DomainConfigError("source path and note type are required")
        source_path = _normalize_source_path(path)
        source_tags = set(_normalize_source_values(tags, field="tags"))
        source_type = _normalize_policy_text(note_type, max_length=MAX_POLICY_TEXT).casefold()
        results: list[SourceDomainMembership] = []
        for domain in self._policy.domains:
            selectors = domain.selectors
            matched = (
                any(fnmatch.fnmatchcase(source_path, pattern) for pattern in selectors.paths),
                bool(source_tags.intersection(selectors.tags)),
                bool(source_type and source_type in selectors.types),
            )
            reasons = tuple(
                reason
                for hit, reason in zip(
                    matched,
                    ("source_path_selector", "source_tag_selector", "source_type_selector"),
                    strict=True,
                )
                if hit
            )
            if reasons:
                results.append(SourceDomainMembership(domain.name, reasons))
        return tuple(results)


class RetrievalDomainRouter:
    """Pure, deterministic, bounded query-to-domain router for Phase 5B."""

    def __init__(self, policy: DomainPolicyRegistry) -> None:
        self._policy = policy

    def route(
        self,
        query: str | QueryIntent,
        *,
        intent: str | None = None,
        routing_hints: Sequence[str] = (),
        budget: RetrievalBudget | None = None,
        max_domains: int | None = None,
    ) -> tuple[DomainMatch, ...]:
        from .context_contracts import DomainMatch
        from .context_contracts import QueryIntent as RuntimeQueryIntent

        if (
            isinstance(routing_hints, (str, bytes))
            or not isinstance(routing_hints, Sequence)
            or len(routing_hints) > MAX_SELECTOR_VALUES
        ):
            raise DomainConfigError("routing_hints must be bounded")
        query_text: str
        intent_value: Any = intent
        hint_values: list[str] = list(routing_hints)
        if isinstance(query, RuntimeQueryIntent):
            if intent is not None:
                raise DomainConfigError("intent must not be repeated")
            query_text, intent_value = query.query, query.intent.value
            hint_values.extend(query.domain_hints or ())
        elif isinstance(query, str):
            query_text, intent_value = query, intent
        else:
            raise DomainConfigError("router query must be text or QueryIntent")
        if len(hint_values) > MAX_SELECTOR_VALUES or any(
            not isinstance(value, str) or not value.strip() for value in hint_values
        ):
            raise DomainConfigError("routing_hints must contain bounded non-empty strings")
        query_tokens = tuple(_TOKEN_RE.findall(_normalize_query_text(query_text)))
        normalized_intent = None
        if intent_value is not None:
            raw_intent = getattr(intent_value, "value", intent_value)
            if not isinstance(raw_intent, str):
                raise DomainConfigError("router intent must be text")
            normalized_intent = _normalize_policy_text(
                raw_intent, max_length=MAX_POLICY_TEXT
            ).casefold()
            if normalized_intent not in _ALLOWED_QUERY_INTENTS:
                raise DomainConfigError("router intent is invalid")
        normalized_hints = {
            _normalize_policy_text(value, max_length=MAX_POLICY_TEXT).casefold()
            for value in hint_values
        }
        if len(normalized_hints) != len(hint_values):
            raise DomainConfigError("routing_hints contains duplicates")
        known_hints = {
            domain.name for domain in self._policy.domains if domain.name in normalized_hints
        }
        maximum = min(MAX_ROUTER_MATCHES, self._policy.routing.max_matches)
        if budget is not None:
            from .context_contracts import RetrievalBudget as RuntimeRetrievalBudget

            if not isinstance(budget, RuntimeRetrievalBudget):
                raise DomainConfigError("budget must be a validated RetrievalBudget")
            maximum = min(maximum, budget.max_domains)
        if max_domains is not None:
            if type(max_domains) is not int or max_domains < 1:
                raise DomainConfigError("max_domains must be positive")
            maximum = min(maximum, max_domains)
        keyword_matches = {
            domain.name: any(
                _contains_phrase(query_tokens, keyword) for keyword in domain.query_signals.keywords
            )
            for domain in self._policy.domains
        }
        intent_matches = {
            domain.name: normalized_intent is not None
            and normalized_intent in domain.query_signals.intents
            for domain in self._policy.domains
        }
        candidates: list[tuple[int, int, DomainPolicySpec, list[str]]] = []
        for index, domain in enumerate(self._policy.domains):
            keyword_match, intent_match, hint_match = (
                keyword_matches[domain.name],
                intent_matches[domain.name],
                domain.name in known_hints,
            )
            units = (
                (self._policy.routing.keyword_weight if keyword_match else 0)
                + (self._policy.routing.intent_weight if intent_match else 0)
                + (self._policy.routing.hint_weight if hint_match else 0)
            )
            reasons = [
                reason
                for matched, weight, reason in (
                    (keyword_match, self._policy.routing.keyword_weight, "keyword_signal"),
                    (intent_match, self._policy.routing.intent_weight, "intent_signal"),
                    (hint_match, self._policy.routing.hint_weight, "caller_hint_signal"),
                )
                if matched and weight > 0
            ]
            if known_hints and (
                (
                    (keyword_match or intent_match)
                    and not hint_match
                    and any(hint != domain.name for hint in known_hints)
                )
                or (
                    hint_match
                    and not keyword_match
                    and not intent_match
                    and (any(keyword_matches.values()) or any(intent_matches.values()))
                )
            ):
                reasons.append("caller_hint_conflict")
            if reasons and units / 100.0 >= self._policy.routing.minimum_score:
                candidates.append((units, index, domain, reasons))
        candidates.sort(key=lambda item: (-item[0], item[1], item[2].name))
        top = candidates[0][0] if candidates else 0
        results: list[DomainMatch] = []
        for units, _index, domain, reasons in candidates[:maximum]:
            if units / 100.0 <= self._policy.routing.low_confidence_score:
                reasons.append(
                    "low_confidence_secondary" if units < top else "low_confidence_match"
                )
            results.append(DomainMatch(domain=domain.name, score=units / 100.0, reasons=reasons))
        return tuple(results)


def route_query_domains(
    policy_or_vault: DomainPolicyRegistry | Path,
    query: str | QueryIntent,
    *,
    intent: str | None = None,
    routing_hints: Sequence[str] = (),
    budget: RetrievalBudget | None = None,
    max_domains: int | None = None,
) -> tuple[DomainMatch, ...]:
    policy = (
        load_domain_policy(policy_or_vault)
        if isinstance(policy_or_vault, Path)
        else policy_or_vault
    )
    return RetrievalDomainRouter(policy).route(
        query, intent=intent, routing_hints=routing_hints, budget=budget, max_domains=max_domains
    )
