"""Static suite-profile guardrails for the unified Web UI presentation surface."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[3]


def test_accessibility_profile_has_focus_motion_and_form_guardrails() -> None:
    css = (ROOT / "src/power_framework/web/static/css/style.css").read_text(encoding="utf-8")
    base = (ROOT / "src/power_framework/web/templates/base.html").read_text(encoding="utf-8")
    graph = (ROOT / "src/power_framework/web/templates/graph.html").read_text(encoding="utf-8")
    search = (ROOT / "src/power_framework/web/templates/search.html").read_text(encoding="utf-8")
    decisions = (ROOT / "src/power_framework/web/templates/decisions.html").read_text(
        encoding="utf-8"
    )

    assert "transition: all" not in css
    assert "prefers-reduced-motion: reduce" in css
    assert ".skip-link" in base
    assert 'id="main-content" tabindex="-1"' in base
    assert "outline: none" not in base
    for control_id in ("graphSearchInput", "graphCategorySelect", "graphDegreeSelect"):
        assert f'for="{control_id}"' in graph
    assert 'for="searchQuery"' in search
    assert 'id="searchQuery"' in search
    assert 'for="decisionInputValue"' in decisions
    assert 'id="decisionInputValue"' in decisions


def test_deployment_profiles_keep_web_only_docker_and_shared_vault_contract() -> None:
    compose = (ROOT / "deploy" / "web" / "compose.yaml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "deploy" / "web" / "Dockerfile").read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "architecture" / "unified-runtime.md").read_text(
        encoding="utf-8"
    )

    assert "Profile A" in architecture
    assert "Profile B" in architecture
    assert '"127.0.0.1:8080:8080"' in compose
    assert ":/brain:rw" in compose
    assert "power-web-cache:/var/cache/power" in compose
    assert 'POWER_WEB_READ_ONLY_MODE: "${POWER_WEB_READ_ONLY_MODE:-false}"' in compose
    assert 'user: "${POWER_WEB_UID:-10001}:${POWER_WEB_GID:-10001}"' in compose
    assert 'ENTRYPOINT ["power-web"]' in dockerfile
    assert "POWER_WHEEL_FILE" in dockerfile
    assert "org.opencontainers.image.revision" in dockerfile
    assert "POWER_MCP_TRANSPORT" not in compose + dockerfile
