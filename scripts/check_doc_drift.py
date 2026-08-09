#!/usr/bin/env python3
"""POWER 3.0 — Doc-Drift CI Gate (R1, fixes DOC-DRIFT / B9).

Every prior release shipped a README that disagreed with the code: README said
Qwen3 while the code defaulted to Granite; cache/model names drifted; the
"5 modes" claim outlived the code. This gate makes that class of bug fail CI.

It compares the canonical stack, executable CLI/MCP interfaces, release version,
local links, and safe onboarding patterns against the current public documentation.

Usage:
    python scripts/check_doc_drift.py                 # check all
    python scripts/check_doc_drift.py --check interfaces,onboarding,links

Checks:
    embedder  — README must name the canonical dense backend (EMBED_PROVIDER)
    reranker  — README must name the canonical reranker model
    mode      — README must name the canonical search mode
    version   — README must not reference a stale default provider
    retrieval — Architecture/API tables must match the code retrieval registry
    interfaces — CLI/MCP references and counts must match executable source
    onboarding — install/migration guides must use the current safe contract
    links      — local Markdown targets in canonical docs must exist

Exit code 0 = in sync, 1 = drift detected.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
README_UA = REPO_ROOT / "README.ua.md"
ARCHITECTURE = REPO_ROOT / "docs" / "architecture.md"
SEARCHER_API = REPO_ROOT / "docs" / "api" / "searcher.md"
RERANKER_API = REPO_ROOT / "docs" / "api" / "reranker.md"
CLI_DOC = REPO_ROOT / "docs" / "cli.md"
MCP_DOC = REPO_ROOT / "docs" / "mcp-server.md"
DOC_INDEX = REPO_ROOT / "docs" / "index.md"
GETTING_STARTED = REPO_ROOT / "docs" / "getting-started.md"
GETTING_STARTED_UA = REPO_ROOT / "docs" / "getting-started.ua.md"
WINDOWS = REPO_ROOT / "docs" / "windows-11-installation.md"
WINDOWS_UA = REPO_ROOT / "docs" / "windows-11-installation.ua.md"
MIGRATION = REPO_ROOT / "docs" / "migration-guide.md"
MIGRATION_UA = REPO_ROOT / "docs" / "migration-guide.ua.md"
HIERARCHICAL = REPO_ROOT / "docs" / "hierarchical-index-migration.md"
HIERARCHICAL_UA = REPO_ROOT / "docs" / "hierarchical-index-migration.ua.md"
INVENTORY_UA = REPO_ROOT / "docs" / "documentation-inventory.ua.md"
AGENT_INSTRUCTIONS = REPO_ROOT / ".agents" / "AGENTS.md"
AGENT_SKILL = REPO_ROOT / "skills" / "power" / "SKILL.md"
WORKSPACE_AGENT_SKILL = REPO_ROOT / ".agents" / "skills" / "power" / "SKILL.md"
HOLISTIC_SKILL = REPO_ROOT / ".agents" / "skills" / "holistic-analysis" / "SKILL.md"
CURRENT_DOCUMENTS = {
    "README": README,
    "README.ua": README_UA,
    "Architecture": ARCHITECTURE,
    "Searcher API": SEARCHER_API,
    "Reranker API": RERANKER_API,
    "CLI": CLI_DOC,
    "MCP": MCP_DOC,
    "Docs index": DOC_INDEX,
    "Getting Started": GETTING_STARTED,
    "Getting Started UA": GETTING_STARTED_UA,
    "Windows": WINDOWS,
    "Windows UA": WINDOWS_UA,
    "Migration": MIGRATION,
    "Migration UA": MIGRATION_UA,
    "Hierarchical report": HIERARCHICAL,
    "Hierarchical report UA": HIERARCHICAL_UA,
    "Documentation inventory UA": INVENTORY_UA,
    "Agent instructions": AGENT_INSTRUCTIONS,
    "Agent skill": AGENT_SKILL,
    "Workspace agent skill": WORKSPACE_AGENT_SKILL,
    "Holistic skill": HOLISTIC_SKILL,
}

# Canonical provider -> the human-readable token(s) the README MUST contain to
# be considered "in sync". Whichever provider the code declares as default, the
# README must advertise it (and must NOT still advertise a superseded default).
_PROVIDER_ALIASES: dict[str, list[str]] = {
    "bge-m3": ["bge-m3", "BGE-M3"],
    "qwen3": ["Qwen3-Embedding", "Qwen3-0.6B"],
    "fastembed": ["MiniLM", "Granite", "granite"],
    "ollama": ["ollama"],
}

# Superseded defaults that must NOT be described as "default" once we moved on.
_STALE_DEFAULT_MARKERS = {
    "bge-m3": [
        r"[Dd]efault backend .{0,40}Qwen3-Embedding",
        r"[Dd]efault .{0,40}Granite",
        r"default provider is now ``qwen3``",
    ],
}


def _load_code_facts() -> dict[str, Any]:
    """Load the canonical runtime manifest; this gate only consumes facts."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from power_framework.core.capabilities import manifest

    return manifest()


