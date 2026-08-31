"""Hermetic unit tests for host-side P.O.W.E.R runtime audit and update CLI."""

from __future__ import annotations

import hashlib
import io
import json
import urllib.error
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from scripts.prxmx_power_runtime_audit import (
    ALLOWED_SKILL_DIRECTORIES,
    ALLOWED_SKILL_EXTENSIONS,
    ALLOWED_SKILL_TARGET_ROOTS,
    ALLOWED_SKILL_TOP_LEVEL_FILES,
    DEFAULT_MCP_CONFIGS,
    DEFAULT_SKILL_TARGETS,
    DEFAULT_VAULT,
    DEFAULT_VENV_ROOTS,
    MAX_RELEASE_WHEEL_BYTES,
    MAX_WRAPPER_DEPTH,
    AuditReport,
    ProcessLock,
    ReleasePayload,
    ReleaseValidationError,
    SkillAuditResult,
    VenvAuditResult,
    _extract_exec_python_from_wrapper,
    _extract_exec_target_from_wrapper,
    _extract_wheel_skill_tree,
    _read_pyproject_version_from_text,
    aggregate_tree_hash,
    apply_skill_update,
    apply_venv_update,
    audit_mcp_config,
    audit_skill,
    audit_venv,
    compare_versions,
    discover_bounded_venvs,
    download_and_verify_wheel,
    extract_skill_version,
    fetch_release_payload,
    find_venv_pip,
    find_venv_python,
    format_human_report,
    get_venv_power_framework_version,
    has_jsonc_comments,
    is_allowed_skill_target,
    is_managed_skill_tree,
    is_python_interpreter,
    is_safe_skill_relative_path,
    is_system_prefix,
    main,
    parse_version,
    persist_state_report,
    record_brain_log,
    redact_secrets,
    resolve_mcp_runtime,
    run_audit,
    sha256_file,
    strip_jsonc_comments,
    tree_from_directory,
)


def _add_published_manifest_asset(
    release_json: dict[str, Any], manifest_json: dict[str, Any], tag: str = "v3.7.8"
) -> None:
    """Add the exact public manifest asset expected by the GitHub fetch contract."""
    manifest_bytes = json.dumps(manifest_json).encode("utf-8")
    release_json["assets"].append(
        {
            "name": "power-release-manifest.json",
            "browser_download_url": (
                f"https://github.com/weby-homelab/power-framework/releases/download/{tag}/"
                "power-release-manifest.json"
            ),
            "digest": f"sha256:{hashlib.sha256(manifest_bytes).hexdigest()}",
        }
    )


# ============================================================================
# 1. Version Parsing and Prerelease Comparison Tests
# ============================================================================


def test_parse_version_semver_and_pep440() -> None:
    assert parse_version("3.7.8")[0] == (3, 7, 8)
    assert parse_version("v3.7.8")[0] == (3, 7, 8)
    assert parse_version("3.7.8.post1")[1] == 1  # post release phase
    assert parse_version("3.7.8.post1")[3] == 1  # post release number
    assert parse_version("3.8.0a2")[1] == -3  # alpha phase
    assert parse_version("3.8.0a2")[2] == 2  # alpha number
    assert parse_version("  v1.0.0-beta.1  ")[1] == -2  # beta phase
    assert parse_version("  v1.0.0-beta.1  ")[2] == 1  # beta number
    assert parse_version("3.8.0.dev3")[1] == -4  # dev phase
    assert parse_version("3.8.0.dev3")[2] == 3  # dev number
    assert parse_version("3.8.0rc1")[1] == -1  # rc phase
    assert parse_version("invalid")[0] == (0,)


def test_compare_versions_prerelease_and_postrelease_ordering() -> None:
    # PEP 440 order: dev < alpha < beta < rc < stable < post
    assert compare_versions("3.8.0.dev1", "3.8.0a1") == -1
    assert compare_versions("3.8.0a1", "3.8.0a2") == -1
    assert compare_versions("3.8.0a2", "3.8.0b1") == -1
    assert compare_versions("3.8.0b1", "3.8.0rc1") == -1
    assert compare_versions("3.8.0rc1", "3.8.0") == -1
    assert compare_versions("3.8.0", "3.8.0.post1") == -1
    assert compare_versions("3.8.0.post1", "3.8.1") == -1

    # Symmetry
    assert compare_versions("3.8.0", "3.8.0rc1") == 1
    assert compare_versions("3.8.0a2", "3.8.0.dev1") == 1
    assert compare_versions("3.8.0.post1", "3.8.0") == 1

    # Stable equivalence
    assert compare_versions("3.7.8", "3.7.8") == 0
    assert compare_versions("3.7.0", "3.7") == 0
    assert compare_versions("3.7.7", "3.7.8") == -1
    assert compare_versions("3.8.0", "3.7.8") == 1
    assert compare_versions("3.10.0", "3.9.9") == 1


# ============================================================================
# 2. Tokenizer-Based JSONC Comment Detection Tests
# ============================================================================


def test_has_jsonc_comments_tokenizer() -> None:
    # True positives: actual comments outside strings
    assert has_jsonc_comments('{\n  // single line comment\n  "key": "val"\n}') is True
    assert has_jsonc_comments('{\n  /* multi\n line */\n  "key": "val"\n}') is True
    assert has_jsonc_comments('{"a": 1} // trailing comment') is True
    assert has_jsonc_comments('{"a": 1} /* inline */') is True

    # False positive guards: // or /* inside JSON strings
    assert has_jsonc_comments('{\n  "url": "https://example.com/foo//bar"\n}') is False
    assert has_jsonc_comments('{\n  "path": "/root//data/*"\n}') is False
    assert has_jsonc_comments('{\n  "text": "This is // not a comment"\n}') is False
    assert has_jsonc_comments('{\n  "text": "/* also not a comment */"\n}') is False
    assert has_jsonc_comments('{\n  "escaped": "Quote \\" and // still in string"\n}') is False
    assert has_jsonc_comments('{"clean": true}') is False


def test_strip_jsonc_comments_tokenizer() -> None:
    raw_jsonc = """{
      // Header comment
      "name": "power", /* inline block comment */
      "endpoint": "https://example.com/api//v1",
      "path": "/root//data/*",
      "escaped_quote": "Quote \\" with // inside",
      "escaped_backslash": "Path C:\\\\ // not a comment",
      "block_in_string": "/* not a comment */",
      /* Multi-line
         block comment
         with * and / symbols ***/
      "mcp": {
        "command": "power-mcp" // trailing comment
      }
      // EOF comment without trailing newline
    }"""
    stripped = strip_jsonc_comments(raw_jsonc)
    data = json.loads(stripped)
    assert data["name"] == "power"
    assert data["endpoint"] == "https://example.com/api//v1"
    assert data["path"] == "/root//data/*"
    assert data["escaped_quote"] == 'Quote " with // inside'
    assert data["escaped_backslash"] == "Path C:\\ // not a comment"
    assert data["block_in_string"] == "/* not a comment */"
    assert data["mcp"]["command"] == "power-mcp"


# ============================================================================
# 3. Default PRXMX MCP Configs Hardening Tests
# ============================================================================


def test_default_mcp_configs_matches_prxmx_canonical_paths() -> None:
    home = str(Path.home())
    expected = [
        f"{home}/.config/opencode/opencode.jsonc",
        f"{home}/.gemini/config/mcp_config.json",
        f"{home}/.codex/config.toml",
        f"{home}/.codex/mcp.json",
    ]
    assert expected == DEFAULT_MCP_CONFIGS
    # Ensure stale nonexistent Gemini settings paths are not present
    assert f"{home}/.gemini/settings.json" not in DEFAULT_MCP_CONFIGS
    assert f"{home}/.gemini/antigravity-cli/settings.json" not in DEFAULT_MCP_CONFIGS


def test_default_audit_paths_are_home_relative_and_not_host_specific() -> None:
    home = Path.home()
    assert home / "brain" == DEFAULT_VAULT
    assert all(Path(path).is_relative_to(home) for path in DEFAULT_VENV_ROOTS)
    assert all(Path(path).is_relative_to(home) for path in DEFAULT_SKILL_TARGETS)
    assert all(path.is_relative_to(home) for path in ALLOWED_SKILL_TARGET_ROOTS)

    source = Path(__file__).resolve().parents[1] / "scripts" / "prxmx_power_runtime_audit.py"
    source_text = source.read_text(encoding="utf-8")
    assert "/root/geminicli" not in source_text


# ============================================================================
# 4. pyproject.toml Parsing with tomllib
# ============================================================================


def test_read_pyproject_version_from_text() -> None:
    # Standard [project] table
    content1 = '[project]\nname = "power-framework"\nversion = "3.7.8"\n'
    assert _read_pyproject_version_from_text(content1) == "3.7.8"

    # Poetry table fallback
    content2 = '[tool.poetry]\nname = "power-framework"\nversion = "3.8.0a1"\n'
    assert _read_pyproject_version_from_text(content2) == "3.8.0a1"

    # Invalid TOML
    with pytest.raises(ReleaseValidationError, match=r"Invalid pyproject\.toml TOML"):
        _read_pyproject_version_from_text("[project\nversion = invalid")

    # Missing version field
    with pytest.raises(ReleaseValidationError, match=r"missing project\.version"):
        _read_pyproject_version_from_text('[project]\nname = "power-framework"\n')


# ============================================================================
# 5. Tree Hashing, Directory Scanning, and Redaction Tests
# ============================================================================


def test_aggregate_tree_hash_is_deterministic() -> None:
    files1 = {
        "SKILL.md": b"---\nname: power\nversion: 3.7.8\n---\n",
        "references/workflow.md": b"# Workflow\n",
    }
    files2 = {
        "references/workflow.md": b"# Workflow\n",
        "SKILL.md": b"---\nname: power\nversion: 3.7.8\n---\n",
    }
    assert aggregate_tree_hash(files1) == aggregate_tree_hash(files2)
    assert len(aggregate_tree_hash(files1)) == 64


def test_tree_from_directory_ignores_bytecode_and_symlinks(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "ref.md").write_text("# Ref\n", encoding="utf-8")

    pycache = skill_dir / "__pycache__"
    pycache.mkdir()
    (pycache / "module.cpython-313.pyc").write_bytes(b"bytecode")
    (skill_dir / "stray.pyc").write_bytes(b"bytecode")

    # Symlink inside directory should be ignored
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("secret", encoding="utf-8")
    symlink_file = skill_dir / "link.txt"
    symlink_file.symlink_to(secret_file)

    tree = tree_from_directory(skill_dir)
    assert "SKILL.md" in tree
    assert "references/ref.md" in tree
    assert "__pycache__/module.cpython-313.pyc" not in tree
    assert "stray.pyc" not in tree
    assert "link.txt" not in tree


