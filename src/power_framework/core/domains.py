"""Opt-in domain routing and search policy for POWER vaults.

The legacy P.A.R.A. layout remains the default.  A vault can add
``.power/domains.yaml`` to make directory placement, templates, and search
priorities explicit.  The registry is deliberately small and fail-closed:
unknown retrieval modes, unsafe paths, duplicate domains, and malformed rules
are rejected before a note is written or a search policy is selected.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

SUPPORTED_SEARCH_MODES = frozenset(
    {"fts", "vector", "hybrid", "semantic", "reranked", "graph_assisted"}
)
SEARCH_MODE_ALIASES = {"hybrid_reranked": "reranked"}
DOMAIN_CONFIG_RELATIVE_PATH = Path(".power") / "domains.yaml"
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class DomainConfigError(ValueError):
    """Raised when a domain registry cannot be trusted."""


@dataclass(frozen=True)
class DomainRule:
    """One deterministic routing rule for a domain."""

    keywords: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    types: tuple[str, ...] = ()
    weight: float = 1.0


@dataclass(frozen=True)
class DomainSpec:
    """Validated domain placement and retrieval policy."""

    name: str
    path: Path
    template: Path
    rules: tuple[DomainRule, ...]
    search_priority: tuple[str, ...]


@dataclass(frozen=True)
class DomainRegistry:
    """Validated set of domain specifications."""

    version: int
    domains: tuple[DomainSpec, ...]

    def get(self, name: str) -> DomainSpec | None:
        """Return a domain by its case-insensitive name."""
        needle = name.casefold()
        return next((domain for domain in self.domains if domain.name.casefold() == needle), None)


def domain_config_path(vault_dir: Path) -> Path:
    """Resolve the registry path, allowing an explicit path inside the vault."""
    configured_raw = os.getenv("POWER_DOMAIN_CONFIG")
    if configured_raw:
        candidate = Path(configured_raw).expanduser()
        if not candidate.is_absolute():
            candidate = vault_dir / candidate
    else:
        candidate = vault_dir / DOMAIN_CONFIG_RELATIVE_PATH
    return candidate.resolve()


def _relative_safe(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise DomainConfigError(f"domain {field} must be a non-empty relative path")
    path = Path(value.strip())
    if path.is_absolute() or ".." in path.parts:
        raise DomainConfigError(f"domain {field} must stay inside the vault: {value!r}")
    return path


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise DomainConfigError(f"domain rule {field} must be a list of strings")
    result = tuple(item.strip().casefold() for item in value if item.strip())
    if not result:
        raise DomainConfigError(f"domain rule {field} must contain a value")
    return result


def _parse_rule(raw: object) -> DomainRule:
    if not isinstance(raw, dict):
        raise DomainConfigError("domain rules must be mappings")
    keywords = raw.get("keywords", raw.get("terms", raw.get("contains")))
    tags = raw.get("tags")
    types = raw.get("types")
    try:
        weight = float(raw.get("weight", 1.0))
    except (TypeError, ValueError) as exc:
        raise DomainConfigError("domain rule weight must be numeric") from exc
    if weight <= 0:
        raise DomainConfigError("domain rule weight must be greater than zero")
    if keywords is None and tags is None and types is None:
        raise DomainConfigError("domain rule needs keywords, tags, or types")
    return DomainRule(
        keywords=_string_tuple(keywords, "keywords"),
        tags=_string_tuple(tags, "tags"),
        types=_string_tuple(types, "types"),
        weight=weight,
    )


def load_domain_registry(vault_dir: Path) -> DomainRegistry:
    """Load and validate a vault's optional domain registry.

    Missing configuration is a valid legacy state and returns an empty
    registry.  A present but malformed registry raises ``DomainConfigError``
    instead of silently falling back to a different placement policy.
    """
    config_path = domain_config_path(vault_dir)
    if not config_path.exists():
        return DomainRegistry(version=1, domains=())
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise DomainConfigError(f"cannot read domain registry {config_path}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise DomainConfigError("domain registry version must be 1")
    entries = raw.get("domains")
    if not isinstance(entries, list):
        raise DomainConfigError("domain registry domains must be a list")

    domains: list[DomainSpec] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise DomainConfigError("each domain must be a mapping")
        name = entry.get("name")
        if not isinstance(name, str) or not _SLUG_RE.fullmatch(name.strip().casefold()):
            raise DomainConfigError("domain name must be a lowercase slug")
        name = name.strip().casefold()
        if name in seen:
            raise DomainConfigError(f"duplicate domain: {name}")
        seen.add(name)
        path = _relative_safe(entry.get("path"), "path")
        template = _relative_safe(entry.get("template"), "template")
        raw_rules = entry.get("rules", [])
        if not isinstance(raw_rules, list):
            raise DomainConfigError(f"domain {name} rules must be a list")
        rules = tuple(_parse_rule(rule) for rule in raw_rules)
        priorities = entry.get("search_priority", ["fts", "semantic"])
        if not isinstance(priorities, list) or not priorities:
            raise DomainConfigError(f"domain {name} search_priority must be a non-empty list")
        normalized_priorities: list[str] = []
        for mode in priorities:
            if not isinstance(mode, str):
                raise DomainConfigError(f"domain {name} search modes must be strings")
            canonical = SEARCH_MODE_ALIASES.get(mode.casefold(), mode.casefold())
            if canonical not in SUPPORTED_SEARCH_MODES:
                raise DomainConfigError(
                    f"domain {name} requests unsupported search mode {mode!r}; "
                    f"supported modes: {', '.join(sorted(SUPPORTED_SEARCH_MODES))}"
                )
            if canonical not in normalized_priorities:
                normalized_priorities.append(canonical)
        domains.append(
            DomainSpec(
                name=name,
                path=path,
                template=template,
                rules=rules,
                search_priority=tuple(normalized_priorities),
            )
        )
    return DomainRegistry(version=1, domains=tuple(domains))


def _rule_score(rule: DomainRule, text: str, tags: set[str], note_type: str) -> float:
    score = 0.0
    for keyword in rule.keywords:
        if keyword in text:
            score += rule.weight
    score += sum(rule.weight for tag in rule.tags if tag in tags)
    if note_type.casefold() in rule.types:
        score += rule.weight
    return score


def route_domain(
    registry: DomainRegistry,
    *,
    title: str = "",
    description: str = "",
    content: str = "",
    tags: list[str] | tuple[str, ...] = (),
    note_type: str = "",
) -> DomainSpec | None:
    """Select the highest-scoring domain, preserving declaration order on ties."""
    text = " ".join((title, description, content)).casefold()
    normalized_tags = {tag.strip().casefold() for tag in tags if tag.strip()}
    scored = [
        (
            sum(_rule_score(rule, text, normalized_tags, note_type) for rule in domain.rules),
            index,
            domain,
        )
        for index, domain in enumerate(registry.domains)
    ]
    matches = [item for item in scored if item[0] > 0]
    if not matches:
        return None
    return max(matches, key=lambda item: (item[0], -item[1]))[2]


def resolve_search_policy(
    vault_dir: Path, query: str, requested_mode: str, domain_name: str | None = None
) -> tuple[str, DomainSpec | None]:
    """Resolve domain policy while leaving no-domain ``auto`` for the runtime.

    A configured domain may explicitly select its first priority. Without a
    domain, the searcher decides whether a verified dense profile is ready and
    otherwise uses FTS; policy resolution itself remains read-only.
    """
    registry = load_domain_registry(vault_dir)
    domain = registry.get(domain_name) if domain_name else None
    if domain_name and domain is None:
        raise DomainConfigError(f"unknown domain: {domain_name}")
    if domain is None and requested_mode.casefold() == "auto":
        domain = route_domain(registry, title=query, description=query, content=query)
    if requested_mode.casefold() != "auto":
        return requested_mode, domain
    return (domain.search_priority[0] if domain else "auto"), domain


def render_domain_template(template: str, values: dict[str, str]) -> str:
    """Replace only POWER placeholders, leaving ordinary Markdown braces intact."""
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def domain_template_path(vault_dir: Path, domain: DomainSpec) -> Path:
    """Return a domain template path guaranteed to be inside the vault."""
    path = (vault_dir / domain.template).resolve()
    try:
        path.relative_to(vault_dir.resolve())
    except ValueError as exc:
        raise DomainConfigError(f"domain template escapes vault: {domain.name}") from exc
    return path