def _read_current_documents() -> dict[str, str]:
    """Read the documentation that describes the current executable contract."""
    documents: dict[str, str] = {}
    for label, path in CURRENT_DOCUMENTS.items():
        if not path.exists():
            print(f"::error:: {label} not found at {path}", file=sys.stderr)
            sys.exit(2)
        documents[label] = path.read_text(encoding="utf-8")
    return documents


def check_embedder(readme: str, provider: str) -> list[str]:
    errors: list[str] = []
    aliases = _PROVIDER_ALIASES.get(provider, [provider])
    if not any(a in readme for a in aliases):
        errors.append(
            f"README does not advertise the canonical embedder "
            f"'{provider}' (expected one of {aliases}). "
            f"Update README's search/embedding sections."
        )
    errors.extend(
        f"README still describes a SUPERSEDED default embedder "
        f"(matched /{pat}/) while code default is '{provider}'."
        for pat in _STALE_DEFAULT_MARKERS.get(provider, [])
        if re.search(pat, readme)
    )
    return errors


def check_reranker(readme: str, model: str) -> list[str]:
    # Match on the model's short name (last path segment) to survive org renames.
    short = model.rsplit("/", 1)[-1]
    if short not in readme and model not in readme:
        return [
            f"README does not name the canonical reranker '{model}' "
            f"(short name '{short}'). Update the Cross-Encoder Reranker row."
        ]
    return []


def check_version(readme: str, provider: str) -> list[str]:
    # Guard against the classic "default provider is now qwen3" line lingering
    # after a provider swap.
    errors: list[str] = []
    if provider != "qwen3" and "default provider is now ``qwen3``" in readme:
        errors.append(
            "README/CHANGELOG claims qwen3 is the default provider, but the "
            f"code default is '{provider}'."
        )
    return errors


def check_mode(readme: str, mode: str) -> list[str]:
    # The canonical search mode declared in code (search_vault default) must be
    # advertised in the README, and a stale "5 modes" / old default must not
    # linger. Prevents the classic "mode claim outlived the code" doc-drift.
    if mode not in readme and f"`{mode}`" not in readme:
        return [
            f"README does not name the canonical search mode '{mode}' "
            f"(the code default for search_vault). Update the search section."
        ]
    return []