def test_sha256_file(tmp_path: Path) -> None:
    f = tmp_path / "sample.txt"
    f.write_text("Hello POWER\n", encoding="utf-8")
    expected = "115f7a56f31fd80f08e658904b713c0372c8182a45aac1ace319ec5f2bdc9c4f"
    assert sha256_file(f) == expected


def test_redact_secrets() -> None:
    raw1 = "Authorization: Bearer token=<set-via-env>"
    assert "token=<set-via-env>" not in redact_secrets(raw1)
    assert "[REDACTED]" in redact_secrets(raw1)

    raw2 = "Error: password: <set-via-env> on host"
    assert "<set-via-env>" not in redact_secrets(raw2)


# ============================================================================
# 6. Release Payload Fetching, Wheel Extraction & Fallback Protection
# ============================================================================


def test_fetch_local_release_supports_agents_skills_power(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "power-framework"\nversion = "3.7.8"\n',
        encoding="utf-8",
    )
    # Source skill in .agents/skills/power
    skill_dir = repo / ".agents" / "skills" / "power"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: power\nversion: 3.7.8\n---\n",
        encoding="utf-8",
    )

    payload = fetch_release_payload(source_dir=repo)
    assert payload.version == "3.7.8"
    assert "SKILL.md" in payload.skill_files


def test_fetch_local_release_prerelease_for_latest_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "power-framework"\nversion = "3.8.0rc1"\n',
        encoding="utf-8",
    )
    with pytest.raises(ReleaseValidationError, match="not a stable release"):
        fetch_release_payload(source_dir=repo, ref="latest")


def test_fetch_local_release_manifest_schema_mismatch_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "power-framework"\nversion = "3.7.8"\n',
        encoding="utf-8",
    )
    rel_dir = repo / "release"
    rel_dir.mkdir()
    (rel_dir / "power-release-manifest.json").write_text(
        json.dumps({"schema": "invalid.schema.v99", "version": "3.7.8"}),
        encoding="utf-8",
    )
    with pytest.raises(ReleaseValidationError, match="Unsupported release manifest schema"):
        fetch_release_payload(source_dir=repo)


def test_fetch_local_release_candidate_template_does_not_bind_final_artifacts(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "power-framework"\nversion = "3.7.8"\n',
        encoding="utf-8",
    )
    release_dir = repo / "release"
    release_dir.mkdir()
    (release_dir / "power-release-manifest.json").write_text(
        json.dumps(
            {
                "schema": "power.release.manifest.template.v1",
                "authority": "candidate-only",
                "version": "3.7.8",
                "artifacts": {"power_wheel": {"filename": "stale.whl", "sha256": "0" * 64}},
            }
        ),
        encoding="utf-8",
    )

    payload = fetch_release_payload(source_dir=repo)

    assert payload.manifest == {}
    assert payload.wheel_filename is None
    assert payload.wheel_sha256 is None


def test_fetch_local_release_wheel_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "power-framework"\nversion = "3.7.8"\n',
        encoding="utf-8",
    )
    rel_dir = repo / "release"
    rel_dir.mkdir()
    manifest_data = {
        "schema": "power.release.manifest.v1",
        "version": "3.7.8",
        "artifacts": {
            "power_wheel": {
                "filename": "power_framework-3.7.8-py3-none-any.whl",
                "sha256": "0" * 64,
            }
        },
    }
    (rel_dir / "power-release-manifest.json").write_text(
        json.dumps(manifest_data),
        encoding="utf-8",
    )
    dist_dir = repo / "dist"
    dist_dir.mkdir()
    (dist_dir / "power_framework-3.7.8-py3-none-any.whl").write_bytes(b"corrupted content")

    with pytest.raises(ReleaseValidationError, match="Wheel digest mismatch"):
        fetch_release_payload(source_dir=repo)


def test_fetch_from_github_api_failure_fails_closed() -> None:
    http_err = urllib.error.URLError("release endpoint unavailable")
    with (
        patch("urllib.request.urlopen", side_effect=http_err),
        pytest.raises(ReleaseValidationError, match="Could not resolve release"),
    ):
        fetch_release_payload(repo="weby-homelab/power-framework", ref="latest")


def test_fetch_from_github_rejects_non_release_ref_before_network() -> None:
    with pytest.raises(ReleaseValidationError, match="stable v<version> tag"):
        fetch_release_payload(repo="weby-homelab/power-framework", ref="main")


def test_fetch_from_github_rejects_prerelease_on_latest() -> None:
    release_resp = MagicMock()
    release_resp.read.return_value = json.dumps(
        {
            "tag_name": "v3.8.0rc1",
            "prerelease": True,
            "draft": False,
        }
    ).encode("utf-8")
    release_resp.__enter__.return_value = release_resp

    with (
        patch("urllib.request.urlopen", return_value=release_resp),
        pytest.raises(ReleaseValidationError, match="prerelease"),
    ):
        fetch_release_payload(repo="weby-homelab/power-framework", ref="latest")


def test_fetch_from_github_wheel_asset_mismatch_fails_closed() -> None:
    release_json = {
        "tag_name": "v3.7.8",
        "prerelease": False,
        "draft": False,
        "assets": [
            {
                "name": "power_framework-3.7.8-py3-none-any.whl",
                "browser_download_url": "https://github.com/weby-homelab/power-framework/releases/download/v3.7.8/power_framework-3.7.8-py3-none-any.whl",
            }
        ],
    }
    pyproject_text = '[project]\nname = "power-framework"\nversion = "3.7.8"\n'
    manifest_json = {
        "schema": "power.release.manifest.v1",
        "version": "3.7.8",
        "commit": "a" * 40,
        "artifacts": {
            "power_wheel": {
                "filename": "power_framework-3.7.8-mismatched.whl",
                "sha256": "a" * 64,
            }
        },
    }
    _add_published_manifest_asset(release_json, manifest_json)

    def urlopen_side_effect(req: urllib.request.Request, **kwargs: Any) -> MagicMock:
        url = req.full_url
        mock = MagicMock()
        mock.__enter__.return_value = mock
        if url.endswith("/releases/latest"):
            mock.read.return_value = json.dumps(release_json).encode("utf-8")
        elif "pyproject.toml" in url:
            mock.read.return_value = pyproject_text.encode("utf-8")
        elif "power-release-manifest.json" in url:
            mock.read.return_value = json.dumps(manifest_json).encode("utf-8")
        return mock

    with (
        patch("urllib.request.urlopen", side_effect=urlopen_side_effect),
        pytest.raises(ReleaseValidationError, match="does not match manifest wheel"),
    ):
        fetch_release_payload(repo="weby-homelab/power-framework", ref="latest")


def test_fetch_from_github_wheel_asset_digest_manifest_mismatch_fails_closed() -> None:
    manifest_sha = "a" * 64
    asset_digest = "sha256:" + "b" * 64
    release_json = {
        "tag_name": "v3.7.8",
        "prerelease": False,
        "draft": False,
        "assets": [
            {
                "name": "power_framework-3.7.8-py3-none-any.whl",
                "browser_download_url": "https://github.com/weby-homelab/power-framework/releases/download/v3.7.8/power_framework-3.7.8-py3-none-any.whl",
                "digest": asset_digest,
            }
        ],
    }
    pyproject_text = '[project]\nname = "power-framework"\nversion = "3.7.8"\n'
    manifest_json = {
        "schema": "power.release.manifest.v1",
        "version": "3.7.8",
        "commit": "a" * 40,
        "artifacts": {
            "power_wheel": {
                "filename": "power_framework-3.7.8-py3-none-any.whl",
                "sha256": manifest_sha,
            }
        },
    }
    _add_published_manifest_asset(release_json, manifest_json)

    def urlopen_side_effect(req: urllib.request.Request, **kwargs: Any) -> MagicMock:
        url = req.full_url
        mock = MagicMock()
        mock.__enter__.return_value = mock
        if url.endswith("/releases/latest"):
            mock.read.return_value = json.dumps(release_json).encode("utf-8")
        elif "pyproject.toml" in url:
            mock.read.return_value = pyproject_text.encode("utf-8")
        elif "power-release-manifest.json" in url:
            mock.read.return_value = json.dumps(manifest_json).encode("utf-8")
        return mock

    with (
        patch("urllib.request.urlopen", side_effect=urlopen_side_effect),
        pytest.raises(ReleaseValidationError, match="does not match manifest wheel SHA-256"),
    ):
        fetch_release_payload(repo="weby-homelab/power-framework", ref="latest")


def test_fetch_from_github_wheel_asset_digest_matching_succeeds() -> None:
    manifest_sha = "a" * 64
    asset_digest = "SHA256:" + "a" * 64
    release_json = {
        "tag_name": "v3.7.8",
        "prerelease": False,
        "draft": False,
        "assets": [
            {
                "name": "power_framework-3.7.8-py3-none-any.whl",
                "browser_download_url": "https://github.com/weby-homelab/power-framework/releases/download/v3.7.8/power_framework-3.7.8-py3-none-any.whl",
                "digest": asset_digest,
            }
        ],
    }
    pyproject_text = '[project]\nname = "power-framework"\nversion = "3.7.8"\n'
    manifest_json = {
        "schema": "power.release.manifest.v1",
        "version": "3.7.8",
        "commit": "a" * 40,
        "artifacts": {
            "power_wheel": {
                "filename": "power_framework-3.7.8-py3-none-any.whl",
                "sha256": manifest_sha,
            }
        },
    }
    _add_published_manifest_asset(release_json, manifest_json)

    def urlopen_side_effect(req: urllib.request.Request, **kwargs: Any) -> MagicMock:
        url = req.full_url
        mock = MagicMock()
        mock.__enter__.return_value = mock
        if url.endswith("/releases/latest"):
            mock.read.return_value = json.dumps(release_json).encode("utf-8")
        elif "pyproject.toml" in url:
            mock.read.return_value = pyproject_text.encode("utf-8")
        elif "power-release-manifest.json" in url:
            mock.read.return_value = json.dumps(manifest_json).encode("utf-8")
        return mock

    with patch("urllib.request.urlopen", side_effect=urlopen_side_effect):
        payload = fetch_release_payload(repo="weby-homelab/power-framework", ref="latest")
        assert payload.wheel_sha256 == "a" * 64
        assert payload.wheel_filename == "power_framework-3.7.8-py3-none-any.whl"


