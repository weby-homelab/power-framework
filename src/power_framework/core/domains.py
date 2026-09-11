"""Opt-in domain routing and search policy for POWER vaults.

The legacy P.A.R.A. layout remains the default.  A vault can add
``.power/domains.yaml`` to make directory placement, templates, and search
priorities explicit.  The registry is deliberately small and fail-closed:
unknown retrieval modes, unsafe paths, duplicate domains, and malformed rules
are rejected before a note is written or a search policy is selected.
"""

from __future__ import annotations

import math
import os
import re
import stat
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from .domain_errors import DomainConfigError

if TYPE_CHECKING:
    from collections.abc import Hashable

    from .domain_policy import (
        DomainAuthorityPolicy,
        DomainEscalationPolicy,
        DomainIndexPolicy,
        DomainNoisePolicy,
        DomainPolicyRegistry,
        DomainPolicySpec,
        DomainQuerySignals,
        DomainRetrievalPolicy,
        DomainRoutingPolicy,
        DomainSourceSelectors,
        DomainTraversalPolicy,
        RetrievalDomainRouter,
        SourceDomainClassifier,
        SourceDomainMembership,
        load_domain_policy,
        route_query_domains,
    )

SUPPORTED_SEARCH_MODES = frozenset(
    {"fts", "vector", "hybrid", "semantic", "reranked", "graph_assisted"}
)
SEARCH_MODE_ALIASES = {"hybrid_reranked": "reranked"}
DOMAIN_CONFIG_RELATIVE_PATH = Path(".power") / "domains.yaml"
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")

# These are structural safety ceilings, not product-quality targets.  The
# router uses the policy's lower values and never raises any of these caps.
MAX_DOMAIN_CONFIG_BYTES = 256 * 1024
MAX_DOMAIN_CONFIG_NODES = 4096
MAX_DOMAINS = 32
MAX_RULES_PER_DOMAIN = 128
MAX_SELECTOR_VALUES = 64
MAX_QUERY_KEYWORDS = 64
MAX_QUERY_INTENTS = 16
MAX_POLICY_LIST = 32
MAX_POLICY_TEXT = 128
MAX_ROUTER_MATCHES = 16
MAX_ROUTER_QUERY_CHARS = 2048
MAX_SOURCE_PATH_CHARS = 1024
MAX_CONFIG_PATH_CHARS = 4096
MAX_TEMPLATE_BYTES = 128 * 1024
MAX_RULE_WEIGHT = 1_000_000.0

_V1_RULE_FIELDS = frozenset({"keywords", "terms", "contains", "tags", "types", "weight"})
_V1_DOMAIN_FIELDS = frozenset({"name", "path", "template", "rules", "search_priority"})
_V1_ROOT_FIELDS = frozenset({"version", "domains"})


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