def check_retrieval_registry(documents: dict[str, str], facts: dict[str, Any]) -> list[str]:
    """Require the generated architecture table to equal the code registry."""
    errors: list[str] = []
    search = facts["search"]
    models = facts["models"]
    architecture = documents["Architecture"]
    expected_header = "| Mode | Candidate sources | Fusion | Reranker | Requires dense index |"
    if expected_header not in architecture:
        errors.append("Architecture is missing the canonical retrieval-registry table header.")
    for spec in search["registry"]:
        mode = spec["mode"]
        sources = " + ".join(spec["candidate_sources"])
        fusion = spec["fusion"] or "—"
        reranker = "yes" if spec["reranker"] else "no"
        dense = "yes" if spec["requires_dense_index"] else "no"
        fusion_cell = f"`{fusion}`" if fusion != "—" else fusion
        expected_row = f"| `{mode}` | `{sources}` | {fusion_cell} | {reranker} | {dense} |"
        if expected_row not in architecture:
            errors.append(
                f"Architecture retrieval row does not match code registry: {expected_row}"
            )
    expected_default = f"The current default is `{search['default_mode']}`"
    if expected_default not in architecture:
        errors.append(f"Architecture does not declare the code default `{search['default_mode']}`.")
    for key, label in (("embedding_model", "embedding"), ("reranker_model", "reranker")):
        if models[key] not in architecture:
            errors.append(
                f"Architecture does not name the pinned canonical {label} model `{models[key]}`."
            )

    searcher_api = documents["Searcher API"]
    if f"The current default is `{search['default_mode']}`, not `reranked`." not in searcher_api:
        errors.append(
            "Searcher API does not declare the current semantic default and reranked opt-in."
        )

    stale_claims = {
        "README": (
            "canonical Jina v2 reranker remains the fallback",
            "**`jina-reranker-v2-base-multilingual`** (default)",
        ),
        "README.ua": (
            "канонічний Jina v2 реранкер залишається fallback",
            "**`jina-reranker-v2-base-multilingual`** (за замовчуванням)",
        ),
        "Architecture": ("Jina v2 multilingual default",),
        "Searcher API": (
            "`reranked` (canonical, default",
            "Jina v2 cross-encoder rerank",
            "`semantic` (alias of `vector`)",
        ),
    }
    for label, claims in stale_claims.items():
        errors.extend(
            f"{label} contains a superseded retrieval/model claim: {claim!r}."
            for claim in claims
            if claim in documents[label]
        )
    return errors


