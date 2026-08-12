"""Domain registry, placement, and search-priority contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from power_framework.core.domains import (
    DomainConfigError,
    domain_template_path,
    load_domain_registry,
    render_domain_template,
    resolve_search_policy,
    route_domain,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_registry(vault: Path, body: str) -> None:
    (vault / ".power").mkdir()
    (vault / ".power" / "domains.yaml").write_text(body, encoding="utf-8")


def test_registry_routes_and_resolves_priority(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_registry(
        vault,
        """
version: 1
domains:
  - name: research
    path: 03_Resources/research
    template: 05_Templates/research.md
    rules:
      - keywords: [paper, experiment]
        weight: 2
      - tags: [science]
    search_priority: [fts, semantic]
  - name: projects
    path: 01_Projects/projects
    template: 05_Templates/project.md
    rules:
      - types: [project]
    search_priority: [reranked, fts]
""",
    )
    registry = load_domain_registry(vault)
    selected = route_domain(
        registry,
        title="Paper review",
        description="An experiment",
        tags=["science"],
        note_type="Resource",
    )
    assert selected is not None
    assert selected.name == "research"
    assert resolve_search_policy(vault, "paper", "auto")[0] == "fts"
    assert resolve_search_policy(vault, "anything", "auto", "projects")[0] == "reranked"


def test_auto_without_domain_is_deferred_to_runtime_readiness(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    assert resolve_search_policy(vault, "anything", "auto")[0] == "auto"


def test_registry_default_priority_is_fts_first(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_registry(
        vault,
        """
version: 1
domains:
  - name: notes
    path: 03_Resources/notes
    template: 05_Templates/default.md
    rules: [{keywords: [note]}]
""",
    )

    assert resolve_search_policy(vault, "note", "auto")[0] == "fts"


def test_registry_rejects_unsafe_paths_and_unknown_modes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_registry(
        vault,
        """
version: 1
domains:
  - name: unsafe
    path: ../outside
    template: 05_Templates/default.md
    rules: [{keywords: [x]}]
    search_priority: [qdrant]
""",
    )
    with pytest.raises(DomainConfigError):
        load_domain_registry(vault)


def test_template_path_and_placeholder_rendering(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_registry(
        vault,
        """
version: 1
domains:
  - name: notes
    path: 03_Resources/notes
    template: 05_Templates/notes.md
    rules: [{keywords: [note]}]
    search_priority: [fts]
""",
    )
    (vault / "05_Templates").mkdir()
    (vault / "05_Templates" / "notes.md").write_text("# {title}\n\n{{literal}}", encoding="utf-8")
    domain = load_domain_registry(vault).get("notes")
    assert domain is not None
    assert domain_template_path(vault, domain).is_file()
    assert render_domain_template("# {title} {{literal}}", {"title": "A"}) == "# A {{literal}}"


def test_explicit_config_path_is_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    custom = vault / "custom.yaml"
    custom.write_text("version: 1\ndomains: []\n", encoding="utf-8")
    monkeypatch.setenv("POWER_DOMAIN_CONFIG", str(custom))
    assert load_domain_registry(vault).domains == ()
