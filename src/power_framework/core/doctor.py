"""Read-only runtime and vault diagnostics for humans and AI agents."""

from __future__ import annotations

import json
import logging
import os
import platform
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

from .coverage import get_index_coverage
from .generation_index import (
    IndexGenerationError,
    list_invalid_sources,
    resolve_active_generation_path,
)
from .vault_storage import existing_vault_db_path

logger = logging.getLogger("power")

DOCTOR_SCHEMA_VERSION = 1


def _issue(
    code: str, severity: str, message: str, remediation: str | None = None
) -> dict[str, str]:
    result = {"code": code, "severity": severity, "message": message}
    if remediation is not None:
        result["remediation"] = remediation
    return result


def _status(issues: list[dict[str, str]]) -> str:
    if any(issue["severity"] == "error" for issue in issues):
        return "error"
    if issues:
        return "degraded"
    return "ok"


def _connect_read_only(database: Path) -> sqlite3.Connection:
    """Open an existing SQLite database without creating or changing it."""
    return sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True, timeout=30)


def _read_index_counts(database: Path) -> tuple[int, int]:
    with closing(_connect_read_only(database)) as connection:
        files_row = connection.execute("SELECT COUNT(*) FROM file_metadata").fetchone()
        chunks_row = connection.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()
    if files_row is None or chunks_row is None:
        raise sqlite3.DatabaseError("index count query returned no rows")
    return int(files_row[0]), int(chunks_row[0])


def _model_is_cached() -> bool:
    """Return whether all canonical BGE files are already in the local HF cache.

    Direct snapshot inspection is intentional. This function is part of a
    read-only command and must never turn a diagnostic into a model download.
    """
    from .embeddings import BGE_M3_ONNX_REPO, BGE_M3_ONNX_REVISION

    cache_override = os.getenv("HF_HUB_CACHE")
    if cache_override:
        cache_root = Path(cache_override).expanduser()
    else:
        hf_home = os.getenv("HF_HOME")
        if hf_home:
            cache_root = Path(hf_home).expanduser() / "hub"
        else:
            xdg_cache = os.getenv("XDG_CACHE_HOME")
            cache_root = (
                Path(xdg_cache).expanduser() / "huggingface" / "hub"
                if xdg_cache
                else Path.home() / ".cache" / "huggingface" / "hub"
            )
    snapshot = (
        cache_root
        / f"models--{BGE_M3_ONNX_REPO.replace('/', '--')}"
        / "snapshots"
        / BGE_M3_ONNX_REVISION
    )
    for filename in ("model.onnx", "model.onnx.data", "tokenizer.json"):
        if not (snapshot / filename).is_file():
            raise FileNotFoundError(filename)
    return True