def check_interfaces(documents: dict[str, str], facts: dict[str, Any]) -> list[str]:
    """Require public interface inventories to match executable source exactly."""
    errors: list[str] = []
    interfaces = facts["interfaces"]
    cli_commands = interfaces["cli_commands"]
    mcp_tools = interfaces["mcp_tools"]
    mcp_contracts = interfaces["mcp_tool_contracts"]
    if len(cli_commands) != len(set(cli_commands)):
        errors.append("CLI source contains duplicate top-level command declarations.")
    if len(mcp_tools) != len(set(mcp_tools)):
        errors.append("MCP source contains duplicate tool declarations.")
    contract_names = [contract.get("name") for contract in mcp_contracts]
    if contract_names != mcp_tools:
        errors.append("MCP capability contracts do not match the executable tool inventory.")
    for contract in mcp_contracts:
        name = contract.get("name", "<unknown>")
        annotations = contract.get("annotations", {})
        risk = contract.get("risk", {})
        errors.extend(
            f"MCP tool `{name}` is missing boolean annotation `{field}`."
            for field in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
            if not isinstance(annotations.get(field), bool)
        )
        errors.extend(
            f"MCP tool `{name}` is missing risk field `{field}`."
            for field in ("local_only", "egress", "approval")
            if field not in risk
        )

    errors.extend(
        f"CLI reference is missing executable command `power {command}`."
        for command in cli_commands
        if f"### `{command}`" not in documents["CLI"]
    )
    errors.extend(
        f"MCP reference is missing executable tool `{tool}`."
        for tool in mcp_tools
        if f"`{tool}`" not in documents["MCP"]
    )

    for label in ("README", "README.ua", "Docs index", "Architecture"):
        cli_count = re.search(rf"(?:all )?{len(cli_commands)} .*commands", documents[label], re.I)
        cli_count = cli_count or f"{len(cli_commands)} команд" in documents[label]
        if not cli_count:
            errors.append(f"{label} does not declare all {len(cli_commands)} CLI commands.")
        mcp_count = re.search(rf"{len(mcp_tools)}(?:[- ]+)?(?:MCP )?tools?", documents[label], re.I)
        mcp_count = mcp_count or f"{len(mcp_tools)} інструмент" in documents[label]
        if not mcp_count:
            errors.append(f"{label} does not declare all {len(mcp_tools)} MCP tools.")
        numeric_mcp_claims = re.findall(
            r"\b(\d+)(?:[- ]+)?(?:Async )?MCP tools?\b", documents[label], re.I
        )
        numeric_mcp_claims.extend(
            re.findall(r"\b(\d+)\s+MCP[- ]?інструмент(?:ів)?", documents[label], re.I)
        )
        numeric_mcp_claims.extend(
            re.findall(r"\b(\d+)\s+інструмент(?:ів)?", documents[label], re.I)
        )
        errors.extend(
            f"{label} contains stale MCP tools count `{claim}`; expected `{len(mcp_tools)}`."
            for claim in numeric_mcp_claims
            if int(claim) != len(mcp_tools)
        )
    for label in ("Getting Started", "Getting Started UA"):
        mcp_count = re.search(rf"{len(mcp_tools)}(?:[- ]+)?(?:MCP )?tools?", documents[label], re.I)
        mcp_count = mcp_count or f"{len(mcp_tools)} інструмент" in documents[label]
        if not mcp_count:
            errors.append(f"{label} does not declare all {len(mcp_tools)} MCP tools.")
    mcp_count = re.search(rf"{len(mcp_tools)} .*tools", documents["MCP"], re.I)
    if not mcp_count:
        errors.append(f"MCP does not declare all {len(mcp_tools)} MCP tools.")
    inventory = documents["Documentation inventory UA"]
    if not re.search(rf"\| `docs/cli\.md` \|.*\| {len(cli_commands)} команд \|", inventory):
        errors.append("Documentation inventory UA does not declare the current CLI count.")
    if not re.search(
        rf"\| `docs/mcp-server\.md` \|.*\| {len(mcp_tools)} інструментів \|",
        inventory,
    ):
        errors.append("Documentation inventory UA does not declare the current MCP count.")
    expected_inventory_history = (
        f"- `12` MCP-інструментів замінено на фактичні `{len(mcp_tools)}`; "
        f"CLI задокументовано як `{len(cli_commands)}`"
    )
    if expected_inventory_history not in inventory:
        errors.append("Documentation inventory UA contains a stale historical interface count.")
    holistic = documents["Holistic skill"]
    if f"all {len(mcp_tools)} MCP tools" not in holistic:
        errors.append(f"Holistic skill does not declare all {len(mcp_tools)} MCP tools.")
    if re.search(r"all 12 MCP tools", holistic):
        errors.append("Holistic skill contains a stale MCP tools count.")
    if f"{len(mcp_tools)} tools" not in documents["Agent instructions"]:
        errors.append(f"Agent instructions do not declare `{len(mcp_tools)} tools`.")

    for label in ("Agent skill", "Workspace agent skill"):
        errors.extend(
            _check_agent_skill(
                label,
                documents[label],
                cli_commands,
                mcp_tools,
                facts["version"],
            )
        )

    external_skill = Path(
        os.getenv(
            "POWER_GLOBAL_SKILL_PATH",
            str(Path.home() / ".opencode" / "skills" / "power" / "SKILL.md"),
        )
    )
    if external_skill.is_file():
        try:
            external_text = external_skill.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"Global agent skill could not be read: {exc}.")
        else:
            errors.extend(
                _check_agent_skill(
                    "Global OpenCode skill",
                    external_text,
                    cli_commands,
                    mcp_tools,
                    facts["version"],
                )
            )
            if external_text != documents["Agent skill"]:
                errors.append(
                    "Global OpenCode skill is not byte-identical to the repository Agent skill."
                )
    return errors