def test_fetch_from_github_without_published_manifest_fails_closed() -> None:
    asset_digest = "sha256:" + "c" * 64
    release_json = {
        "tag_name": "v3.7.8",
        "prerelease": False,
        "draft": False,
        "assets": [
            {
                "name": "power_framework-3.7.8-py3-none-any.whl",
                "browser_download_url": "https://github.com/weby-homelab/power-framework/releases/download/v3.7.8/power_framework-3.7.8-py3-none-any.whl",
                "digest": asset_digest,
            }
        ],
    }
    pyproject_text = '[project]\nname = "power-framework"\nversion = "3.7.8"\n'

    def urlopen_side_effect(req: urllib.request.Request, **kwargs: Any) -> MagicMock:
        url = req.full_url
        mock = MagicMock()
        mock.__enter__.return_value = mock
        if "releases" in url:
            mock.read.return_value = json.dumps(release_json).encode("utf-8")
        elif "pyproject.toml" in url:
            mock.read.return_value = pyproject_text.encode("utf-8")
        elif "power-release-manifest.json" in url:
            raise urllib.error.URLError("manifest endpoint unavailable")
        return mock

    with (
        patch("urllib.request.urlopen", side_effect=urlopen_side_effect),
        pytest.raises(ReleaseValidationError, match="exactly one published"),
    ):
        fetch_release_payload(repo="weby-homelab/power-framework", ref="latest")


def test_extract_wheel_skill_tree_path_traversal_protection(tmp_path: Path) -> None:
    wheel_file = tmp_path / "malicious.whl"

    with zipfile.ZipFile(wheel_file, "w") as zf:
        zf.writestr("power_framework/data/skills/power/../../evil.sh", "echo evil")

    with pytest.raises(ReleaseValidationError, match="Unsafe or disallowed path"):
        _extract_wheel_skill_tree(wheel_file)


def test_download_and_verify_wheel(tmp_path: Path) -> None:
    dummy_wheel = b"PK\x03\x04dummy_wheel_content"
    wheel_hash = hashlib.sha256(dummy_wheel).hexdigest()

    resp_mock = MagicMock()
    resp_mock.read.side_effect = [dummy_wheel, b""]
    resp_mock.__enter__.return_value = resp_mock

    with patch("urllib.request.urlopen", return_value=resp_mock):
        downloaded = download_and_verify_wheel(
            wheel_url="https://github.com/weby-homelab/power-framework/releases/download/v3.7.8/wheel.whl",
            expected_sha256=wheel_hash,
            dest_dir=tmp_path,
        )
        assert downloaded.is_file()
        assert sha256_file(downloaded) == wheel_hash


def test_download_and_verify_wheel_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    dummy_wheel = b"PK\x03\x04dummy_wheel_content"
    resp_mock = MagicMock()
    resp_mock.read.side_effect = [dummy_wheel, b""]
    resp_mock.__enter__.return_value = resp_mock

    with (
        patch("urllib.request.urlopen", return_value=resp_mock),
        pytest.raises(ReleaseValidationError, match="SHA-256 mismatch"),
    ):
        download_and_verify_wheel(
            wheel_url="https://github.com/weby-homelab/power-framework/releases/download/v3.7.8/wheel.whl",
            expected_sha256="0" * 64,
            dest_dir=tmp_path,
        )


def test_download_and_verify_wheel_rejects_noncanonical_url(tmp_path: Path) -> None:
    with pytest.raises(ReleaseValidationError, match="canonical GitHub release URL"):
        download_and_verify_wheel(
            wheel_url="https://example.com/wheel.whl",
            expected_sha256="0" * 64,
            dest_dir=tmp_path,
        )


def test_download_and_verify_wheel_rejects_oversized_response(tmp_path: Path) -> None:
    response = MagicMock()
    response.headers = {"Content-Length": str(MAX_RELEASE_WHEEL_BYTES + 1)}
    response.__enter__.return_value = response

    with (
        patch("urllib.request.urlopen", return_value=response),
        pytest.raises(ReleaseValidationError, match="maximum download size"),
    ):
        download_and_verify_wheel(
            wheel_url="https://github.com/weby-homelab/power-framework/releases/download/v3.7.8/wheel.whl",
            expected_sha256="0" * 64,
            dest_dir=tmp_path,
        )


# ============================================================================
# 7. Bounded Virtual Environments Discovery, pip3 / python3 & Root Guards
# ============================================================================


def test_is_system_prefix() -> None:
    assert is_system_prefix(Path("/")) is True
    assert is_system_prefix(Path("/var")) is True
    assert is_system_prefix(Path("/var/log")) is True
    assert is_system_prefix(Path("/var/lib/venvs/test")) is True
    assert is_system_prefix(Path("/run")) is True
    assert is_system_prefix(Path("/run/user/1000")) is True
    assert is_system_prefix(Path("/usr/bin/python3")) is True
    assert is_system_prefix(Path("/usr/lib/python3.13")) is True
    assert is_system_prefix(Path("/bin/sh")) is True
    assert is_system_prefix(Path("/etc/passwd")) is True
    assert is_system_prefix(Path("/root/.local/share/power/venv")) is False
    assert is_system_prefix(Path("/root/geminicli/projects/P.O.W.E.R/.venv")) is False


def test_discover_bounded_venvs_with_python3_and_pip3(tmp_path: Path) -> None:
    root = tmp_path / "venvs"
    root.mkdir()

    # Venv with bin/python3 and bin/pip3 (no bin/python or bin/pip)
    venv1 = root / "venv_py3"
    venv1.mkdir()
    (venv1 / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    bin1 = venv1 / "bin"
    bin1.mkdir()
    (bin1 / "python3").write_text("#!/bin/sh\n", encoding="utf-8")
    (bin1 / "pip3").write_text("#!/bin/sh\n", encoding="utf-8")

    dist_info = venv1 / "lib" / "python3.13" / "site-packages" / "power_framework-3.7.8.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.7.8\n",
        encoding="utf-8",
    )

    discovered = discover_bounded_venvs([root])
    assert venv1.resolve() in discovered
    assert find_venv_python(venv1) == bin1 / "python3"
    assert find_venv_pip(venv1) == [str(bin1 / "pip3")]
    assert get_venv_power_framework_version(venv1) == "3.7.8"


def test_audit_venv_system_prefix_guard() -> None:
    res = audit_venv(Path("/usr"), "3.7.8")
    assert res.status == "unwritable"
    assert "System Python" in str(res.error)


def test_get_venv_power_framework_version_system_prefix_exclusion() -> None:
    for prefix in (
        "/",
        "/usr",
        "/var",
        "/run",
        "/bin",
        "/sbin",
        "/lib",
        "/lib64",
        "/opt/local",
        "/etc",
        "/sys",
        "/proc",
        "/dev",
    ):
        assert get_venv_power_framework_version(Path(prefix)) is None


def test_apply_venv_update_prohibits_unverified_pypi(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "bin").mkdir()
    (venv / "bin" / "python").write_text("#!/bin/sh\n", encoding="utf-8")
    (venv / "bin" / "pip").write_text("#!/bin/sh\n", encoding="utf-8")

    audit = VenvAuditResult(
        path=str(venv),
        python_path=str(venv / "bin" / "python"),
        installed_version="3.4.5",
        is_writable=True,
        status="outdated",
    )
    rel = ReleasePayload(tag="v3.7.8", version="3.7.8", pyproject_version="3.7.8", wheel_path=None)
    action, err = apply_venv_update(audit, rel, dry_run=False)
    assert action == "failed"
    assert "unverified PyPI is prohibited" in str(err)


# ============================================================================
# 8. MCP Client Config & Runtime Shebang Inspection Tests
# ============================================================================


def test_resolve_mcp_runtime_via_shebang(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    py_bin = bin_dir / "python"
    py_bin.write_text("#!/bin/sh\n", encoding="utf-8")

    dist_info = venv / "lib" / "python3.13" / "site-packages" / "power_framework-3.7.8.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.7.8\n",
        encoding="utf-8",
    )

    power_mcp = bin_dir / "power-mcp"
    power_mcp.write_text(f"#!{py_bin}\nimport sys\n", encoding="utf-8")
    power_mcp.chmod(0o755)

    exe, run_py, inst_ver, err = resolve_mcp_runtime(str(power_mcp))
    assert exe == str(power_mcp)
    assert run_py == str(py_bin)
    assert inst_ver == "3.7.8"
    assert err is None


def test_resolve_mcp_runtime_env_shebang_via_which(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    fake_python = bin_dir / "python3"
    fake_python.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_python.chmod(0o755)

    dist_info = venv / "lib" / "python3.13" / "site-packages" / "power_framework-3.7.8.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.7.8\n",
        encoding="utf-8",
    )

    power_mcp = bin_dir / "power-mcp"
    power_mcp.write_text("#!/usr/bin/env python3\nimport sys\n", encoding="utf-8")
    power_mcp.chmod(0o755)

    with patch("shutil.which", return_value=str(fake_python)):
        exe, run_py, inst_ver, err = resolve_mcp_runtime(str(power_mcp))
        assert exe == str(power_mcp)
        assert run_py == str(fake_python)
        assert inst_ver == "3.7.8"
        assert err is None