@contextmanager
def _offline_model_probe() -> Iterator[None]:
    """Force model loading and Hugging Face tooling to stay local."""
    names = ("POWER_MODEL_OFFLINE", "HF_HUB_OFFLINE", "HF_HUB_DISABLE_TELEMETRY")
    previous = {name: os.environ.get(name) for name in names}
    os.environ["POWER_MODEL_OFFLINE"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _probe_embedding_binding() -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Probe the actual canonical ONNX binding without downloading a model."""
    from .embeddings import (
        EMBED_PROVIDER,
        _preload_gpu_runtime,
        requested_device,
    )

    embedding: dict[str, Any] = {
        "provider": EMBED_PROVIDER,
        "requested_device": requested_device("POWER_EMBED_DEVICE"),
        "available_providers": [],
        "model_cached": False,
        "binding": "not_verified",
        "bound_provider": None,
        "probe_seconds": None,
    }
    issues: list[dict[str, str]] = []

    try:
        import onnxruntime as ort  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - platform-specific loader failures
        embedding["runtime"] = {"available": False, "error_type": type(exc).__name__}
        issues.append(
            _issue(
                "onnxruntime_unavailable",
                "error",
                f"onnxruntime could not be imported ({type(exc).__name__})",
                "Install the supported runtime and run power doctor again.",
            )
        )
        return embedding, issues

    embedding["runtime"] = {"available": True, "version": getattr(ort, "__version__", None)}
    try:
        _preload_gpu_runtime(ort)
        embedding["available_providers"] = list(ort.get_available_providers())
    except Exception as exc:  # pragma: no cover - defensive backend boundary
        embedding["binding"] = "not_verified"
        issues.append(
            _issue(
                "onnxruntime_provider_query_failed",
                "error",
                f"onnxruntime providers could not be queried ({type(exc).__name__})",
                "Repair the ONNX Runtime installation and run power doctor again.",
            )
        )
        return embedding, issues

    if EMBED_PROVIDER != "bge-m3":
        embedding["binding"] = "not_supported"
        issues.append(
            _issue(
                "embedding_probe_not_supported",
                "warning",
                f"The canonical binding probe does not cover POWER_EMBED_PROVIDER={EMBED_PROVIDER!r}.",
                "Use the canonical bge-m3 provider or verify the selected backend separately.",
            )
        )
        return embedding, issues

    try:
        with _offline_model_probe():
            _model_is_cached()
        embedding["model_cached"] = True
    except Exception as exc:
        embedding["binding"] = "not_verified"
        issues.append(
            _issue(
                "embedding_model_not_cached",
                "warning",
                "The pinned embedding model is not fully available in the local cache; binding was not verified.",
                "Run power sync once, then run power doctor again. doctor never downloads models.",
            )
        )
        embedding["cache_error_type"] = type(exc).__name__
        return embedding, issues

    try:
        from .embeddings import BGEM3OnnxManager

        started = time.perf_counter()
        with _offline_model_probe():
            manager = BGEM3OnnxManager()
            manager.embed("power doctor probe")
        elapsed = time.perf_counter() - started
        embedding["probe_seconds"] = round(elapsed, 3)
        embedding["bound_provider"] = manager.active_provider
        if not manager.active_provider:
            embedding["binding"] = "failed"
            issues.append(
                _issue(
                    "embedding_provider_unknown",
                    "error",
                    "The embedding session produced no active provider.",
                    "Run power doctor with the requested device configuration checked.",
                )
            )
        else:
            embedding["binding"] = "verified"
    except Exception as exc:
        embedding["binding"] = "failed"
        issues.append(
            _issue(
                "embedding_binding_failed",
                "error",
                f"The cached embedding session could not be created ({type(exc).__name__}).",
                "Check the requested device, provider DLLs, and run power doctor again.",
            )
        )
    return embedding, issues


def _probe_vault(vault_dir: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Inspect a vault and its search state without creating cache or index files."""
    root = Path(vault_dir).expanduser().resolve()
    vault: dict[str, Any] = {
        "path": str(root),
        "exists": root.exists(),
        "is_directory": root.is_dir(),
        "database_path": None,
        "index_state": "not_checked",
        "active_generation": None,
        "indexed_notes": None,
        "indexed_chunks": None,
        "scanned_notes": None,
        "excluded_notes": [],
    }
    issues: list[dict[str, str]] = []

    if not root.is_dir():
        issues.append(
            _issue(
                "vault_not_directory",
                "error",
                f"Vault path is not an existing directory: {root}",
                "Pass a valid vault directory to power doctor.",
            )
        )
        return vault, issues

    try:
        active = resolve_active_generation_path(root)
    except IndexGenerationError as exc:
        vault["index_state"] = "unreadable"
        issues.append(
            _issue(
                "active_generation_unreadable",
                "error",
                f"The active search generation cannot be verified ({type(exc).__name__}).",
                "Run power sync PATH to rebuild a verified generation.",
            )
        )
        active = None
    except (OSError, ValueError) as exc:
        vault["index_state"] = "unreadable"
        issues.append(
            _issue(
                "active_generation_probe_failed",
                "error",
                f"The active search generation could not be inspected ({type(exc).__name__}).",
                "Check filesystem permissions and run power doctor again.",
            )
        )
        active = None

    database = active
    if active is not None:
        vault["index_state"] = "active_generation"
        vault["active_generation"] = active.name
    else:
        legacy: Path | None = None
        if vault["index_state"] != "unreadable":
            try:
                legacy = existing_vault_db_path(root)
            except (OSError, ValueError) as exc:
                vault["index_state"] = "unreadable"
                issues.append(
                    _issue(
                        "vault_identity_unreadable",
                        "error",
                        f"The vault identity could not be read ({type(exc).__name__}).",
                        "Repair .power/vault.json or restore the vault from a verified backup.",
                    )
                )
        if legacy is not None and legacy.is_file():
            database = legacy
            vault["index_state"] = "legacy_database"
        elif vault["index_state"] == "not_checked":
            vault["index_state"] = "missing"

    if database is not None and database.is_file():
        vault["database_path"] = str(database)
        try:
            indexed_notes, indexed_chunks = _read_index_counts(database)
            vault["indexed_notes"] = indexed_notes
            vault["indexed_chunks"] = indexed_chunks
        except (OSError, sqlite3.Error) as exc:
            vault["index_state"] = "unreadable"
            issues.append(
                _issue(
                    "search_database_unreadable",
                    "error",
                    f"The search database could not be read ({type(exc).__name__}).",
                    "Run power sync PATH to rebuild the search database.",
                )
            )
    elif vault["index_state"] == "missing":
        issues.append(
            _issue(
                "search_index_missing",
                "warning",
                "No searchable index is available for this vault.",
                "Run power sync PATH before relying on search results.",
            )
        )

    try:
        indexed, scanned = get_index_coverage(root)
        vault["indexed_notes"] = (
            indexed if vault["indexed_notes"] is None else vault["indexed_notes"]
        )
        vault["scanned_notes"] = scanned
    except Exception as exc:  # pragma: no cover - defensive filesystem boundary
        issues.append(
            _issue(
                "vault_coverage_unavailable",
                "error",
                f"Vault coverage could not be calculated ({type(exc).__name__}).",
                "Check vault readability and run power doctor again.",
            )
        )

    try:
        excluded = list_invalid_sources(root)
        vault["excluded_notes"] = [
            {"path": path, "reason": reason} for path, reason in sorted(excluded.items())
        ]
    except Exception as exc:  # pragma: no cover - defensive filesystem boundary
        issues.append(
            _issue(
                "vault_exclusion_scan_failed",
                "error",
                f"The exclusion ledger could not be calculated ({type(exc).__name__}).",
                "Check vault readability and run power doctor again.",
            )
        )

    excluded_count = len(vault["excluded_notes"])
    indexed_notes = vault["indexed_notes"]
    scanned_notes = vault["scanned_notes"]
    if excluded_count:
        issues.append(
            _issue(
                "notes_excluded",
                "warning",
                f"{excluded_count} note(s) would be excluded from the next index.",
                "Review excluded_notes, then repair or explicitly migrate the affected fields.",
            )
        )
    if indexed_notes is not None and scanned_notes is not None:
        expected_indexed = scanned_notes - excluded_count
        if (
            vault["index_state"] not in {"missing", "unreadable"}
            and indexed_notes != expected_indexed
        ):
            issues.append(
                _issue(
                    "index_coverage_mismatch",
                    "error",
                    f"Search index covers {indexed_notes} of {expected_indexed} currently indexable note(s).",
                    "Run power sync PATH and inspect its strict coverage receipt.",
                )
            )
    return vault, issues


def run_doctor(vault_dir: Path | None = None) -> dict[str, Any]:
    """Build the versioned, read-only doctor report."""
    try:
        package_version = distribution_version("power-framework")
    except PackageNotFoundError:
        package_version = None

    report: dict[str, Any] = {
        "schema_version": DOCTOR_SCHEMA_VERSION,
        "command": "doctor",
        "status": "ok",
        "runtime": {
            "python": platform.python_version(),
            "executable": os.path.abspath(sys.executable),
            "platform": platform.platform(),
            "power_framework": package_version,
        },
        "configuration": {},
        "embedding": {},
        "vault": None,
        "issues": [],
    }
    issues: list[dict[str, str]] = []
    from .embeddings import requested_device

    report["configuration"] = {
        "embed_device": requested_device("POWER_EMBED_DEVICE"),
        "reranker_device": requested_device("POWER_RERANKER_DEVICE"),
    }
    embedding, embedding_issues = _probe_embedding_binding()
    report["embedding"] = embedding
    issues.extend(embedding_issues)
    if vault_dir is not None:
        vault, vault_issues = _probe_vault(vault_dir)
        report["vault"] = vault
        issues.extend(vault_issues)
    report["issues"] = issues
    report["status"] = _status(issues)
    report["exit_code"] = 0 if report["status"] == "ok" else 1
    return report


def render_doctor(report: dict[str, Any]) -> str:
    """Render a concise human report while keeping JSON as the machine contract."""
    embedding = report["embedding"]
    lines = [
        "=== P.O.W.E.R. Doctor ===",
        f"Status          : {report['status']}",
        f"Python          : {report['runtime']['python']} ({report['runtime']['executable']})",
        f"Platform        : {report['runtime']['platform']}",
        f"power-framework : {report['runtime']['power_framework'] or 'distribution metadata unavailable'}",
        f"Reranker device : {report['configuration']['reranker_device']}",
        f"Embed provider  : {embedding.get('provider')}",
        f"Embed device    : {embedding.get('requested_device')}",
        f"onnxruntime     : {embedding.get('runtime', {}).get('version', 'unavailable')}",
        f"Providers listed: {', '.join(embedding.get('available_providers', [])) or 'unavailable'}",
        "NOTE: listed providers describe compiled support; only a created session proves binding.",
        f"Bound provider  : {embedding.get('bound_provider') or 'not verified'}",
    ]
    if embedding.get("probe_seconds") is not None:
        lines[-1] += f" (probe {embedding['probe_seconds']:.3f}s)"
    vault = report.get("vault")
    if vault is not None:
        lines.extend(
            [
                f"Vault           : {vault['path']}",
                f"Search index    : {vault['index_state']}",
                f"Index coverage  : {vault['indexed_notes']}/{vault['scanned_notes']}",
                f"Excluded now    : {len(vault['excluded_notes'])}",
            ]
        )
        lines.extend(
            f"  excluded: {excluded['path']} ({excluded['reason']})"
            for excluded in vault["excluded_notes"]
        )
    for issue in report["issues"]:
        lines.append(f"{issue['severity'].upper()}: {issue['code']}: {issue['message']}")
        if "remediation" in issue:
            lines.append(f"  remediation: {issue['remediation']}")
    return "\n".join(lines)


def report_as_json(report: dict[str, Any]) -> str:
    """Serialize a doctor report deterministically for agents and CI."""
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