def _check_agent_skill(
    label: str,
    skill: str,
    cli_commands: tuple[str, ...],
    mcp_tools: tuple[str, ...],
    version: str,
) -> list[str]:
    """Check every agent-loaded skill copy against the executable contract."""
    errors: list[str] = []
    prefix = f"{label}"
    cli_section = skill.split("### MCP Tools", 1)[0]
    mcp_section = skill.split("### MCP Tools", 1)[1].split("**Записав", 1)[0]
    if f"{len(mcp_tools)} tools" not in skill and f"MCP Tools ({len(mcp_tools)})" not in skill:
        errors.append(f"{prefix} does not declare `{len(mcp_tools)} tools`.")
    if not re.search(rf"CLI[^\n]*\b{len(cli_commands)}\b", skill):
        errors.append(f"{prefix} does not declare all {len(cli_commands)} CLI commands.")
    errors.extend(
        f"{prefix} is missing executable CLI command `power {command}`."
        for command in cli_commands
        if f"`power {command}" not in cli_section
    )
    errors.extend(
        f"{prefix} is missing executable tool `{tool}`."
        for tool in mcp_tools
        if f"`{tool}`" not in mcp_section
    )
    if not re.search(rf"^version:\s*{re.escape(version)}\s*$", skill, re.M):
        errors.append(f"{prefix} frontmatter does not declare version {version}.")
    for pattern, description in {
        r"/root/": "absolute path from a foreign machine",
        r"POWER_VAULT_PATH": "legacy MCP vault variable",
    }.items():
        if re.search(pattern, skill):
            errors.append(f"{prefix} contains a forbidden {description}.")
    for pattern, description, marker in (
        (r"### Крок 2.*?```bash\s*power index\b", "index command", "power index"),
        (r"### Крок 4.*?```bash\s*power lint\b", "lint command", "power lint"),
        (
            r"power sync[^\n]*--accept-dense-loss",
            "explicit dense-loss policy",
            "--accept-dense-loss",
        ),
    ):
        if not re.search(pattern, skill, re.DOTALL):
            errors.append(f"{prefix} is missing the current {description} marker `{marker}`.")
    return errors


def check_onboarding(documents: dict[str, str], facts: dict[str, Any]) -> list[str]:
    """Reject stale, moving, or unsafe setup and migration recipes."""
    errors: list[str] = []
    onboarding_labels = (
        "README",
        "README.ua",
        "Getting Started",
        "Getting Started UA",
        "Windows",
        "Windows UA",
        "Migration",
        "Migration UA",
    )
    combined = "\n".join(documents[label] for label in onboarding_labels)
    version = facts["version"]
    if f"power_framework-{version}-py3-none-any.whl" not in combined:
        errors.append(f"Onboarding docs do not pin the release wheel for version {version}.")

    forbidden = {
        r"git reset --hard": "destructive reset recipe",
        r"pip[^\n]*--break-system-packages": "system-package bypass",
        r"%USERPROFILE%": "cmd.exe variable used in PowerShell",
        r'"command"\s*:\s*"py"': "unscoped MCP Python launcher",
        r"POWER_VAULT_PATH": "legacy MCP vault variable",
        r"git\+https://github\.com/[^\s'\"]+\.git(?:@main)?(?=[\s'\"]|$)": (
            "moving Git installation target"
        ),
    }
    for label in onboarding_labels:
        for pattern, description in forbidden.items():
            if re.search(pattern, documents[label], flags=re.IGNORECASE):
                errors.append(f"{label} contains a forbidden {description}.")

    for label in ("Windows", "Windows UA"):
        windows_doc = documents[label]
        errors.extend(
            f"{label} is missing required acceptance marker `{marker}`."
            for marker in ("Windows 11 25H2", "26200", "POWER_VAULT_DIR", "--fts-only")
            if marker not in windows_doc
        )
    for label in ("Migration", "Migration UA"):
        migration_doc = documents[label]
        errors.extend(
            f"{label} is missing migration gate `{marker}`."
            for marker in ("SHA-256", "--strict", "rollback")
            if marker.lower() not in migration_doc.lower()
        )
    errors.extend(check_migration_guide(documents, facts))
    return errors