class _StrictSafeLoader(yaml.SafeLoader):
    """Safe YAML loader with duplicate-key and node-count limits."""

    def __init__(self, stream: Any) -> None:
        super().__init__(stream)
        self._power_node_count = 0

    def compose_node(self, parent: Any, index: Any) -> Any:
        self._power_node_count += 1
        if self._power_node_count > MAX_DOMAIN_CONFIG_NODES:
            raise DomainConfigError("domain policy exceeds the YAML node bound")
        return super().compose_node(parent, index)

    def construct_mapping(self, node: Any, deep: bool = False) -> dict[Hashable, Any]:
        if not isinstance(node, yaml.MappingNode):
            raise DomainConfigError("domain policy mappings must use YAML objects")
        mapping: dict[Hashable, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise DomainConfigError("domain policy mapping keys must be strings")
            if key in mapping:
                raise DomainConfigError("domain policy contains duplicate keys")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _check_keys(raw: object, allowed: frozenset[str], context: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise DomainConfigError(f"{context} must be a mapping")
    unknown = set(raw) - allowed
    if unknown:
        raise DomainConfigError(f"{context} contains unknown fields")
    return raw


def _vault_root(vault_dir: Path) -> Path:
    try:
        root = Path(vault_dir).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise DomainConfigError("vault path cannot be resolved") from exc
    if not root.is_dir():
        raise DomainConfigError("vault path must be a directory")
    return root


def _validate_vault_path(
    root: Path,
    candidate: Path,
    *,
    label: str,
    allow_missing: bool,
    require_regular_file: bool = False,
) -> Path:
    """Return a vault-contained path while rejecting every existing symlink."""
    if any(part in {"..", ""} for part in candidate.parts):
        raise DomainConfigError(f"{label} contains an unsafe path segment")
    try:
        lexical_relative = candidate.relative_to(root)
    except ValueError as exc:
        raise DomainConfigError(f"{label} escapes the vault") from exc
    current = root
    parts = lexical_relative.parts
    for index, part in enumerate(parts):
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if not allow_missing:
                raise DomainConfigError(f"{label} is missing") from None
            break
        except (OSError, ValueError) as exc:
            raise DomainConfigError(f"{label} cannot be inspected") from exc
        if stat.S_ISLNK(info.st_mode):
            raise DomainConfigError(f"{label} cannot use symlink components")
        is_final = index == len(parts) - 1
        if not is_final and not stat.S_ISDIR(info.st_mode):
            raise DomainConfigError(f"{label} has a non-directory parent")
        if is_final and require_regular_file and not stat.S_ISREG(info.st_mode):
            raise DomainConfigError(f"{label} must be a regular file")
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise DomainConfigError(f"{label} escapes the vault") from exc
    return resolved


def _read_bounded_text(path: Path, *, label: str, max_bytes: int) -> str:
    """Read a regular file through a no-follow descriptor with a byte bound."""
    fd: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise DomainConfigError(f"{label} must be a regular file")
        if info.st_size > max_bytes:
            raise DomainConfigError(f"{label} exceeds its byte bound")
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            fd = None
            content = handle.read(max_bytes + 1)
        if len(content.encode("utf-8")) > max_bytes:
            raise DomainConfigError(f"{label} exceeds its byte bound")
        return content
    except DomainConfigError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise DomainConfigError(f"{label} cannot be read") from exc
    finally:
        if fd is not None:
            with suppress(OSError):
                os.close(fd)


def _read_bounded_vault_text(root: Path, relative: Path, *, label: str, max_bytes: int) -> str:
    """Read a vault file through descriptor-relative no-follow traversal."""
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fds: list[int] = []
    file_fd: int | None = None
    try:
        current_fd = os.open(root, directory_flags)
        directory_fds.append(current_fd)
        parts = relative.parts
        if not parts:
            raise DomainConfigError(f"{label} must name a file")
        for part in parts[:-1]:
            current_fd = os.open(part, directory_flags, dir_fd=current_fd)
            directory_fds.append(current_fd)
        file_fd = os.open(
            parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=current_fd,
        )
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise DomainConfigError(f"{label} is not a bounded regular file")
        with os.fdopen(file_fd, "r", encoding="utf-8") as handle:
            file_fd = None
            content = handle.read(max_bytes + 1)
        if len(content.encode("utf-8")) > max_bytes:
            raise DomainConfigError(f"{label} exceeds its byte bound")
        return content
    except DomainConfigError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise DomainConfigError(f"{label} cannot be read") from exc
    finally:
        if file_fd is not None:
            with suppress(OSError):
                os.close(file_fd)
        for directory_fd in reversed(directory_fds):
            with suppress(OSError):
                os.close(directory_fd)


def _load_yaml(path: Path, *, label: str, root: Path | None = None) -> object:
    if root is None:
        content = _read_bounded_text(path, label=label, max_bytes=MAX_DOMAIN_CONFIG_BYTES)
    else:
        content = _read_bounded_vault_text(
            root,
            path.relative_to(root),
            label=label,
            max_bytes=MAX_DOMAIN_CONFIG_BYTES,
        )
    try:
        raw = yaml.load(content, Loader=_StrictSafeLoader)  # noqa: S506
    except DomainConfigError:
        raise
    except (yaml.YAMLError, RecursionError) as exc:
        raise DomainConfigError(f"{label} is malformed YAML") from exc
    return raw


def _path_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainConfigError(f"domain {field} must be a non-empty relative path")
    text = value.strip()
    if len(text) > MAX_SOURCE_PATH_CHARS:
        raise DomainConfigError(f"domain {field} exceeds its length bound")
    if (
        _CONTROL_CHARACTERS.search(text)
        or "\\" in text
        or _WINDOWS_DRIVE.match(text)
        or "://" in text
        or text.casefold().startswith(("file:", "http:", "https:"))
    ):
        raise DomainConfigError(f"domain {field} contains unsafe characters")
    path = Path(text)
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        raise DomainConfigError(f"domain {field} must stay inside the vault")
    return path.as_posix()


def _bounded_weight(value: object, *, field: str, maximum: float = MAX_RULE_WEIGHT) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainConfigError(f"{field} must be numeric")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise DomainConfigError(f"{field} must be finite") from exc
    if not math.isfinite(result) or result <= 0 or result > maximum:
        raise DomainConfigError(f"{field} must be finite and bounded")
    return result


def _domain_config_path_info(vault_dir: Path) -> tuple[Path, bool]:
    root = _vault_root(vault_dir)
    configured_raw = os.environ.get("POWER_DOMAIN_CONFIG")
    explicit = bool(configured_raw)
    if configured_raw:
        if (
            _CONTROL_CHARACTERS.search(configured_raw)
            or _WINDOWS_DRIVE.match(configured_raw)
            or "://" in configured_raw
            or len(configured_raw) > MAX_CONFIG_PATH_CHARS
        ):
            raise DomainConfigError("POWER_DOMAIN_CONFIG must be a non-empty safe path")
        candidate = Path(configured_raw).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        elif not candidate.is_relative_to(root):
            raise DomainConfigError("POWER_DOMAIN_CONFIG must stay inside the vault")
    else:
        candidate = root / DOMAIN_CONFIG_RELATIVE_PATH
    return (
        _validate_vault_path(
            root,
            candidate,
            label="domain config",
            allow_missing=True,
            require_regular_file=candidate.exists(),
        ),
        explicit,
    )


def domain_config_path(vault_dir: Path) -> Path:
    """Resolve a default or explicit config path inside the canonical vault."""
    return _domain_config_path_info(vault_dir)[0]


def _relative_safe(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise DomainConfigError(f"domain {field} must be a non-empty relative path")
    return Path(_path_text(value, field))


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > MAX_SELECTOR_VALUES:
        raise DomainConfigError(f"domain rule {field} must be a list of strings")
    if any(not isinstance(item, str) for item in value):
        raise DomainConfigError(f"domain rule {field} must be a list of strings")
    result = tuple(item.strip().casefold() for item in value if item.strip())
    if not result:
        raise DomainConfigError(f"domain rule {field} must contain a value")
    if any(_CONTROL_CHARACTERS.search(item) for item in result):
        raise DomainConfigError(f"domain rule {field} contains unsafe text")
    return result


def _parse_rule(raw: object) -> DomainRule:
    raw = _check_keys(raw, _V1_RULE_FIELDS, "domain rule")
    keyword_aliases = [key for key in ("keywords", "terms", "contains") if key in raw]
    if len(keyword_aliases) > 1:
        raise DomainConfigError("domain rule keyword aliases are mutually exclusive")
    keywords = raw.get("keywords", raw.get("terms", raw.get("contains")))
    tags = raw.get("tags")
    types = raw.get("types")
    try:
        weight = _bounded_weight(raw.get("weight", 1.0), field="domain rule weight")
    except DomainConfigError:
        raise
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
    root = _vault_root(vault_dir)
    config_path, explicit = _domain_config_path_info(root)
    if not config_path.exists():
        if explicit:
            raise DomainConfigError("explicit domain registry is missing")
        return DomainRegistry(version=1, domains=())
    raw = _load_yaml(config_path, label="domain registry", root=root)
    root_fields = _check_keys(raw, _V1_ROOT_FIELDS, "domain registry")
    if type(root_fields.get("version")) is not int or root_fields.get("version") != 1:
        raise DomainConfigError("domain registry version must be 1")
    entries = root_fields.get("domains")
    if not isinstance(entries, list) or len(entries) > MAX_DOMAINS:
        raise DomainConfigError("domain registry domains must be a list")

    domains: list[DomainSpec] = []
    seen: set[str] = set()
    for entry in entries:
        entry = _check_keys(entry, _V1_DOMAIN_FIELDS, "domain")
        name = entry.get("name")
        if not isinstance(name, str) or not _SLUG_RE.fullmatch(name.strip().casefold()):
            raise DomainConfigError("domain name must be a lowercase slug")
        name = name.strip().casefold()
        if name in seen:
            raise DomainConfigError(f"duplicate domain: {name}")
        seen.add(name)
        path = _relative_safe(entry.get("path"), "path")
        template = _relative_safe(entry.get("template"), "template")
        _validate_vault_path(root, root / path, label=f"domain {name} path", allow_missing=True)
        _validate_vault_path(
            root,
            root / template,
            label=f"domain {name} template",
            allow_missing=True,
        )
        raw_rules = entry.get("rules", [])
        if not isinstance(raw_rules, list) or len(raw_rules) > MAX_RULES_PER_DOMAIN:
            raise DomainConfigError(f"domain {name} rules must be a list")
        rules = tuple(_parse_rule(rule) for rule in raw_rules)
        priorities = entry.get("search_priority", ["fts", "semantic"])
        if not isinstance(priorities, list) or not priorities or len(priorities) > MAX_POLICY_LIST:
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
    """Return an existing, bounded, regular template inside the vault."""
    root = _vault_root(vault_dir)
    return _validate_vault_path(
        root,
        root / domain.template,
        label=f"domain {domain.name} template",
        allow_missing=False,
        require_regular_file=True,
    )


def read_domain_template(vault_dir: Path, domain: DomainSpec) -> str:
    """Read a validated domain template without following a final symlink."""
    root = _vault_root(vault_dir)
    template_path = domain_template_path(root, domain)
    return _read_bounded_vault_text(
        root,
        template_path.relative_to(root),
        label=f"domain {domain.name} template",
        max_bytes=MAX_TEMPLATE_BYTES,
    )


def validate_domain_placement_path(vault_dir: Path, domain: DomainSpec) -> Path:
    """Validate a domain directory before the caller creates or writes it."""
    root = _vault_root(vault_dir)
    path = _validate_vault_path(
        root,
        root / domain.path,
        label=f"domain {domain.name} placement",
        allow_missing=True,
    )
    if path.exists() and not path.is_dir():
        raise DomainConfigError(f"domain {domain.name} placement must be a directory")
    return path


def ensure_domain_placement_path(vault_dir: Path, domain: DomainSpec) -> Path:
    """Create a validated domain directory through descriptor-relative mkdirat."""
    root = _vault_root(vault_dir)
    relative = domain.path
    _validate_vault_path(
        root,
        root / relative,
        label=f"domain {domain.name} placement",
        allow_missing=True,
    )
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fds: list[int] = []
    try:
        current_fd = os.open(root, directory_flags)
        fds.append(current_fd)
        for part in relative.parts:
            with suppress(FileExistsError):
                os.mkdir(part, 0o755, dir_fd=current_fd)
            current_fd = os.open(part, directory_flags, dir_fd=current_fd)
            fds.append(current_fd)
    except (OSError, ValueError) as exc:
        raise DomainConfigError(f"domain {domain.name} placement cannot be created") from exc
    finally:
        for fd in reversed(fds):
            with suppress(OSError):
                os.close(fd)
    return root / relative


# Phase 5B routing is kept in a separate module so the legacy v1 placement
# surface remains small and auditable.  Re-export the stable public names from
# this compatibility module for existing callers.
from .domain_policy import (  # noqa: E402,F401
    DomainAuthorityPolicy,
    DomainEscalationPolicy,
    DomainIndexPolicy,
    DomainNoisePolicy,
    DomainPolicyRegistry,
    DomainPolicySpec,
    DomainQuerySignals,
    DomainRetrievalPolicy,
    DomainRoutingPolicy,
    DomainSourceSelectors,
    DomainTraversalPolicy,
    RetrievalDomainRouter,
    SourceDomainClassifier,
    SourceDomainMembership,
    load_domain_policy,
    route_query_domains,
)