def test_audit_mcp_config_outdated_runtime(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    py_bin = bin_dir / "python"
    py_bin.write_text("#!/bin/sh\n", encoding="utf-8")

    dist_info = venv / "lib" / "python3.13" / "site-packages" / "power_framework-3.4.5.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.4.5\n",
        encoding="utf-8",
    )

    power_mcp = bin_dir / "power-mcp"
    power_mcp.write_text(f"#!{py_bin}\nimport sys\n", encoding="utf-8")

    config = tmp_path / "opencode.json"
    config.write_text(
        json.dumps(
            {
                "mcp": {
                    "power": {
                        "type": "local",
                        "command": [str(power_mcp)],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    res = audit_mcp_config(config, target_version="3.7.8")
    assert res.status == "outdated"
    assert res.installed_version == "3.4.5"


def test_audit_mcp_config_missing_runtime(tmp_path: Path) -> None:
    config = tmp_path / "mcp_config.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "power": {
                        "command": "/non/existent/path/to/power-mcp",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    res = audit_mcp_config(config, target_version="3.7.8")
    assert res.status == "missing_runtime"


def test_audit_mcp_foreign_entry_marked_mismatch(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[mcp_servers.power]\ncommand = "some-foreign-cmd"\n', encoding="utf-8")

    res = audit_mcp_config(config)
    assert res.status == "mismatch"


def test_is_python_interpreter_matrix() -> None:
    # Valid python interpreter paths and names
    assert is_python_interpreter("python") is True
    assert is_python_interpreter("python3") is True
    assert is_python_interpreter("python3.11") is True
    assert is_python_interpreter("python3.13") is True
    assert is_python_interpreter("python3.13t") is True
    assert is_python_interpreter("python.exe") is True
    assert is_python_interpreter("pypy3") is True
    assert is_python_interpreter(Path("/root/venv/bin/python")) is True
    assert is_python_interpreter(Path("/usr/bin/python3.13")) is True

    # Shells and non-python binaries MUST be rejected
    assert is_python_interpreter("/bin/sh") is False
    assert is_python_interpreter("/bin/bash") is False
    assert is_python_interpreter("sh") is False
    assert is_python_interpreter("bash") is False
    assert is_python_interpreter("dash") is False
    assert is_python_interpreter("zsh") is False
    assert is_python_interpreter("ksh") is False
    assert is_python_interpreter("fish") is False
    assert is_python_interpreter("busybox") is False
    assert is_python_interpreter("env") is False
    assert is_python_interpreter("node") is False
    assert is_python_interpreter("perl") is False
    assert is_python_interpreter("ruby") is False
    assert is_python_interpreter("power-mcp") is False
    assert is_python_interpreter("") is False


def test_resolve_mcp_runtime_shell_wrapper_with_exec_resolves_venv_python(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    py_bin = bin_dir / "python"
    py_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    py_bin.chmod(0o755)

    dist_info = venv / "lib" / "python3.13" / "site-packages" / "power_framework-3.7.8.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.7.8\n",
        encoding="utf-8",
    )

    # Shell wrapper at /tmp_path/local_bin/power-mcp
    local_bin = tmp_path / "local_bin"
    local_bin.mkdir()
    power_mcp = local_bin / "power-mcp"
    power_mcp.write_text(
        f'#!/bin/sh\nexec {py_bin} -m power_framework.mcp "$@"\n',
        encoding="utf-8",
    )
    power_mcp.chmod(0o755)

    exe, run_py, inst_ver, err = resolve_mcp_runtime(str(power_mcp))
    assert exe == str(power_mcp)
    assert run_py == str(py_bin)
    assert inst_ver == "3.7.8"
    assert err is None


def test_resolve_mcp_runtime_shell_wrapper_variants_quoted_and_multiline(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    py_bin = bin_dir / "python3"
    py_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    py_bin.chmod(0o755)

    dist_info = venv / "lib" / "python3.13" / "site-packages" / "power_framework-3.7.8.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.7.8\n",
        encoding="utf-8",
    )

    local_bin = tmp_path / "local_bin"
    local_bin.mkdir()

    # 1. Double-quoted exec with environment variables
    wrapper1 = local_bin / "wrapper1"
    wrapper1.write_text(
        f'#!/bin/bash\nexport POWER_VAULT_DIR="/root/brain"\nexec "{py_bin}" -m power_framework.mcp "$@"\n',
        encoding="utf-8",
    )
    wrapper1.chmod(0o755)
    exe1, run_py1, inst_ver1, err1 = resolve_mcp_runtime(str(wrapper1))
    assert exe1 == str(wrapper1)
    assert run_py1 == str(py_bin)
    assert inst_ver1 == "3.7.8"
    assert err1 is None

    # 2. Single-quoted exec with semicolon
    wrapper2 = local_bin / "wrapper2"
    wrapper2.write_text(
        f"#!/bin/sh\ncd /tmp; exec '{py_bin}' \"$@\"\n",
        encoding="utf-8",
    )
    wrapper2.chmod(0o755)
    exe2, run_py2, inst_ver2, err2 = resolve_mcp_runtime(str(wrapper2))
    assert exe2 == str(wrapper2)
    assert run_py2 == str(py_bin)
    assert inst_ver2 == "3.7.8"
    assert err2 is None


def test_extract_exec_python_from_wrapper_unit(tmp_path: Path) -> None:
    fake_py = tmp_path / "bin" / "python3"
    fake_py.parent.mkdir(parents=True)
    fake_py.write_text("#!/bin/sh\n", encoding="utf-8")

    content1 = f'#!/bin/sh\nexec "{fake_py}" -m power_framework.mcp "$@"\n'
    assert _extract_exec_python_from_wrapper(content1) == fake_py

    content2 = f"#!/bin/bash\n# comment\nexec '{fake_py}' \"$@\"\n"
    assert _extract_exec_python_from_wrapper(content2) == fake_py

    # Non-existent python returns None
    content_missing = '#!/bin/sh\nexec "/nonexistent/python" "$@"\n'
    assert _extract_exec_python_from_wrapper(content_missing) is None

    # Shell executable returns None
    content_sh = '#!/bin/sh\nexec "/bin/sh" "$@"\n'
    assert _extract_exec_python_from_wrapper(content_sh) is None

    # No exec line returns None
    assert _extract_exec_python_from_wrapper("#!/bin/sh\necho hello\n") is None


def test_resolve_mcp_runtime_shell_wrapper_never_treats_bin_sh_as_python(tmp_path: Path) -> None:
    local_bin = tmp_path / "local_bin"
    local_bin.mkdir()

    # Shell script without Python exec
    wrapper_sh = local_bin / "power-mcp"
    wrapper_sh.write_text("#!/bin/sh\necho 'running shell wrapper'\n", encoding="utf-8")
    wrapper_sh.chmod(0o755)

    exe, run_py, inst_ver, err = resolve_mcp_runtime(str(wrapper_sh))
    assert exe == str(wrapper_sh)
    assert run_py != "/bin/sh"
    assert run_py is None
    assert inst_ver is None
    assert err is None

    # Shell script execing /bin/sh
    wrapper_exec_sh = local_bin / "power-mcp-sh"
    wrapper_exec_sh.write_text('#!/bin/sh\nexec /bin/sh "$@"\n', encoding="utf-8")
    wrapper_exec_sh.chmod(0o755)

    exe2, run_py2, inst_ver2, err2 = resolve_mcp_runtime(str(wrapper_exec_sh))
    assert exe2 == str(wrapper_exec_sh)
    assert run_py2 != "/bin/sh"
    assert run_py2 is None
    assert inst_ver2 is None
    assert err2 is None


def test_extract_exec_target_from_wrapper_unit(tmp_path: Path) -> None:
    fake_py = tmp_path / "bin" / "python3"
    base_dir = tmp_path / "wrappers"
    base_dir.mkdir(parents=True)

    # 1. Absolute target
    content_abs = f'#!/bin/sh\nexec "{fake_py}" -m power_framework.mcp "$@"\n'
    assert _extract_exec_target_from_wrapper(content_abs) == fake_py

    # 2. Relative target with base_dir
    content_rel = '#!/bin/sh\nexec ../bin/python3 "$@"\n'
    assert _extract_exec_target_from_wrapper(content_rel, base_dir=base_dir) == fake_py.resolve()

    # 3. Target with spaces in quotes
    spaced_target = tmp_path / "my bin" / "power-mcp"
    content_spaced = f'#!/bin/sh\nexec "{spaced_target}" "$@"\n'
    assert _extract_exec_target_from_wrapper(content_spaced) == spaced_target

    # 4. Command preceded by export or cd
    content_multi = f'#!/bin/bash\nexport FOO="bar"; exec \'{fake_py}\' "$@"\n'
    assert _extract_exec_target_from_wrapper(content_multi) == fake_py

    # 5. Commented exec line is ignored
    content_commented = "#!/bin/sh\n# exec /ignore/this\necho ok\n"
    assert _extract_exec_target_from_wrapper(content_commented) is None

    # 6. Inline comment stripped
    content_inline = f'#!/bin/sh\nexec {fake_py} "$@" # launch python\n'
    assert _extract_exec_target_from_wrapper(content_inline) == fake_py


def test_resolve_mcp_runtime_nested_two_level_wrapper_prxmx(tmp_path: Path) -> None:
    # Simulates: /root/.local/bin/power-mcp -> exec /root/.local/share/power/current/venv/bin/power-mcp
    # where the second script has shebang: #!/root/.local/share/power/current/venv/bin/python3
    venv = tmp_path / ".local" / "share" / "power" / "current" / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    py_bin = bin_dir / "python3"
    py_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    py_bin.chmod(0o755)

    dist_info = venv / "lib" / "python3.13" / "site-packages" / "power_framework-3.7.8.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.7.8\n",
        encoding="utf-8",
    )

    # Level 2 console script
    level2_script = bin_dir / "power-mcp"
    level2_script.write_text(
        f"#!{py_bin}\nimport sys\nfrom power_framework.mcp import main\nif __name__ == '__main__':\n    sys.exit(main())\n",
        encoding="utf-8",
    )
    level2_script.chmod(0o755)

    # Level 1 shell wrapper
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)
    level1_wrapper = local_bin / "power-mcp"
    level1_wrapper.write_text(
        f'#!/bin/sh\nexec {level2_script} "$@"\n',
        encoding="utf-8",
    )
    level1_wrapper.chmod(0o755)

    exe, run_py, inst_ver, err = resolve_mcp_runtime(str(level1_wrapper))
    assert exe == str(level1_wrapper)
    assert run_py == str(py_bin)
    assert inst_ver == "3.7.8"
    assert err is None

    # Verify audit_mcp_config also passes with Level 1 wrapper
    config = tmp_path / "opencode.jsonc"
    config.write_text(
        json.dumps(
            {
                "mcp": {
                    "power": {
                        "command": str(level1_wrapper),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    res = audit_mcp_config(config, target_version="3.7.8")
    assert res.status == "canonical"
    assert res.installed_version == "3.7.8"
    assert res.runtime_python == str(py_bin)
    assert res.resolved_executable == str(level1_wrapper)
    assert res.error is None


def test_resolve_mcp_runtime_wrapper_relative_two_level_wrapper(tmp_path: Path) -> None:
    # Level 1 wrapper at /tmp_path/local/bin/power-mcp execing ../../share/power/current/venv/bin/power-mcp
    venv = tmp_path / "share" / "power" / "current" / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    py_bin = bin_dir / "python"
    py_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    py_bin.chmod(0o755)

    dist_info = venv / "lib" / "python3.13" / "site-packages" / "power_framework-3.7.8.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.7.8\n",
        encoding="utf-8",
    )

    level2_script = bin_dir / "power-mcp"
    level2_script.write_text(f"#!{py_bin}\nimport sys\n", encoding="utf-8")
    level2_script.chmod(0o755)

    local_bin = tmp_path / "local" / "bin"
    local_bin.mkdir(parents=True)
    level1_wrapper = local_bin / "power-mcp"
    level1_wrapper.write_text(
        '#!/bin/sh\nexec ../../share/power/current/venv/bin/power-mcp "$@"\n',
        encoding="utf-8",
    )
    level1_wrapper.chmod(0o755)

    exe, run_py, inst_ver, err = resolve_mcp_runtime(str(level1_wrapper))
    assert exe == str(level1_wrapper)
    assert run_py == str(py_bin)
    assert inst_ver == "3.7.8"
    assert err is None


def test_resolve_mcp_runtime_cyclic_wrappers_fail_closed(tmp_path: Path) -> None:
    # Direct mutual recursion: wrapper_a -> exec wrapper_b -> exec wrapper_a
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    dir_b = tmp_path / "b"
    dir_b.mkdir()
    wrapper_a = dir_a / "power-mcp"
    wrapper_b = dir_b / "power-mcp"

    wrapper_a.write_text(f'#!/bin/sh\nexec {wrapper_b} "$@"\n', encoding="utf-8")
    wrapper_a.chmod(0o755)
    wrapper_b.write_text(f'#!/bin/sh\nexec {wrapper_a} "$@"\n', encoding="utf-8")
    wrapper_b.chmod(0o755)

    exe_a, run_py_a, inst_ver_a, err_a = resolve_mcp_runtime(str(wrapper_a))
    assert exe_a == str(wrapper_a)
    assert run_py_a is None
    assert inst_ver_a is None
    assert err_a is not None
    assert "Cyclic exec wrapper" in err_a

    # Self-referencing wrapper
    dir_self = tmp_path / "self"
    dir_self.mkdir()
    wrapper_self = dir_self / "power-mcp"
    wrapper_self.write_text(f'#!/bin/sh\nexec {wrapper_self} "$@"\n', encoding="utf-8")
    wrapper_self.chmod(0o755)

    exe_s, run_py_s, inst_ver_s, err_s = resolve_mcp_runtime(str(wrapper_self))
    assert exe_s == str(wrapper_self)
    assert run_py_s is None
    assert inst_ver_s is None
    assert err_s is not None
    assert "Cyclic exec wrapper" in err_s

    # audit_mcp_config fails closed to missing_runtime on cyclic wrapper
    config = tmp_path / "mcp_cyclic.json"
    config.write_text(
        json.dumps({"mcpServers": {"power": {"command": str(wrapper_a)}}}),
        encoding="utf-8",
    )
    res = audit_mcp_config(config)
    assert res.status == "missing_runtime"
    assert res.error is not None
    assert "Cyclic exec wrapper" in res.error


def test_resolve_mcp_runtime_depth_limit_fail_closed(tmp_path: Path) -> None:
    # Chain of wrappers exceeding MAX_WRAPPER_DEPTH
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    py_bin = bin_dir / "python3"
    py_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    py_bin.chmod(0o755)

    chain_len = MAX_WRAPPER_DEPTH + 3
    wrappers: list[Path] = []
    for i in range(chain_len):
        w_dir = tmp_path / f"w_{i}"
        w_dir.mkdir()
        wrappers.append(w_dir / "power-mcp")

    for i in range(chain_len - 1):
        wrappers[i].write_text(f'#!/bin/sh\nexec {wrappers[i + 1]} "$@"\n', encoding="utf-8")
        wrappers[i].chmod(0o755)
    # Last wrapper points to python
    wrappers[-1].write_text(f'#!/bin/sh\nexec {py_bin} "$@"\n', encoding="utf-8")
    wrappers[-1].chmod(0o755)

    exe, run_py, inst_ver, err = resolve_mcp_runtime(str(wrappers[0]))
    assert exe == str(wrappers[0])
    assert run_py is None
    assert inst_ver is None
    assert err is not None
    assert "depth limit" in err

    # audit_mcp_config fails closed to missing_runtime on depth limit
    config = tmp_path / "mcp_deep.json"
    config.write_text(
        json.dumps({"mcpServers": {"power": {"command": str(wrappers[0])}}}),
        encoding="utf-8",
    )
    res = audit_mcp_config(config)
    assert res.status == "missing_runtime"
    assert res.error is not None
    assert "depth limit" in res.error


def test_resolve_mcp_runtime_nonexistent_exec_target_fails_closed(tmp_path: Path) -> None:
    wrapper = tmp_path / "wrapper_missing_target.sh"
    wrapper.write_text('#!/bin/sh\nexec /nonexistent/target/path "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)

    exe, run_py, inst_ver, err = resolve_mcp_runtime(str(wrapper))
    assert exe == str(wrapper)
    assert run_py is None
    assert inst_ver is None
    assert err is not None
    assert "not found" in err


def test_resolve_mcp_runtime_non_regular_file_exec_target_fails_closed(tmp_path: Path) -> None:
    target_dir = tmp_path / "a_directory"
    target_dir.mkdir()
    wrapper = tmp_path / "wrapper_dir_target.sh"
    wrapper.write_text(f'#!/bin/sh\nexec {target_dir} "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)

    exe, run_py, inst_ver, err = resolve_mcp_runtime(str(wrapper))
    assert exe == str(wrapper)
    assert run_py is None
    assert inst_ver is None
    assert err is not None
    assert "not a regular file" in err


def test_audit_mcp_config_with_shell_wrapper(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    py_bin = bin_dir / "python"
    py_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    py_bin.chmod(0o755)

    dist_info = venv / "lib" / "python3.13" / "site-packages" / "power_framework-3.7.8.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.7.8\n",
        encoding="utf-8",
    )

    power_mcp = bin_dir / "power-mcp"
    power_mcp.write_text(
        f'#!/bin/sh\nexec {py_bin} -m power_framework.mcp "$@"\n',
        encoding="utf-8",
    )
    power_mcp.chmod(0o755)

    config = tmp_path / "gemini_mcp.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "power": {
                        "command": str(power_mcp),
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    res = audit_mcp_config(config, target_version="3.7.8")
    assert res.status == "canonical"
    assert res.installed_version == "3.7.8"
    assert res.runtime_python == str(py_bin)
    assert res.resolved_executable == str(power_mcp)


def test_audit_mcp_extract_and_validate_structure(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    py_bin = bin_dir / "python"
    py_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    py_bin.chmod(0o755)

    dist_info = venv / "lib" / "python3.13" / "site-packages" / "power_framework-3.7.8.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.7.8\n",
        encoding="utf-8",
    )

    power_mcp = bin_dir / "power-mcp"
    power_mcp.write_text(
        f'#!/bin/sh\nexec {py_bin} -m power_framework.mcp "$@"\n',
        encoding="utf-8",
    )
    power_mcp.chmod(0o755)

    config = tmp_path / "mcp_config.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "power": {
                        "command": str(power_mcp),
                        "args": [],
                        "env": {"POWER_VAULT_DIR": "/custom/brain", "SECRET": "xyz"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    res = audit_mcp_config(config)
    assert res.executable == str(power_mcp)
    assert res.resolved_executable == str(power_mcp)
    assert res.runtime_python == str(py_bin)
    assert res.installed_version == "3.7.8"
    assert res.status == "canonical"
    assert res.env_keys == ["POWER_VAULT_DIR", "SECRET"]
    assert "xyz" not in json.dumps(res.as_dict())


# ============================================================================
# 9. Skill Targets Allowlist, Path Traversal & Atomic Replacement
# ============================================================================


def test_is_safe_skill_relative_path_rules() -> None:
    assert "SKILL.md" in ALLOWED_SKILL_TOP_LEVEL_FILES
    assert "README.md" in ALLOWED_SKILL_TOP_LEVEL_FILES
    assert "references" in ALLOWED_SKILL_DIRECTORIES
    assert "scripts" in ALLOWED_SKILL_DIRECTORIES
    assert ".md" in ALLOWED_SKILL_EXTENSIONS
    assert ".py" in ALLOWED_SKILL_EXTENSIONS

    # Top-level allowlist
    assert is_safe_skill_relative_path("SKILL.md") is True
    assert is_safe_skill_relative_path("README.md") is True
    assert is_safe_skill_relative_path("script.py") is False  # not top-level allowed
    assert is_safe_skill_relative_path("evil.sh") is False

    # Allowed subdirectories with safe extensions
    assert is_safe_skill_relative_path("references/architecture.md") is True
    assert is_safe_skill_relative_path("scripts/sync_vault.py") is True
    assert is_safe_skill_relative_path("templates/config.toml") is True
    assert is_safe_skill_relative_path("assets/diagram.png") is True

    # Disallowed extensions or directory traversal
    assert is_safe_skill_relative_path("references/evil.exe") is False
    assert is_safe_skill_relative_path("untrusted/doc.md") is False
    assert is_safe_skill_relative_path("../SKILL.md") is False
    assert is_safe_skill_relative_path("references/../../evil.md") is False
    assert is_safe_skill_relative_path("/absolute/path.md") is False
    assert is_safe_skill_relative_path(".hidden") is False


def test_is_allowed_skill_target_protection(tmp_path: Path) -> None:
    # Disallowed: system prefixes, root directory, user home root
    assert is_allowed_skill_target(Path("/usr/local/skills/power")) is False
    assert is_allowed_skill_target(Path("/etc/power")) is False
    assert is_allowed_skill_target(Path("/root")) is False
    assert is_allowed_skill_target(Path("/")) is False

    # Allowed: valid non-system target under explicit allowed roots
    allowed_root_1 = tmp_path / "agents_skills"
    allowed_root_2 = tmp_path / "gemini_skills"
    allowed_root_1.mkdir(parents=True)
    allowed_root_2.mkdir(parents=True)

    target_1 = allowed_root_1 / "power"
    target_2 = allowed_root_2 / "power"
    target_1.mkdir()
    target_2.mkdir()

    allowed_roots = [allowed_root_1, allowed_root_2]
    assert is_allowed_skill_target(target_1, allowed_roots=allowed_roots) is True
    assert is_allowed_skill_target(target_2, allowed_roots=allowed_roots) is True
    assert (
        is_allowed_skill_target(tmp_path / "disallowed" / "power", allowed_roots=allowed_roots)
        is False
    )


def test_audit_skill_and_extract_metadata(tmp_path: Path) -> None:
    target = tmp_path / "skills" / "power"
    target.mkdir(parents=True)
    skill_content = "---\nname: power\nversion: 3.7.8\n---\n# Power Skill\n"
    (target / "SKILL.md").write_text(skill_content, encoding="utf-8")

    assert extract_skill_version(skill_content) == "3.7.8"
    assert is_managed_skill_tree({"SKILL.md": skill_content.encode("utf-8")}) is True

    rel = ReleasePayload(
        tag="v3.7.8",
        version="3.7.8",
        pyproject_version="3.7.8",
        skill_tree_sha256=aggregate_tree_hash({"SKILL.md": skill_content.encode("utf-8")}),
        skill_files={"SKILL.md": skill_content.encode("utf-8")},
    )
    res = audit_skill(target, rel, allowed_roots=[tmp_path / "skills"])
    assert res.status == "up_to_date"
    assert res.installed_version == "3.7.8"


def test_apply_skill_update_path_traversal_fails(tmp_path: Path) -> None:
    target = tmp_path / "skills" / "power"
    files = {
        "SKILL.md": b"---\nname: power\nversion: 3.7.8\n---\n",
        "../traversal.txt": b"evil",
    }
    rel = ReleasePayload(
        tag="v3.7.8",
        version="3.7.8",
        pyproject_version="3.7.8",
        skill_files=files,
    )
    audit = SkillAuditResult(
        target_path=str(target),
        installed_version=None,
        tree_sha256=None,
        status="ready",
    )
    action, err = apply_skill_update(audit, rel, dry_run=False, allowed_roots=[tmp_path / "skills"])
    assert action == "failed"
    assert "Unsafe or disallowed skill relative path" in str(err)


def test_apply_skill_update_outside_allowed_roots_fails() -> None:
    target = Path("/etc/cron.d/power")
    files = {"SKILL.md": b"---\nname: power\nversion: 3.7.8\n---\n"}
    rel = ReleasePayload(
        tag="v3.7.8",
        version="3.7.8",
        pyproject_version="3.7.8",
        skill_files=files,
    )
    audit = SkillAuditResult(
        target_path=str(target),
        installed_version=None,
        tree_sha256=None,
        status="ready",
    )
    action, err = apply_skill_update(audit, rel, dry_run=False)
    assert action == "failed"
    assert "outside allowed roots" in str(err)


# ============================================================================
# 10. Process Lock, Dedup, State Persistence & Pipeline Tests
# ============================================================================


def test_process_lock_prevents_concurrency(tmp_path: Path) -> None:
    lock_file = tmp_path / ".test.lock"
    with (
        ProcessLock(lock_file),
        pytest.raises(RuntimeError, match="Another audit/update process is currently running"),
        ProcessLock(lock_file),
    ):
        pass


def test_persist_state_report_unique_filenames(tmp_path: Path) -> None:
    state_dir = tmp_path / "audit_state"
    rep = AuditReport(
        timestamp="2026-08-29 18:00:00",
        release={"version": "3.7.8", "tag": "v3.7.8"},
        venvs=[],
        mcp_configs=[],
        skills=[],
        applied=False,
        recorded=False,
        has_drift=False,
    )
    saved1 = persist_state_report(rep, state_dir)
    saved2 = persist_state_report(rep, state_dir)

    assert saved1.is_file()
    assert saved2.is_file()
    assert saved1 != saved2  # Distinct filename avoiding timestamp collision
    assert (state_dir / "latest.json").is_file()

    data = json.loads(saved1.read_text(encoding="utf-8"))
    assert data["release"]["version"] == "3.7.8"


def test_run_audit_release_failure_persists_state_and_log(tmp_path: Path) -> None:
    vault = tmp_path / "brain"
    vault.mkdir()
    (vault / "log.md").write_text("# Operational Log\n", encoding="utf-8")
    state_dir = tmp_path / "state"

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("release endpoint unavailable"),
    ):
        report, code = run_audit(
            repo="invalid/power",
            ref="latest",
            vault_path=vault,
            state_dir=state_dir,
            record=True,
            fail_on_drift=True,
        )

    assert code == 1
    assert "error" in report.release
    assert (state_dir / "latest.json").is_file()
    log_content = (vault / "log.md").read_text(encoding="utf-8")
    assert "Release validation failed" in log_content


def test_run_audit_fail_on_drift_detects_manual_review_and_missing(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text(
        '[project]\nname = "power-framework"\nversion = "3.7.8"\n',
        encoding="utf-8",
    )
    (source / "skills" / "power").mkdir(parents=True)
    (source / "skills" / "power" / "SKILL.md").write_text(
        "---\nname: power\nversion: 3.7.8\n---\n",
        encoding="utf-8",
    )

    # MCP config with JSONC comment -> manual_review
    mcp_file = tmp_path / "opencode.jsonc"
    mcp_file.write_text('{\n  // custom user comment\n  "mcp": {}\n}\n', encoding="utf-8")

    state_dir = tmp_path / "state"
    vault = tmp_path / "brain"
    vault.mkdir()

    report, code = run_audit(
        source_dir=source,
        vault_path=vault,
        state_dir=state_dir,
        venv_roots=[],
        skill_targets=[],
        mcp_configs=[mcp_file],
        apply=False,
        record=False,
        fail_on_drift=True,
    )

    assert report.has_drift is True
    assert report.mcp_configs[0].status == "manual_review"
    assert code == 2  # Drift exit code


def test_record_brain_log_distinguishes_audit_and_apply(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    log_file = vault / "log.md"
    log_file.write_text("# Operational Log\n", encoding="utf-8")

    rep_audit = AuditReport(
        timestamp="2026-08-29 18:00:00",
        release={"version": "3.7.8", "tag": "v3.7.8"},
        venvs=[],
        mcp_configs=[],
        skills=[],
        applied=False,
        recorded=False,
        has_drift=False,
    )
    rep_apply = AuditReport(
        timestamp="2026-08-29 18:00:00",
        release={"version": "3.7.8", "tag": "v3.7.8"},
        venvs=[],
        mcp_configs=[],
        skills=[],
        applied=True,
        recorded=False,
        has_drift=False,
    )

    # 1. Audit log recorded
    assert record_brain_log(vault, rep_audit) is True
    # 2. Apply log is NOT deduplicated against audit log
    assert record_brain_log(vault, rep_apply) is True

    content = log_file.read_text(encoding="utf-8")
    assert "Runtime Audit (v3.7.8)" in content
    assert "Runtime Apply (v3.7.8)" in content

    # 3. Second identical apply log IS deduplicated
    assert record_brain_log(vault, rep_apply) is False


def test_run_audit_record_failure_is_not_reported_as_success(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text(
        '[project]\nname = "power-framework"\nversion = "3.7.8"\n',
        encoding="utf-8",
    )
    vault = tmp_path / "vault"
    vault.mkdir()

    report, code = run_audit(
        source_dir=source,
        vault_path=vault,
        state_dir=tmp_path / "state",
        venv_roots=[],
        skill_targets=[],
        mcp_configs=[],
        record=True,
    )

    assert code == 1
    assert report.recorded is False
    assert any("canonical brain log" in error.lower() for error in report.errors)


def test_format_human_report() -> None:
    rep = AuditReport(
        timestamp="2026-08-29 18:00:00",
        release={"version": "3.7.8", "tag": "v3.7.8"},
        venvs=[
            VenvAuditResult(
                path="/root/.local/share/power/current/venv",
                python_path="/root/.local/share/power/current/venv/bin/python",
                installed_version="3.7.8",
                is_writable=True,
                status="up_to_date",
            )
        ],
        mcp_configs=[],
        skills=[],
        applied=False,
        recorded=False,
        has_drift=False,
    )
    formatted = format_human_report(rep)
    assert "P.O.W.E.R Host-side Runtime Audit Report" in formatted
    assert "ALL UP TO DATE" in formatted


def test_run_audit_pipeline_reads_back_updated_version(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text(
        '[project]\nname = "power-framework"\nversion = "3.7.8"\n',
        encoding="utf-8",
    )
    (source / ".agents" / "skills" / "power").mkdir(parents=True)
    (source / ".agents" / "skills" / "power" / "SKILL.md").write_text(
        "---\nname: power\nversion: 3.7.8\n---\n",
        encoding="utf-8",
    )

    vault = tmp_path / "brain"
    vault.mkdir()
    (vault / "log.md").write_text("# Log\n", encoding="utf-8")
    state_dir = tmp_path / "state"

    skill_target = tmp_path / "skills_dest" / "power"

    report, code = run_audit(
        source_dir=source,
        vault_path=vault,
        state_dir=state_dir,
        venv_roots=[tmp_path / "venvs"],
        skill_targets=[skill_target],
        mcp_configs=[],
        apply=True,
        record=True,
        fail_on_drift=False,
    )

    assert code == 0
    assert report.applied is True
    assert report.recorded is True
    assert report.skills[0].status == "up_to_date"
    assert report.skills[0].installed_version == "3.7.8"

    latest_data = json.loads((state_dir / "latest.json").read_text(encoding="utf-8"))
    assert latest_data["recorded"] is True


def test_main_cli_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text(
        '[project]\nname = "power-framework"\nversion = "3.7.8"\n',
        encoding="utf-8",
    )
    (source / "skills" / "power").mkdir(parents=True)
    (source / "skills" / "power" / "SKILL.md").write_text(
        "---\nname: power\nversion: 3.7.8\n---\n",
        encoding="utf-8",
    )

    skill_target = tmp_path / "skill_target"
    skill_target.mkdir(parents=True)
    (skill_target / "SKILL.md").write_text(
        "---\nname: power\nversion: 3.7.8\n---\n",
        encoding="utf-8",
    )

    stdout_capture = io.StringIO()
    monkeypatch.setattr("sys.stdout", stdout_capture)

    code = main(
        [
            "--source-dir",
            str(source),
            "--state-dir",
            str(tmp_path / "state"),
            "--vault",
            str(tmp_path / "vault"),
            "--venv-root",
            str(tmp_path / "venvs"),
            "--skill-target",
            str(skill_target),
            "--mcp-config",
            str(tmp_path / "mcp_clean.json"),
            "--json",
        ]
    )

    parsed = json.loads(stdout_capture.getvalue())
    assert parsed["release"]["version"] == "3.7.8"
    assert code == 0


def test_fetch_from_github_apply_requires_verified_wheel(tmp_path: Path) -> None:
    release_json = {
        "tag_name": "v3.7.8",
        "prerelease": False,
        "draft": False,
        "assets": [],  # No wheel asset
    }
    pyproject_text = '[project]\nname = "power-framework"\nversion = "3.7.8"\n'
    manifest_json = {
        "schema": "power.release.manifest.v1",
        "version": "3.7.8",
        "commit": "a" * 40,
        "artifacts": {
            "power_wheel": {
                "filename": "power_framework-3.7.8-py3-none-any.whl",
                "sha256": "c" * 64,
            }
        },
    }
    _add_published_manifest_asset(release_json, manifest_json)

    def urlopen_side_effect(req: urllib.request.Request, **kwargs: Any) -> MagicMock:
        url = req.full_url
        mock = MagicMock()
        mock.__enter__.return_value = mock
        if url.endswith("/releases/latest"):
            mock.read.return_value = json.dumps(release_json).encode("utf-8")
        elif "pyproject.toml" in url:
            mock.read.return_value = pyproject_text.encode("utf-8")
        elif "power-release-manifest.json" in url:
            mock.read.return_value = json.dumps(manifest_json).encode("utf-8")
        return mock

    state_dir = tmp_path / "state"
    vault = tmp_path / "brain"
    vault.mkdir()

    with patch("urllib.request.urlopen", side_effect=urlopen_side_effect):
        # 1. Audit-only mode preserves audit report without failing on wheel absence
        rep_audit, code_audit = run_audit(
            repo="weby-homelab/power-framework",
            ref="latest",
            vault_path=vault,
            state_dir=state_dir,
            venv_roots=[],
            skill_targets=[],
            mcp_configs=[],
            apply=False,
            fail_on_drift=False,
        )
        assert code_audit == 0
        assert rep_audit.applied is False

        # 2. Apply mode fails closed with explicit actionable error
        rep_apply, code_apply = run_audit(
            repo="weby-homelab/power-framework",
            ref="latest",
            vault_path=vault,
            state_dir=state_dir,
            venv_roots=[],
            skill_targets=[],
            mcp_configs=[],
            apply=True,
            fail_on_drift=False,
        )
        assert code_apply == 1
        assert rep_apply.applied is True
        assert any("verified release wheel" in err for err in rep_apply.errors)


def test_fetch_from_github_apply_missing_wheel_digest_fails_closed(tmp_path: Path) -> None:
    release_json = {
        "tag_name": "v3.7.8",
        "prerelease": False,
        "draft": False,
        "assets": [
            {
                "name": "power_framework-3.7.8-py3-none-any.whl",
                "browser_download_url": "https://github.com/weby-homelab/power-framework/releases/download/v3.7.8/power_framework-3.7.8-py3-none-any.whl",
            }
        ],
    }
    pyproject_text = '[project]\nname = "power-framework"\nversion = "3.7.8"\n'
    manifest_json = {
        "schema": "power.release.manifest.v1",
        "version": "3.7.8",
        "commit": "a" * 40,
        "artifacts": {
            "power_wheel": {
                "filename": "power_framework-3.7.8-py3-none-any.whl",
            }
        },
    }
    _add_published_manifest_asset(release_json, manifest_json)

    def urlopen_side_effect(req: urllib.request.Request, **kwargs: Any) -> MagicMock:
        url = req.full_url
        mock = MagicMock()
        mock.__enter__.return_value = mock
        if url.endswith("/releases/latest"):
            mock.read.return_value = json.dumps(release_json).encode("utf-8")
        elif "pyproject.toml" in url:
            mock.read.return_value = pyproject_text.encode("utf-8")
        elif "power-release-manifest.json" in url:
            mock.read.return_value = json.dumps(manifest_json).encode("utf-8")
        return mock

    state_dir = tmp_path / "state"
    vault = tmp_path / "brain"
    vault.mkdir()

    with patch("urllib.request.urlopen", side_effect=urlopen_side_effect):
        # 1. Audit-only mode preserves audit report without failing on missing digest
        rep_audit, code_audit = run_audit(
            repo="weby-homelab/power-framework",
            ref="latest",
            vault_path=vault,
            state_dir=state_dir,
            venv_roots=[],
            skill_targets=[],
            mcp_configs=[],
            apply=False,
            fail_on_drift=False,
        )
        assert code_audit == 0
        assert rep_audit.applied is False

        # 2. Apply mode fails closed because wheel digest is missing
        rep_apply, code_apply = run_audit(
            repo="weby-homelab/power-framework",
            ref="latest",
            vault_path=vault,
            state_dir=state_dir,
            venv_roots=[],
            skill_targets=[],
            mcp_configs=[],
            apply=True,
            fail_on_drift=False,
        )
        assert code_apply == 1
        assert rep_apply.applied is True
        assert any("verified release wheel" in err for err in rep_apply.errors)


def test_github_fetch_uses_published_manifest_asset_not_raw_source() -> None:
    public_commit = "a" * 40
    stale_commit = "b" * 40
    wheel_sha = "c" * 64
    release_json = {
        "tag_name": "v3.7.8",
        "prerelease": False,
        "draft": False,
        "assets": [
            {
                "name": "power_framework-3.7.8-py3-none-any.whl",
                "browser_download_url": "https://github.com/weby-homelab/power-framework/releases/download/v3.7.8/power_framework-3.7.8-py3-none-any.whl",
                "digest": f"sha256:{wheel_sha}",
            }
        ],
    }
    pyproject_text = '[project]\nname = "power-framework"\nversion = "3.7.8"\n'
    public_manifest = {
        "schema": "power.release.manifest.v1",
        "version": "3.7.8",
        "commit": public_commit,
        "artifacts": {
            "power_wheel": {
                "filename": "power_framework-3.7.8-py3-none-any.whl",
                "sha256": wheel_sha,
            }
        },
    }
    stale_manifest = {
        "schema": "power.release.manifest.v1",
        "version": "3.7.8",
        "commit": stale_commit,
        "artifacts": {
            "power_wheel": {
                "filename": "power_framework-3.7.8-py3-none-any.whl",
                "sha256": wheel_sha,
            }
        },
    }
    public_manifest_bytes = json.dumps(public_manifest).encode("utf-8")
    release_json["assets"].append(
        {
            "name": "power-release-manifest.json",
            "browser_download_url": "https://github.com/weby-homelab/power-framework/releases/download/v3.7.8/power-release-manifest.json",
            "digest": f"sha256:{hashlib.sha256(public_manifest_bytes).hexdigest()}",
        }
    )
    calls: list[str] = []

    def urlopen_side_effect(req: Any, **kwargs: Any) -> MagicMock:
        url = req.full_url
        calls.append(url)
        mock = MagicMock()
        mock.__enter__.return_value = mock
        if url.endswith("/releases/tags/v3.7.8"):
            mock.read.return_value = json.dumps(release_json).encode("utf-8")
        elif url.endswith("/pyproject.toml"):
            mock.read.return_value = pyproject_text.encode("utf-8")
        elif url.endswith("/releases/download/v3.7.8/power-release-manifest.json"):
            mock.read.return_value = json.dumps(public_manifest).encode("utf-8")
        elif url.startswith("https://raw.githubusercontent.com/") and url.endswith(
            "/release/power-release-manifest.json"
        ):
            mock.read.return_value = json.dumps(stale_manifest).encode("utf-8")
        else:
            raise AssertionError(f"unexpected URL: {url}")
        return mock

    with patch("urllib.request.urlopen", side_effect=urlopen_side_effect):
        payload = fetch_release_payload(repo="weby-homelab/power-framework", ref="v3.7.8")

    assert payload.commit == public_commit
    assert (
        "https://github.com/weby-homelab/power-framework/releases/download/v3.7.8/power-release-manifest.json"
        in calls
    )
    assert not any(
        url.startswith("https://raw.githubusercontent.com/")
        and "power-release-manifest.json" in url
        for url in calls
    )


def test_apply_updates_mcp_backed_venv_and_retains_comment_guard(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text(
        '[project]\nname = "power-framework"\nversion = "3.7.8"\n',
        encoding="utf-8",
    )
    (source / "skills" / "power").mkdir(parents=True)
    (source / "skills" / "power" / "SKILL.md").write_text(
        "---\nname: power\nversion: 3.7.8\n---\n",
        encoding="utf-8",
    )

    # Build dummy wheel in source/dist
    dist_dir = source / "dist"
    dist_dir.mkdir()
    wheel_path = dist_dir / "power_framework-3.7.8-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(
            "power_framework/data/skills/power/SKILL.md", "---\nname: power\nversion: 3.7.8\n---\n"
        )

    # Create target venv with old version 3.4.5
    venv_dir = tmp_path / "venvs" / "power_venv"
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir(parents=True)
    (venv_dir / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    py_bin = bin_dir / "python"
    py_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    (bin_dir / "pip").write_text("#!/bin/sh\n", encoding="utf-8")

    site_pkg = venv_dir / "lib" / "python3.13" / "site-packages"
    dist_info = site_pkg / "power_framework-3.4.5.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.4.5\n",
        encoding="utf-8",
    )

    # power-mcp binary pointing to venv
    power_mcp = bin_dir / "power-mcp"
    power_mcp.write_text(f"#!{py_bin}\nimport sys\n", encoding="utf-8")
    power_mcp.chmod(0o755)

    # Canonical clean MCP config
    clean_mcp = tmp_path / "mcp_clean.json"
    clean_mcp.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "power": {
                        "command": str(power_mcp),
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    # Commented MCP config
    commented_mcp = tmp_path / "mcp_commented.jsonc"
    commented_mcp.write_text(
        f'{{\n  // User comments to preserve\n  "mcpServers": {{\n    "power": {{\n      "command": "{power_mcp}"\n    }}\n  }}\n}}\n',
        encoding="utf-8",
    )

    state_dir = tmp_path / "state"
    vault = tmp_path / "brain"
    vault.mkdir()

    # Mock subprocess.run for pip install to simulate successful installation
    def fake_subprocess_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        # Simulate pip upgrade: replace 3.4.5 with 3.7.8
        import shutil

        shutil.rmtree(dist_info)
        new_dist_info = site_pkg / "power_framework-3.7.8.dist-info"
        new_dist_info.mkdir(parents=True)
        (new_dist_info / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.7.8\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    import subprocess

    with patch("subprocess.run", side_effect=fake_subprocess_run):
        rep, code = run_audit(
            source_dir=source,
            vault_path=vault,
            state_dir=state_dir,
            venv_roots=[tmp_path / "venvs"],
            skill_targets=[],
            mcp_configs=[clean_mcp, commented_mcp],
            apply=True,
            record=False,
            fail_on_drift=True,
        )

    # Venv was updated to 3.7.8
    assert rep.venvs[0].status == "up_to_date"
    assert rep.venvs[0].installed_version == "3.7.8"

    # Clean MCP config reflects post-update installed version and status=canonical
    clean_res = next(m for m in rep.mcp_configs if m.config_path == str(clean_mcp))
    assert clean_res.installed_version == "3.7.8"
    assert clean_res.status == "canonical"

    # Commented MCP config remains manual_review and was NOT mutated, but populates runtime version
    commented_res = next(m for m in rep.mcp_configs if m.config_path == str(commented_mcp))
    assert commented_res.status == "manual_review"
    assert commented_res.has_comments is True
    assert commented_res.entry_present is True
    assert commented_res.installed_version == "3.7.8"
    assert "// User comments to preserve" in commented_mcp.read_text(encoding="utf-8")

    # Exit code is 2 because commented_mcp has drift (manual_review)
    assert code == 2


# ============================================================================
# 11. Additional Hermetic Hardening & Regression Tests
# ============================================================================


def test_root_var_run_guards_discovery_and_audit() -> None:
    # discover_bounded_venvs rejects scanning / or /var or /run
    assert discover_bounded_venvs(["/"]) == []
    assert discover_bounded_venvs(["/var"]) == []
    assert discover_bounded_venvs(["/run"]) == []
    assert discover_bounded_venvs(["/usr"]) == []

    res_root = audit_venv(Path("/"), "3.7.8")
    assert res_root.status == "unwritable"
    assert "System Python" in str(res_root.error)

    res_var = audit_venv(Path("/var"), "3.7.8")
    assert res_var.status == "unwritable"
    assert "System Python" in str(res_var.error)

    res_run = audit_venv(Path("/run"), "3.7.8")
    assert res_run.status == "unwritable"
    assert "System Python" in str(res_run.error)


def test_extract_skill_version_quoted_and_unquoted() -> None:
    # Double quotes
    assert extract_skill_version('---\nname: power\nversion: "3.7.8"\n---\n') == "3.7.8"
    # Single quotes
    assert extract_skill_version("---\nname: power\nversion: '3.7.8'\n---\n") == "3.7.8"
    # Unquoted
    assert extract_skill_version("---\nname: power\nversion: 3.7.8\n---\n") == "3.7.8"
    # Double quotes with inline comment
    assert extract_skill_version('---\nname: power\nversion: "3.7.8" # comment\n---\n') == "3.7.8"
    # Single quotes with prerelease
    assert (
        extract_skill_version("---\nname: power\nversion: '3.8.0rc1'  # release candidate\n---\n")
        == "3.8.0rc1"
    )
    # Empty or missing
    assert extract_skill_version("---\nname: power\nversion:\n---\n") is None
    assert extract_skill_version("---\nname: power\n---\n") is None
    assert extract_skill_version("# No frontmatter\n") is None


@pytest.mark.parametrize(
    "shebang_line",
    [
        "#!/usr/bin/env python3\n",
        "#!/usr/bin/env -S python3\n",
        "#!/usr/bin/env -S python3 -u\n",
        "#!/usr/bin/env -S python3 -B -u\n",
        "#!/usr/bin/env -Spython3\n",
        "#!/bin/env -S python3\n",
    ],
)
def test_resolve_mcp_runtime_env_shebang_variants(tmp_path: Path, shebang_line: str) -> None:
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    fake_python = bin_dir / "python3"
    fake_python.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_python.chmod(0o755)

    dist_info = venv / "lib" / "python3.13" / "site-packages" / "power_framework-3.7.8.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.7.8\n",
        encoding="utf-8",
    )

    power_mcp = bin_dir / "power-mcp"
    power_mcp.write_text(f"{shebang_line}import sys\n", encoding="utf-8")
    power_mcp.chmod(0o755)

    with patch("shutil.which", return_value=str(fake_python)):
        exe, run_py, inst_ver, err = resolve_mcp_runtime(str(power_mcp))
        assert exe == str(power_mcp)
        assert run_py == str(fake_python)
        assert inst_ver == "3.7.8"
        assert err is None


def test_run_audit_fail_on_drift_missing_mcp_config_file(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text(
        '[project]\nname = "power-framework"\nversion = "3.7.8"\n',
        encoding="utf-8",
    )
    (source / "skills" / "power").mkdir(parents=True)
    (source / "skills" / "power" / "SKILL.md").write_text(
        "---\nname: power\nversion: 3.7.8\n---\n",
        encoding="utf-8",
    )

    nonexistent_mcp = tmp_path / "missing_config.json"
    state_dir = tmp_path / "state"
    vault = tmp_path / "brain"
    vault.mkdir()

    report, code = run_audit(
        source_dir=source,
        vault_path=vault,
        state_dir=state_dir,
        venv_roots=[],
        skill_targets=[],
        mcp_configs=[nonexistent_mcp],
        apply=False,
        record=False,
        fail_on_drift=True,
    )

    assert report.has_drift is True
    assert report.mcp_configs[0].status == "missing_file"
    assert code == 2


def test_apply_skill_update_post_write_hash_failure_rolls_back(tmp_path: Path) -> None:
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    target = skill_root / "power"
    target.mkdir(parents=True)
    original_skill_md = "---\nname: power\nversion: 3.4.5\n---\n# Original Skill\n"
    original_ref = "# Original Ref\n"
    (target / "SKILL.md").write_text(original_skill_md, encoding="utf-8")
    (target / "references").mkdir()
    (target / "references" / "ref.md").write_text(original_ref, encoding="utf-8")

    new_skill_files = {
        "SKILL.md": b"---\nname: power\nversion: 3.7.8\n---\n# New Skill\n",
        "references/ref.md": b"# New Ref\n",
    }
    expected_new_hash = aggregate_tree_hash(new_skill_files)

    rel = ReleasePayload(
        tag="v3.7.8",
        version="3.7.8",
        pyproject_version="3.7.8",
        skill_tree_sha256=expected_new_hash,
        skill_files=new_skill_files,
    )
    audit = SkillAuditResult(
        target_path=str(target),
        installed_version="3.4.5",
        tree_sha256=aggregate_tree_hash(tree_from_directory(target)),
        status="upgrade_ready",
    )

    # Mock aggregate_tree_hash so that during post-replacement verification it simulates a mismatch
    real_aggregate_tree_hash = aggregate_tree_hash
    call_count = 0

    def mock_aggregate(files: dict[str, bytes]) -> str:
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            return "corrupted_hash_" + "0" * 49
        return real_aggregate_tree_hash(files)

    with patch("scripts.prxmx_power_runtime_audit.aggregate_tree_hash", side_effect=mock_aggregate):
        action, err = apply_skill_update(
            audit,
            rel,
            dry_run=False,
            allowed_roots=[skill_root],
        )

    assert action == "failed"
    assert "Installed skill tree hash mismatch" in str(err)

    # Assert target was restored to original version 3.4.5 files
    assert target.is_dir()
    assert (target / "SKILL.md").read_text(encoding="utf-8") == original_skill_md
    assert (target / "references" / "ref.md").read_text(encoding="utf-8") == original_ref

    # Assert no staging or prev directories left behind
    remaining = [p.name for p in skill_root.iterdir() if p.name != "power"]
    assert remaining == []


def test_run_audit_state_report_persist_failure_is_redacted_and_truthful(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text(
        '[project]\nname = "power-framework"\nversion = "3.7.8"\n',
        encoding="utf-8",
    )
    (source / "skills" / "power").mkdir(parents=True)
    (source / "skills" / "power" / "SKILL.md").write_text(
        "---\nname: power\nversion: 3.7.8\n---\n",
        encoding="utf-8",
    )

    state_dir = tmp_path / "state"
    vault = tmp_path / "brain"
    vault.mkdir()

    with patch(
        "scripts.prxmx_power_runtime_audit.persist_state_report",
        side_effect=OSError("Disk write error with token=<set-via-env> and password=<set-via-env>"),
    ):
        report, code = run_audit(
            source_dir=source,
            vault_path=vault,
            state_dir=state_dir,
            venv_roots=[],
            skill_targets=[],
            mcp_configs=[],
            apply=False,
            record=False,
            fail_on_drift=False,
        )

    assert code == 1
    assert any("Failed to persist state report" in err for err in report.errors)
    for err in report.errors:
        assert "<set-via-env>" not in err
        assert "[REDACTED]" in err


def test_audit_mcp_config_commented_opencode_jsonc_canonical_entry(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    py_bin = bin_dir / "python3"
    py_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    py_bin.chmod(0o755)

    dist_info = venv / "lib" / "python3.13" / "site-packages" / "power_framework-3.7.8.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.7.8\n",
        encoding="utf-8",
    )

    power_mcp = bin_dir / "power-mcp"
    power_mcp.write_text(f"#!{py_bin}\nimport sys\n", encoding="utf-8")
    power_mcp.chmod(0o755)

    config_path = tmp_path / "opencode.jsonc"
    raw_content = f"""{{
      // OpenCode Configuration for P.O.W.E.R MCP Server
      /* Multi-line metadata block
         containing special symbols * / and settings */
      "endpoint": "https://opencode.internal/api//v1",
      "escaped_note": "Includes \\"quotes\\" and // double-slash inside string",
      "mcp": {{
        "power": {{
          "type": "local",
          "command": ["{power_mcp}"],
          "environment": {{
            "POWER_VAULT": "/root/brain"
          }}
        }}
      }}
      // Trailing configuration comment
    }}"""
    config_path.write_text(raw_content, encoding="utf-8")

    res = audit_mcp_config(config_path, target_version="3.7.8")

    assert res.client == "opencode"
    assert res.config_format == "jsonc"
    assert res.status == "manual_review"
    assert res.has_comments is True
    assert res.entry_present is True
    assert res.executable == str(power_mcp)
    assert res.resolved_executable == str(power_mcp)
    assert res.runtime_python == str(py_bin)
    assert res.installed_version == "3.7.8"
    assert res.env_keys == ["POWER_VAULT"]
    assert res.error == "JSONC contains user comments; manual review required to preserve structure"

    # Disk content must NEVER be mutated or rewritten
    assert config_path.read_text(encoding="utf-8") == raw_content


def test_audit_mcp_config_commented_opencode_jsonc_nested_shell_wrapper(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    py_bin = bin_dir / "python3"
    py_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    py_bin.chmod(0o755)

    dist_info = venv / "lib" / "python3.13" / "site-packages" / "power_framework-3.7.8.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.7.8\n",
        encoding="utf-8",
    )

    # Level 2 inner wrapper execs python interpreter
    inner_wrapper = tmp_path / "power-mcp-inner.sh"
    inner_wrapper.write_text(
        f'#!/bin/sh\nexec {py_bin} -m power_framework.mcp "$@"\n',
        encoding="utf-8",
    )
    inner_wrapper.chmod(0o755)

    # Level 1 outer wrapper execs inner wrapper
    outer_wrapper = tmp_path / "power-mcp"
    outer_wrapper.write_text(
        f'#!/bin/sh\nexec {inner_wrapper} "$@"\n',
        encoding="utf-8",
    )
    outer_wrapper.chmod(0o755)

    config_path = tmp_path / "opencode.jsonc"
    raw_content = f"""{{
      // OpenCode MCP Configuration with nested wrappers
      /* Documentation: https://example.com/docs//setup */
      "custom_url": "https://service.internal/v2//call",
      "escaped_str": "Testing \\"inner quotes\\" // still string",
      "mcp": {{
        "power": {{
          "command": ["{outer_wrapper}"]
        }}
      }}
      /* End of settings */
    }}"""
    config_path.write_text(raw_content, encoding="utf-8")

    res = audit_mcp_config(config_path, target_version="3.7.8")

    assert res.client == "opencode"
    assert res.config_format == "jsonc"
    assert res.status == "manual_review"
    assert res.has_comments is True
    assert res.entry_present is True
    assert res.executable == str(outer_wrapper)
    assert res.resolved_executable == str(outer_wrapper)
    assert res.runtime_python == str(py_bin)
    assert res.installed_version == "3.7.8"
    assert res.error == "JSONC contains user comments; manual review required to preserve structure"

    # Disk content must NEVER be mutated or rewritten
    assert config_path.read_text(encoding="utf-8") == raw_content


def test_audit_mcp_config_commented_opencode_jsonc_outdated_version(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    py_bin = bin_dir / "python"
    py_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    py_bin.chmod(0o755)

    dist_info = venv / "lib" / "python3.13" / "site-packages" / "power_framework-3.4.5.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: power-framework\nVersion: 3.4.5\n",
        encoding="utf-8",
    )

    power_mcp = bin_dir / "power-mcp"
    power_mcp.write_text(f"#!{py_bin}\nimport sys\n", encoding="utf-8")
    power_mcp.chmod(0o755)

    config_path = tmp_path / "opencode.jsonc"
    config_path.write_text(
        f'{{\n  // User custom comment\n  "mcp": {{\n    "power": {{\n      "command": "{power_mcp}"\n    }}\n  }}\n}}\n',
        encoding="utf-8",
    )

    res = audit_mcp_config(config_path, target_version="3.7.8")

    assert res.status == "manual_review"
    assert res.has_comments is True
    assert res.entry_present is True
    assert res.executable == str(power_mcp)
    assert res.runtime_python == str(py_bin)
    assert res.installed_version == "3.4.5"
    assert res.error == "JSONC contains user comments; manual review required to preserve structure"