def check_migration_guide(documents: dict[str, str], facts: dict[str, Any]) -> list[str]:
    """Keep the migration guide's versioned safety claims executable and current."""
    errors: list[str] = []
    version = facts["version"]
    mcp_count = len(facts["interfaces"]["mcp_tools"])
    default_mode = facts["search"]["default_mode"]
    required_markers = {
        "Migration": (
            f"v{version}",
            f"{mcp_count} MCP tools",
            f"default search mode is `{default_mode}`",
            "power doctor DESTINATION",
            "--json",
            "--policy quarantine",
            "x-status",
            "x-related",
            "does not promise a complete rewrite",
            "not wikilinks",
        ),
        "Migration UA": (
            f"v{version}",
            f"{mcp_count} MCP tools",
            f"режим пошуку за замовчуванням — `{default_mode}`",
            "power doctor DESTINATION",
            "--json",
            "--policy quarantine",
            "x-status",
            "x-related",
            "не гарантує повний rewrite",
            "але не ремонтує wikilinks",
        ),
    }
    for label, markers in required_markers.items():
        document = documents[label]
        errors.extend(
            f"{label} is missing versioned executable migration fact `{marker}`."
            for marker in markers
            if marker not in document
        )

    stale_claims = {
        r"\b(?:12|17) MCP tools?\b": "stale MCP tool count",
        r"\b(?:12|17) MCP[- ]інструмент": "stale MCP tool count",
        r"reranked.{0,40}(?:canonical|default|канонічн|за замовчуванням)": (
            "reranked presented as the default"
        ),
        r"\.power_search\.db": "hard-coded legacy database path",
        r"HF_HUB_DISABLE_SYMLINKS": "obsolete manual symlink workaround",
        r"(?:3-6|3\u20136)\s*KB": "unbounded catalog-size promise",
        r"(?:2-3|2\u20133)\s*GB": "unverified VRAM promise",
    }
    for label in ("Migration", "Migration UA"):
        document = documents[label]
        errors.extend(
            f"{label} contains {description} (matched /{pattern}/)."
            for pattern, description in stale_claims.items()
            if re.search(pattern, document, flags=re.IGNORECASE)
        )
    return errors


def _markdown_targets(text: str) -> list[str]:
    """Extract link/image destinations after removing fenced examples."""
    without_fences = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    without_code = re.sub(r"`[^`\n]+`", "", without_fences)
    return re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", without_code)


def check_links(documents: dict[str, str], _facts: dict[str, Any]) -> list[str]:
    """Require every repository-local Markdown destination to resolve."""
    errors: list[str] = []
    for label, text in documents.items():
        source = CURRENT_DOCUMENTS[label]
        for raw_target in _markdown_targets(text):
            target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            path_part = unquote(target.split("#", 1)[0].split("?", 1)[0])
            resolved = (source.parent / path_part).resolve()
            if not resolved.exists():
                errors.append(f"{label} has a missing local link `{target}`.")
    return errors


CHECKS = {
    "embedder": lambda r, f: check_embedder(r, f["models"]["embedder"]),
    "reranker": lambda r, f: check_reranker(r, f["models"]["reranker"]),
    "mode": lambda r, f: check_mode(r, f["search"]["default_mode"]),
    "version": lambda r, f: check_version(r, f["models"]["embedder"]),
    "retrieval": check_retrieval_registry,
    "interfaces": check_interfaces,
    "onboarding": check_onboarding,
    "links": check_links,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="POWER doc-drift gate")
    parser.add_argument(
        "--check",
        default="embedder,reranker,mode,version,retrieval,interfaces,onboarding,links",
        help="comma-separated checks to run (default: all)",
    )
    args = parser.parse_args()
    requested = [c.strip() for c in args.check.split(",") if c.strip()]

    facts = _load_code_facts()
    documents = _read_current_documents()
    readme = documents["README"]

    all_errors: list[str] = []
    for name in requested:
        fn = CHECKS.get(name)
        if fn is None:
            print(f"::warning:: unknown check '{name}' skipped", file=sys.stderr)
            continue
        if name in {"retrieval", "interfaces", "onboarding", "links"}:
            all_errors.extend(fn(documents, facts))
        else:
            all_errors.extend(fn(readme, facts))

    if all_errors:
        print("Doc-drift detected:\n", file=sys.stderr)
        for e in all_errors:
            print(f"  - {e}", file=sys.stderr)
        print(
            f"\nCode facts: embedder={facts['models']['embedder']!r} "
            f"reranker={facts['models']['reranker']!r} "
            f"mode={facts['search']['default_mode']!r}",
            file=sys.stderr,
        )
        return 1

    print(
        f"Doc-drift check passed: current public docs match code "
        f"(embedder={facts['models']['embedder']}, "
        f"reranker={facts['models']['reranker'].rsplit('/', 1)[-1]}, "
        f"mode={facts['search']['default_mode']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
