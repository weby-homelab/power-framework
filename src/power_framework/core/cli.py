"""
P.O.W.E.R. CLI — AI-Native Toolkit for Second Brain.

Usage:
    power init ~/my-vault
    power lint ~/my-vault
    power index ~/my-vault
    power ingest ~/my-vault --type Project --title "My Project" --description "A new project"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

try:  # resource is POSIX-only; Windows uses the no-limit path.
    import resource
except ImportError:  # pragma: no cover - exercised on Windows
    resource = None  # type: ignore[assignment]

from power_framework.experimental.relations import (
    format_relation_suggestions,
    suggest_related,
    suggest_related_v2,
)

from .application import ApplicationService, RequestContext
from .connect import apply_connect_plan, build_connect_plan
from .constants import SKIP_FILES
from .control_plane import (
    build_control_plane,
    build_obsidian_base,
    remove_obsidian_base,
    write_control_plane,
    write_obsidian_base,
)
from .doctor import render_doctor, report_as_json, run_doctor
from .domains import (
    DomainConfigError,
    domain_template_path,
    load_domain_registry,
    render_domain_template,
    route_domain,
)
from .healer import heal_vault_report
from .ignore import should_skip
from .importer import (
    ImportPolicy,
    apply_import_plan,
    build_import_plan,
    format_import_report,
)
from .indexer import generate_log_initial, run_generate_hierarchical_index
from .integrations import (
    apply_mcp_config_integration_plan,
    apply_native_install_plan,
    apply_skill_install_plan,
    build_integrations_doctor,
    build_mcp_config_integration_plan,
    build_native_install_plan,
    build_skill_check_plan,
)
from .linter import (
    archive_stale_notes,
    run_lint_report,
    run_lint_vault,
    run_rot_report,
    run_status_report,
)
from .maintenance import apply_maintenance_plan, build_maintenance_plan
from .markdown_checks import check_all as check_markdown_issues
from .memory_api import (
    commit_note_change,
    get_context,
    validate_state,
)
from .models import VAULT_STRUCTURE, NoteType, OKFMetadata
from .mutation import execute_vault_mutation
from .parser import build_frontmatter, read_file_content
from .searcher import (
    CANONICAL_SEARCH_MODES,
    DEFAULT_SEARCH_MODE,
    SEARCH_MODE_ALIASES,
)
from .state_migration import build_state_migration_plan
from .synthesize import synthesize_session_ingest
from .utils import __version__, atomic_write, enforce_cpu_throttling_env

logger = logging.getLogger("power")

if TYPE_CHECKING:
    from .generation_index import GenerationReport

TEMPLATE_NOTE = """\
---
type: {type}
title: "{title}"
description: "{description}"
tags: []
timestamp: {timestamp}
---

# {title}

Your content here.
"""


def _configure_windows_utf8_streams() -> None:
    """Keep CLI reports printable when Windows inherits a legacy code page."""
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                # Captured/embedded streams may reject runtime reconfiguration.
                continue


def _resolve_path(path_str: str) -> Path:
    """Resolve a vault path from CLI argument or environment variable."""
    if path_str:
        return Path(path_str).expanduser().resolve()
    env_val = os.getenv("POWER_VAULT_DIR") or os.getenv("POWER_VAULT_PATH")
    if env_val:
        return Path(env_val).resolve()
    return Path.cwd().resolve()


def _positive_int(value: str) -> int:
    """Parse a strictly positive CLI integer."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def _non_negative_int(value: str) -> int:
    """Parse a non-negative CLI integer."""
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be at least 0")
    return parsed


def _cmd_init(args: argparse.Namespace) -> int:
    """Create a new OKF-compliant vault structure."""
    vault_dir = _resolve_path(args.path)

    if vault_dir.exists() and any(vault_dir.iterdir()):
        logger.warning(
            "Directory %s is not empty. Use an empty directory or a new path.", vault_dir
        )
        return 1

    created = []
    for entry in VAULT_STRUCTURE:
        dir_path = vault_dir / entry
        dir_path.mkdir(parents=True, exist_ok=True)
        created.append(f"  {entry}/")

    index_path = vault_dir / "index.md"
    atomic_write(index_path, "")
    created.append("  index.md")

    template_path = vault_dir / "05_Templates" / "default.md"
    content = TEMPLATE_NOTE.format(
        type="Resource",
        title="Template Note",
        description="Default OKF template for new notes",
        timestamp=datetime.now(UTC).isoformat(),
    )
    atomic_write(template_path, content)
    created.append("  05_Templates/default.md")

    generate_log_initial(vault_dir, 0)
    created.append("  log.md")

    logger.info("Created vault structure at %s", vault_dir)
    for item in created:
        logger.info(item)
    logger.info("")
    logger.info("Next steps:")
    logger.info("  power index %s", args.path)
    logger.info("  power lint  %s", args.path)
    return 0


def _cmd_lint(args: argparse.Namespace) -> int:
    """Run health lint on the vault."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    result = run_lint_vault(vault_dir)
    logger.info(result.format_report(vault_dir))
    return 1 if result.has_blocking_issues else 0


def _cmd_index(args: argparse.Namespace) -> int:
    """Generate hierarchical index (index.md + _index.md files) from vault notes."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    msg = execute_vault_mutation(vault_dir, lambda: run_generate_hierarchical_index(vault_dir))
    logger.info("Generated hierarchical index:\n%s", msg)
    if args.strict and (
        "WARNING: skipped invalid notes (" in msg or "WARNING: catalog conflicts preserved (" in msg
    ):
        logger.error("Strict index check failed: notes or catalog files were skipped")
        return 1
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    """Create a new note with OKF metadata."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    note_type = args.type
    title = args.title
    description = args.description
    resource = args.resource
    tags = args.tags or []

    try:
        registry = load_domain_registry(vault_dir)
        domain = (
            registry.get(args.domain)
            if args.domain
            else route_domain(
                registry,
                title=title,
                description=description,
                tags=tags,
                note_type=note_type,
            )
        )
    except DomainConfigError as exc:
        logger.error("Invalid domain registry: %s", exc)
        return 1
    if args.domain and domain is None:
        logger.error("Unknown domain: %s", args.domain)
        return 1

    type_dir_map = {
        "Project": "01_Projects",
        "Area": "02_Areas",
        "Resource": "03_Resources",
        "Daily Log": "06_Daily_Logs",
        "Archive": "04_Archive",
        "System Guide": "PROTOCOLS",
    }
    target_dir = vault_dir / (domain.path if domain else type_dir_map.get(note_type, "00_Inbox"))
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = title.lower().replace(" ", "_").replace("/", "-")
    note_path = target_dir / f"{safe_name}.md"

    if note_path.exists() and not args.overwrite:
        logger.warning("Note already exists: %s", note_path)
        logger.warning("Use --overwrite to replace it.")
        return 1

    metadata = OKFMetadata(
        type=NoteType(note_type),
        title=title,
        description=description,
        resource=resource,
        tags=tags,
        timestamp=datetime.now(UTC),
    )
    fm = build_frontmatter(metadata)
    body = f"{fm}\n\n# {title}\n\n"
    if domain:
        try:
            template_path = domain_template_path(vault_dir, domain)
            template = template_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, DomainConfigError) as exc:
            logger.error("Cannot load template for domain %s: %s", domain.name, exc)
            return 1
        values = {
            "type": note_type,
            "title": title,
            "description": description,
            "timestamp": metadata.timestamp.isoformat(),
            "resource": resource or "",
            "tags": ", ".join(tags),
        }
        rendered = render_domain_template(template, values).strip()
        body = rendered if rendered.startswith("---") else f"{fm}\n\n{rendered}\n"
    relative_name = note_path.relative_to(vault_dir).as_posix()
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    log_entry = (
        f"\n## [{date_str}] ingest | Created {title}\n"
        f"- **Action:** Created note '{relative_name}' of type {note_type} via CLI ingest.\n"
        f"- **Result:** Saved note and compiled hierarchical index.\n"
    )
    try:
        receipt = commit_note_change(
            vault_dir,
            relative_name,
            body,
            require_absent=not args.overwrite,
            operation="cli.ingest",
            log_entry=log_entry,
        )
    except (FileExistsError, RuntimeError, ValueError, OSError) as exc:
        logger.error("Ingest transaction failed: %s", exc)
        return 1
    logger.info("Created note: %s", note_path.relative_to(vault_dir))
    logger.info("Search projection: %s (%s)", receipt["search_mode"], receipt["search_generation"])
    if domain:
        logger.info("Domain routing: %s (template: %s)", domain.name, domain.template)
    return 0


def _resolve_import_target(vault_dir: Path, relative_path: str) -> Path:
    """Resolve an import target inside the vault's documented note scope."""
    candidate = Path(relative_path).expanduser()
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("--into must be a relative path inside the vault")
    target = (vault_dir / candidate).resolve()
    try:
        target.relative_to(vault_dir)
    except ValueError as exc:
        raise ValueError("--into must stay inside the vault") from exc
    if not candidate.parts or candidate.parts[0] not in (*VAULT_STRUCTURE, "00_Inbox"):
        raise ValueError("--into must start with a P.A.R.A. or PROTOCOLS folder")
    return target


def _cmd_import(args: argparse.Namespace) -> int:
    """Preflight and import Markdown notes with an explicit compatibility policy."""
    vault_dir = _resolve_path(args.path)
    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.is_dir():
        logger.error("Import source directory not found: %s", source_dir)
        return 1
    if not vault_dir.is_dir():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    try:
        target_dir = _resolve_import_target(vault_dir, args.into)
    except ValueError as exc:
        logger.error("Invalid import target: %s", exc)
        return 1
    if source_dir == vault_dir or source_dir.is_relative_to(vault_dir):
        logger.error("Import source must be outside the target vault: %s", source_dir)
        return 1
    if target_dir.is_relative_to(source_dir):
        logger.error("Import target must not be inside the source directory: %s", source_dir)
        return 1

    plan = build_import_plan(source_dir, target_dir, ImportPolicy(args.policy))
    logger.info(format_import_report(plan, dry_run=args.dry_run))
    if plan.excluded and not args.allow_partial:
        logger.error(
            "Import failed closed: %d note(s) are excluded; pass --allow-partial to import the rest.",
            len(plan.excluded),
        )
        return 1
    if args.dry_run or not plan.will_write:
        return 0

    from .generation_index import IndexGenerationError, sync_vault_atomically

    try:

        def apply_and_index() -> tuple[int, tuple[str, GenerationReport]]:
            """Write the planned notes, then publish catalog and FTS state."""
            written = apply_import_plan(plan, allow_partial=args.allow_partial)
            index_message = run_generate_hierarchical_index(vault_dir)
            sync_report = sync_vault_atomically(vault_dir, sync_embeddings=False)
            return written, (index_message, sync_report)

        written, result = execute_vault_mutation(vault_dir, apply_and_index)
    except (IndexGenerationError, OSError, ValueError) as exc:
        logger.error("Import apply failed: %s", exc)
        return 1

    index_message, sync_report = result
    logger.info("Imported %d note(s).", written)
    logger.info("%s", index_message)
    if sync_report.invalid_sources:
        logger.error(
            "Import produced a partial searchable index: %d note(s) excluded.",
            sync_report.invalid_sources,
        )
        if not args.allow_partial:
            return 1
    logger.info(
        "FTS index ready: %d/%d notes indexed.",
        sync_report.actual_files,
        sync_report.total_scanned,
    )
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    """Search through the shared application boundary."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    query = args.query
    max_results = args.max_results
    mode = args.mode

    if args.json and args.envelope:
        logger.error("Choose only one of --json and --envelope")
        return 1
    envelope = ApplicationService(vault_dir).retrieve(
        query,
        max_results=max_results,
        mode=mode,
        temporal_view=args.temporal_view,
        as_of=args.as_of,
        domain=args.domain,
        context=RequestContext(actor="cli"),
    )
    if args.envelope:
        print(json.dumps(envelope.as_dict(), ensure_ascii=False, sort_keys=True))
    elif args.json:
        print(json.dumps(envelope.data, ensure_ascii=False, sort_keys=True))
    else:
        print(_format_retrieval_data(envelope.data), end="")
    return 0


def _format_retrieval_data(data: dict[str, object]) -> str:
    """Render application retrieval data without reopening storage."""
    query = str(data.get("query", ""))
    results = data.get("results", [])
    if not isinstance(results, list) or not results:
        return f"No results found for '{query}'.\n"
    actual_mode = str(data.get("actual_mode") or data.get("mode") or "unknown")
    lines = [
        f"=== Search Results for '{query}' ===",
        f"Mode: {actual_mode.upper()}  |  Found {len(results)} matching note(s):",
        "",
    ]
    for index, result in enumerate(results, 1):
        if not isinstance(result, dict):
            continue
        metadata = result.get("metadata", {})
        metadata = metadata if isinstance(metadata, dict) else {}
        source = result.get("source", {})
        source = source if isinstance(source, dict) else {}
        lines.append(
            f"{index}. [{metadata.get('note_type', 'Note')}] "
            f"{metadata.get('title', 'Untitled')}  (score: {float(result.get('score', 0)):.4f})"
        )
        lines.append(f"   Path: {source.get('path', 'unavailable')}")
        lines.append(f"   Temporal status: {metadata.get('temporal_status', 'unknown')}")
        lines.append(f"   {metadata.get('description', '')}")
        context = result.get("matched_text") or result.get("snippet") or ""
        if context:
            lines.append(f"   ...{context}...")
        lines.append("")
    return "\n".join(lines)


def _cmd_sync(args: argparse.Namespace) -> int:
    """Synchronously build the search index for the vault (FTS + embeddings)."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    from .generation_index import IndexGenerationError, sync_vault_atomically

    sync_embeddings = not getattr(args, "fts_only", False)

    # v2.2.0 low-RAM guard: cap the address space so an over-sized embedding
    # batch cannot trigger the kernel OOM-killer and take down the host. This is
    # an OPT-IN backstop (default 0 = disabled) because some backends (e.g.
    # Qwen3-0.6B ONNX) legitimately need >6 GB for their inference arena. Enable
    # it on tight 8 GB hosts via POWER_SYNC_VMEM_LIMIT_MB=6144.
    vmem_limit_mb = int(os.getenv("POWER_SYNC_VMEM_LIMIT_MB", "0"))
    if (
        vmem_limit_mb
        and sync_embeddings
        and resource is not None
        and hasattr(resource, "RLIMIT_AS")
    ):
        try:
            getrlimit = getattr(resource, "getrlimit")  # noqa: B009 - optional POSIX module.
            setrlimit = getattr(resource, "setrlimit")  # noqa: B009 - optional POSIX module.
            _, hard = getrlimit(resource.RLIMIT_AS)
            new_soft = (
                min(vmem_limit_mb * 1024 * 1024, hard) if hard > 0 else vmem_limit_mb * 1024 * 1024
            )
            setrlimit(resource.RLIMIT_AS, (new_soft, hard))
            logger.info("Applied virtual-memory cap: %d MB", vmem_limit_mb)
        except (ValueError, OSError) as e:  # pragma: no cover
            logger.warning("Could not apply vmem cap: %s", e)

    logger.info(
        "Building %s index for %s ...",
        "semantic" if sync_embeddings else "fts",
        vault_dir,
    )
    force_rebuild = getattr(args, "force", False)
    accept_dense_loss = getattr(args, "accept_dense_loss", False)
    try:
        report = execute_vault_mutation(
            vault_dir,
            lambda: sync_vault_atomically(
                vault_dir,
                sync_embeddings=sync_embeddings,
                force_rebuild=force_rebuild,
                accept_dense_loss=accept_dense_loss,
            ),
        )
    except IndexGenerationError as exc:
        logger.error("Index generation failed: %s", exc)
        return 1
    logger.info(
        "Index generation %s active: %d/%d files, %d chunks.",
        report.generation_id,
        report.actual_files,
        report.expected_files,
        report.actual_chunks,
    )
    logger.info(
        "Coverage: %d notes scanned, %d indexed, %d excluded.",
        report.total_scanned,
        report.actual_files,
        report.invalid_sources,
    )
    if report.excluded_reason_counts:
        reasons = ", ".join(
            f"{reason}={count}" for reason, count in report.excluded_reason_counts.items()
        )
        logger.info("Exclusion reasons: %s", reasons)
    if report.excluded_sources:
        allow_partial = getattr(args, "allow_partial", False)
        level = logger.warning if allow_partial else logger.error
        level(
            "%d note(s) are not searchable. %s",
            report.invalid_sources,
            "Continuing because --allow-partial was requested."
            if allow_partial
            else "Sync failed closed; pass --allow-partial to accept a partial index.",
        )
        for rel_path, reason in sorted(report.excluded_sources.items()):
            level("  excluded: %s (%s)", rel_path, reason)
        if not allow_partial:
            return 1
    return 0


def _cmd_rot(args: argparse.Namespace) -> int:
    """Run ROT (Redundant, Outdated, Trivial) audit."""
    logger.warning("Deprecated compatibility command: use 'power maintenance PATH' for the plan.")
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1
    report = run_rot_report(vault_dir, extended=args.extended)
    logger.info(report)
    return 0


def _cmd_archive(args: argparse.Namespace) -> int:
    """Move stale/expired notes to 04_Archive."""
    logger.warning(
        "Deprecated compatibility command: use 'power maintenance PATH' for the plan/apply gate."
    )
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1
    if args.dry_run:
        result = archive_stale_notes(vault_dir, dry_run=True)
    else:
        result = execute_vault_mutation(
            vault_dir, lambda: archive_stale_notes(vault_dir, dry_run=False)
        )
    logger.info(result)
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    """Show vault status dashboard."""
    logger.warning(
        "Deprecated compatibility command: use 'power doctor PATH' or 'power control-plane PATH'."
    )
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1
    report = run_status_report(vault_dir)
    print(report)
    return 0


def _cmd_control_plane(args: argparse.Namespace) -> int:
    """Preview or explicitly materialize the human-visible control plane."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1
    if args.remove_obsidian_base:
        logger.info("Obsidian Base removed: %s", remove_obsidian_base(vault_dir))
        return 0
    if args.apply:
        logger.info("Control plane written to %s", write_control_plane(vault_dir))
        if args.obsidian_base:
            logger.info("Obsidian Base written to %s", write_obsidian_base(vault_dir))
    elif args.obsidian_base:
        print(build_obsidian_base(), end="")
    else:
        print(build_control_plane(vault_dir), end="")
    return 0


def _cmd_maintenance(args: argparse.Namespace) -> int:
    """Preview policy-driven maintenance and apply only reversible actions."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1
    plan = build_maintenance_plan(vault_dir)
    if args.apply:
        receipt = apply_maintenance_plan(vault_dir, plan, approved=True)
        print(json.dumps(receipt.as_dict(), sort_keys=True))
    else:
        print(json.dumps(plan.as_dict(), ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_migrate_state(args: argparse.Namespace) -> int:
    """Print the read-only source/control/runtime/evidence inventory."""
    try:
        plan = build_state_migration_plan(_resolve_path(args.path))
    except (OSError, ValueError) as exc:
        logger.error("State migration plan failed: %s", exc)
        return 1
    print(json.dumps(plan.as_dict(), ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_cron(args: argparse.Namespace) -> int:
    """Run automated maintenance: lint + index + rot. Designed for cron/systemd timer."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    logger.info("=== P.O.W.E.R. Cron Maintenance ===")
    logger.info("Vault: %s", vault_dir)
    logger.info("")

    logger.info("--- Step 1: Lint ---")
    lint_report = run_lint_report(vault_dir)
    logger.info(lint_report)
    logger.info("")

    logger.info("--- Step 2: Index ---")
    index_msg = execute_vault_mutation(
        vault_dir, lambda: run_generate_hierarchical_index(vault_dir)
    )
    logger.info(index_msg)
    logger.info("")

    logger.info("--- Step 3: ROT Audit ---")
    rot_report = run_rot_report(vault_dir)
    logger.info(rot_report)

    return 0


def _cmd_heal(args: argparse.Namespace) -> int:
    """Heal missing/invalid frontmatter in vault notes."""
    logger.warning(
        "Deprecated compatibility command: use 'power maintenance PATH' for the plan/apply gate."
    )
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    dry_run = not args.no_dry_run
    limit = getattr(args, "limit", None)

    if dry_run:
        result = heal_vault_report(vault_dir, dry_run=True, limit=limit)
    else:
        result = execute_vault_mutation(
            vault_dir, lambda: heal_vault_report(vault_dir, dry_run=False, limit=limit)
        )
    logger.info(result.format())
    return result.exit_code


def _cmd_rename(args: argparse.Namespace) -> int:
    """Rename a vault note and update related paths in other notes."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    old_rel = args.old
    new_rel = args.new
    dry_run = not args.no_dry_run

    old_file = vault_dir / old_rel
    new_file = vault_dir / new_rel

    if not old_file.exists() or not old_file.is_file():
        logger.error("Source note not found: %s", old_file)
        return 1

    def _rename_and_propagate() -> tuple[int, list[str]]:
        """Perform the physical rename and reference propagation atomically."""
        new_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(old_file, new_file)
            logger.info("Physically renamed %s to %s", old_rel, new_rel)
        except Exception as e:
            logger.error("Failed to rename file physically: %s", e)
            raise

        from .healer import propagate_rename

        return propagate_rename(vault_dir, old_rel, new_rel, dry_run=False)

    if dry_run:
        logger.info("[DRY RUN] Would rename %s to %s", old_rel, new_rel)
        from .healer import propagate_rename

        updated_count, logs = propagate_rename(vault_dir, old_rel, new_rel, dry_run=True)
    else:
        updated_count, logs = execute_vault_mutation(vault_dir, _rename_and_propagate)

    if logs:
        logger.info("Updated references:")
        for log in logs:
            logger.info(log)
    else:
        logger.info("No other notes reference this path.")

    logger.info("Rename process completed. Updated notes: %d", updated_count)
    return 0


def _cmd_markdown_check(args: argparse.Namespace) -> int:
    """Check markdown quality (trailing whitespace, list markers, header jumps, code language)."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    total_issues = 0
    for filepath in vault_dir.rglob("*.md"):
        rel = filepath.relative_to(vault_dir)
        if should_skip(vault_dir, rel.as_posix()):
            continue
        if filepath.name in SKIP_FILES:
            continue

        try:
            content = read_file_content(filepath)
        except Exception as exc:
            logger.debug("Cannot read %s: %s", filepath, exc)
            continue

        issues = check_markdown_issues(content)
        if issues:
            total_issues += len(issues)
            logger.info("%s:", rel)
            for issue in issues:
                logger.info("  L%s: [%s] %s", issue["line"], issue["type"], issue["context"])

    logger.info("\nTotal issues found: %s", total_issues)
    return 0


def _cmd_suggest_related(args: argparse.Namespace) -> int:
    """Auto-suggest related notes via keyword/tag overlap."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1

    suggest_fn = suggest_related_v2 if getattr(args, "v2", False) else suggest_related
    suggestions = suggest_fn(
        vault_dir,
        target_path=args.target,
        max_results=args.max_results,
    )
    report = format_relation_suggestions(suggestions, vault_dir)
    logger.info(report)
    return 0


def _cmd_synthesize(args: argparse.Namespace) -> int:
    """Synthesize a session note and auto-ingest it into the vault (Phase 3)."""
    vault_dir = _resolve_path(args.path)
    if not vault_dir.exists():
        logger.error("Vault not found: %s", vault_dir)
        return 1
    try:
        report = synthesize_session_ingest(
            name=args.name,
            title=args.title,
            description=args.description,
            content=args.content,
            note_type=args.note_type,
            tags=args.tags,
            related=args.related,
            owner=args.owner,
            vault_path=str(vault_dir),
        )
    except (FileExistsError, RuntimeError, ValueError, OSError) as e:
        logger.error(str(e))
        return 1
    logger.info(report)
    return 0


def _cmd_cache(args: argparse.Namespace) -> int:
    """Inspect or prune per-vault cache namespaces."""
    from .vault_storage import classify_cache_namespaces, prune_vault_caches

    if args.cache_command == "list":
        namespaces = classify_cache_namespaces()
        total = sum(n.size_bytes for n in namespaces)
        logger.info("=== Cache Namespaces ===")
        logger.info("Count: %d  Total: %.1f MB", len(namespaces), total / 1024 / 1024)
        for namespace in namespaces:
            logger.info(
                "  %s  %-7s %8.0f KB  %s",
                namespace.vault_id,
                namespace.verdict,
                namespace.size_bytes / 1024,
                namespace.detail,
            )
        return 0

    logger.info(
        "%s",
        prune_vault_caches(dry_run=args.dry_run, include_unknown=args.include_unknown),
    )
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Run read-only runtime and vault diagnostics for humans or agents."""
    vault_dir = _resolve_path(args.path) if getattr(args, "path", None) else None
    report = run_doctor(vault_dir, probe_embedding=getattr(args, "probe_provider", False))
    if getattr(args, "json", False):
        print(report_as_json(report), end="")
    else:
        logger.info(render_doctor(report))
    return int(report["exit_code"])


def _cmd_connect(args: argparse.Namespace) -> int:
    """Plan or apply a conflict-safe local MCP client connection."""
    vault_dir = _resolve_path(args.path)
    try:
        if args.plan_file:
            plan = json.loads(Path(args.plan_file).read_text(encoding="utf-8"))
            if not isinstance(plan, dict):
                raise ValueError("connect plan must be a JSON object")
        else:
            plan = build_connect_plan(
                args.client,
                vault_dir,
                config_path=Path(args.config).expanduser() if args.config else None,
                executable=args.executable,
                action="remove" if args.remove else "install",
            ).as_dict()

        if args.plan_output:
            atomic_write(
                Path(args.plan_output).expanduser(),
                json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )
        if args.apply:
            receipt = apply_connect_plan(plan, approved=args.approved)
            print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
        else:
            print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
    except (KeyError, PermissionError, RuntimeError, ValueError, OSError) as exc:
        logger.error("Connect transaction failed: %s", exc)
        return 1
    return 0


def _cmd_integrations(args: argparse.Namespace) -> int:
    """Plan or apply generic, path-safe suite integration operations."""
    try:
        if args.integration_command == "doctor":
            print(json.dumps(build_integrations_doctor(), ensure_ascii=False, sort_keys=True))
        elif args.integration_command == "mcp-config":
            plan = build_mcp_config_integration_plan(
                args.path,
                client=args.client,
                config_path=args.config,
                executable=args.executable,
                remove=args.remove,
            )
            if args.plan_output:
                atomic_write(
                    Path(args.plan_output).expanduser(),
                    json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                )
            if args.apply:
                print(
                    json.dumps(
                        apply_mcp_config_integration_plan(plan, approved=args.approved),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
            else:
                print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        elif args.integration_command == "skill-check":
            print(
                json.dumps(build_skill_check_plan(args.target), ensure_ascii=False, sort_keys=True)
            )
        elif args.integration_command == "skill-install":
            plan = build_skill_check_plan(args.target)
            if args.apply:
                print(
                    json.dumps(
                        apply_skill_install_plan(plan, approved=args.approved),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
            else:
                print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        elif args.integration_command == "install":
            plan = build_native_install_plan(
                home=args.home,
                power_wheel=args.power_wheel,
                gui_wheel=args.gui_wheel,
            )
            if args.apply:
                print(
                    json.dumps(
                        apply_native_install_plan(
                            plan,
                            approved=args.approved,
                            no_deps=args.no_deps,
                        ),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
            else:
                print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        else:  # pragma: no cover - argparse enforces the choices
            raise ValueError(f"unsupported integration command: {args.integration_command}")
    except (KeyError, PermissionError, RuntimeError, ValueError, OSError) as exc:
        logger.error("Integration transaction failed: %s", exc)
        return 1
    return 0


def _cmd_memory(args: argparse.Namespace) -> int:
    vault_dir = _resolve_path(args.path)
    try:
        if args.memory_command == "context":
            print(json.dumps([item.rel_path for item in get_context(vault_dir, args.query)]))
        elif args.memory_command == "propose":
            if args.content is not None:
                raise ValueError(
                    "memory content is not accepted in argv; use --content-file or --content-stdin"
                )
            if args.content_file and args.content_stdin:
                raise ValueError("choose only one of --content-file and --content-stdin")
            if args.content_file:
                content = Path(args.content_file).read_text(encoding="utf-8")
            elif args.content_stdin:
                content = sys.stdin.read()
            else:
                raise ValueError("provide memory content through --content-file or --content-stdin")
            print(
                json.dumps(
                    ApplicationService(vault_dir)
                    .propose(
                        args.note_path,
                        content,
                        context=RequestContext(actor="cli", authority="propose"),
                    )
                    .data,
                    sort_keys=True,
                )
            )
        elif args.memory_command == "apply":
            if args.proposal is not None:
                raise ValueError(
                    "memory proposal is not accepted in argv; use --proposal-file or --proposal-stdin"
                )
            if args.proposal_file and args.proposal_stdin:
                raise ValueError("choose only one of --proposal-file and --proposal-stdin")
            if args.proposal_file:
                proposal_text = Path(args.proposal_file).read_text(encoding="utf-8")
            elif args.proposal_stdin:
                proposal_text = sys.stdin.read()
            else:
                raise ValueError(
                    "provide the durable memory proposal through --proposal-file or --proposal-stdin"
                )
            proposal = json.loads(proposal_text)
            print(
                json.dumps(
                    ApplicationService(vault_dir)
                    .apply(
                        proposal,
                        approved=args.approved,
                        context=RequestContext(actor="cli", authority="apply"),
                    )
                    .data,
                    sort_keys=True,
                )
            )
        elif args.memory_command == "validate":
            print(json.dumps({"valid": validate_state(vault_dir)}))
        else:
            print(
                json.dumps(
                    ApplicationService(vault_dir).receipt().data["receipts"],
                    sort_keys=True,
                )
            )
    except (PermissionError, RuntimeError, ValueError, OSError) as exc:
        logger.error("Memory transaction failed: %s", exc)
        return 1
    return 0


def _cmd_handoff(args: argparse.Namespace) -> int:
    """Create, inspect, or advance one canonical Task v2 record."""
    vault_dir = _resolve_path(args.path)
    service = ApplicationService(vault_dir)
    try:
        if args.handoff_command == "create":
            result = service.task(
                action="create",
                task_id=args.task_id,
                values={
                    "title": args.objective[:256],
                    "objective": args.objective,
                    "owner": args.owner,
                    "scope": args.scope,
                    "authority": args.authority,
                    "source_revision": args.source_revision,
                    "next_action": args.next_action,
                    "profile": args.profile,
                    "state": "submitted",
                    "required_input": (
                        {"required_approval": args.required_approval}
                        if args.required_approval
                        else None
                    ),
                },
                context=RequestContext(
                    actor=args.actor,
                    authority="propose",
                    idempotency_key=args.idempotency_key,
                ),
            ).data
        elif args.handoff_command == "show":
            result = service.task(action="read", task_id=args.task_id).data
        elif args.handoff_command == "list":
            result = {"packets": service.task(action="list").data}
        else:
            result = service.task(
                action="advance",
                task_id=args.task_id,
                values={
                    "action": args.handoff_command,
                    "expected_revision": args.expected_revision,
                    "approved": args.approved,
                    "next_action": args.next_action,
                    "blocker": args.blocker,
                    "required_approval": args.required_approval,
                    "receipt_id": args.receipt_id,
                    "changed_artifacts": args.changed_artifacts,
                    "open_gates": args.open_gates,
                    "phase": args.phase,
                    "completion_postcondition": args.completion_postcondition,
                    "completion_artifact_refs": args.changed_artifacts,
                },
                context=RequestContext(
                    actor=args.actor,
                    authority="apply",
                    idempotency_key=args.idempotency_key,
                ),
            ).data
    except (
        FileExistsError,
        FileNotFoundError,
        PermissionError,
        RuntimeError,
        ValueError,
        OSError,
    ) as exc:
        logger.error("Handoff transaction failed: %s", exc)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_task(args: argparse.Namespace) -> int:
    """Manage canonical Task v2 records through ApplicationService."""
    vault_dir = _resolve_path(args.path)
    service = ApplicationService(vault_dir)
    try:
        if args.task_command == "list":
            result = service.task_list(
                state=args.state,
                owner=args.owner,
                assignee=args.assignee,
                limit=args.limit,
                offset=args.offset,
            ).data
        elif args.task_command == "read":
            result = service.task_read(args.task_id).data
        elif args.task_command == "events":
            result = service.task_events(
                args.task_id,
                since_sequence=args.since_sequence,
            ).data
        elif args.task_command == "create":
            result = service.task_create(
                args.task_id,
                args.title,
                objective=args.objective,
                owner=args.owner,
                assignee=args.assignee,
                state=args.state,
                priority=args.priority,
                authority=args.authority,
                kind=args.kind,
                scope=args.scope,
                dependencies=args.dependencies,
                source_revision=args.source_revision,
                next_action=args.next_action,
                open_gates=args.open_gates,
                due_at=args.due_at,
                context=RequestContext(
                    actor=args.actor,
                    authority="propose",
                    idempotency_key=args.idempotency_key,
                ),
            ).data
        else:
            result = service.task_transition(
                args.task_id,
                args.state,
                expected_revision=args.expected_revision,
                receipt_id=args.receipt_id,
                next_action=args.next_action,
                assignee=args.assignee,
                open_gates=args.open_gates,
                error_ref=args.error_ref,
                completion_postcondition=args.completion_postcondition,
                completion_artifact_refs=args.completion_artifacts,
                context=RequestContext(
                    actor=args.actor,
                    authority="apply",
                    idempotency_key=args.idempotency_key,
                ),
            ).data
    except (
        FileExistsError,
        FileNotFoundError,
        PermissionError,
        RuntimeError,
        ValueError,
        OSError,
    ) as exc:
        logger.error("Task transaction failed: %s", exc)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def main() -> None:
    """P.O.W.E.R. CLI entry point."""
    enforce_cpu_throttling_env()
    _configure_windows_utf8_streams()
    parser = argparse.ArgumentParser(
        prog="power",
        description=f"P.O.W.E.R. {__version__} — Hybrid Knowledge Management Framework",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"P.O.W.E.R. {__version__} — Hybrid Knowledge Management Framework",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose logging (DEBUG level)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    p_init = subparsers.add_parser("init", help="Create a new OKF-compliant vault structure")
    p_init.add_argument("path", help="Path to the vault directory")
    p_init.set_defaults(func=_cmd_init)

    p_lint = subparsers.add_parser("lint", help="Run health lint on the vault")
    p_lint.add_argument("path", help="Path to the vault directory")
    p_lint.set_defaults(func=_cmd_lint)

    p_index = subparsers.add_parser(
        "index", help="Generate hierarchical index (index.md + per-folder _index.md)"
    )
    p_index.add_argument("path", help="Path to the vault directory")
    p_index.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Return non-zero when invalid notes were skipped (useful for CI)",
    )
    p_index.set_defaults(func=_cmd_index)

    p_ingest = subparsers.add_parser("ingest", help="Create a new note with OKF metadata")
    p_ingest.add_argument("path", help="Path to the vault directory")
    p_ingest.add_argument(
        "--type",
        "-t",
        required=True,
        choices=[t.value for t in NoteType],
        help="OKF note type",
    )
    p_ingest.add_argument("--title", required=True, help="Note title")
    p_ingest.add_argument("--description", required=True, help="Short summary (max 150 chars)")
    p_ingest.add_argument("--resource", default=None, help="External URL (optional)")
    p_ingest.add_argument("--tags", nargs="*", default=[], help="Markdown tags")
    p_ingest.add_argument("--overwrite", action="store_true", help="Overwrite existing note")
    p_ingest.add_argument(
        "--domain",
        default=None,
        help="Domain slug; without it, configured domain rules route the note automatically",
    )
    p_ingest.set_defaults(func=_cmd_ingest)

    p_import = subparsers.add_parser(
        "import",
        help="Preflight and import Markdown notes from another vault",
    )
    p_import.add_argument("source", help="Source directory containing Markdown notes")
    p_import.add_argument(
        "--into",
        required=True,
        help="Vault-relative destination folder, for example 03_Resources",
    )
    p_import.add_argument(
        "--path",
        default=None,
        help="Target vault path (defaults to POWER_VAULT_DIR or the current directory)",
    )
    p_import.add_argument(
        "--policy",
        choices=[policy.value for policy in ImportPolicy],
        default=ImportPolicy.STRICT.value,
        help="Foreign frontmatter policy (default: strict)",
    )
    p_import.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Only print the deterministic plan; do not write notes or indexes",
    )
    p_import.add_argument(
        "--allow-partial",
        action="store_true",
        default=False,
        help="Import valid notes even when some source notes remain excluded",
    )
    p_import.set_defaults(func=_cmd_import)

    p_search = subparsers.add_parser("search", help="Full-text search across vault notes")
    p_search.add_argument("path", help="Path to the vault directory")
    p_search.add_argument(
        "query", help='Search query (supports multiple terms and "quoted phrases")'
    )
    p_search.add_argument(
        "--temporal-view",
        choices=["current", "historical", "all"],
        default="current",
        help="Lifecycle projection: current (default), historical, or all including conflicts",
    )
    p_search.add_argument(
        "--as-of",
        default=None,
        help="Inclusive lifecycle boundary in ISO date format (YYYY-MM-DD)",
    )
    p_search.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Maximum number of results (default: 20)",
    )
    p_search.add_argument(
        "--mode",
        choices=sorted(CANONICAL_SEARCH_MODES | set(SEARCH_MODE_ALIASES) | {"auto"}),
        default=DEFAULT_SEARCH_MODE,
        help=(
            'Search mode: "auto" (default; verified dense or FTS), "fts" (BM25), '
            '"vector" (TF cosine), "hybrid" (RRF merged), or "semantic" '
            '(explicit dense embedding); "reranked" is an explicit opt-in. '
            '"auto" falls back to FTS when dense is not ready, and '
            '"hybrid_reranked" is a deprecated alias.'
        ),
    )
    p_search.add_argument("--domain", default=None, help="Optional domain slug to scope the search")
    p_search.add_argument(
        "--json", action="store_true", help="Emit retrieval data as versioned JSON"
    )
    p_search.add_argument(
        "--envelope", action="store_true", help="Emit the full application envelope as JSON"
    )
    p_search.set_defaults(func=_cmd_search)

    p_cache = subparsers.add_parser(
        "cache", help="Inspect or prune per-vault cache namespaces in the user cache"
    )
    cache_sub = p_cache.add_subparsers(dest="cache_command", required=True)
    cache_sub.add_parser(
        "list", help="Show every cache namespace and whether its vault still exists"
    )
    p_prune = cache_sub.add_parser(
        "prune", help="Remove cache namespaces whose vault is provably gone"
    )
    p_prune.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        default=True,
        help="Actually delete; default is a preview only",
    )
    p_prune.add_argument(
        "--include-unknown",
        action="store_true",
        default=False,
        help=(
            "Also remove namespaces with no source record. These predate the "
            "back-reference and cannot be attributed to any vault"
        ),
    )
    p_cache.set_defaults(func=_cmd_cache)

    p_doctor = subparsers.add_parser(
        "doctor",
        help="Diagnose runtime, ONNX provider binding, and index coverage without writes",
    )
    p_doctor.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Optional vault path to inspect without creating cache or index state",
    )
    p_doctor.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit the versioned machine-readable report to stdout",
    )
    p_doctor.add_argument(
        "--probe-provider",
        action="store_true",
        default=False,
        help="Explicitly probe the configured provider without downloading a model",
    )
    p_doctor.set_defaults(func=_cmd_doctor)

    p_integrations = subparsers.add_parser(
        "integrations",
        help="Plan or apply generic POWER suite integrations (dry-run by default)",
    )
    integration_sub = p_integrations.add_subparsers(dest="integration_command", required=True)
    integration_sub.add_parser(
        "doctor", help="Read-only integration, launcher, SDK, and Skill diagnostics"
    ).set_defaults(func=_cmd_integrations)

    p_mcp_config = integration_sub.add_parser(
        "mcp-config", help="Plan or apply a hash-bound local MCP client configuration"
    )
    p_mcp_config.add_argument("path", help="Path to the POWER vault")
    p_mcp_config.add_argument(
        "--client",
        choices=["auto", "codex", "opencode", "gemini", "claude"],
        default="auto",
        help="Client to configure",
    )
    p_mcp_config.add_argument("--config", default=None, help="Explicit client config path")
    p_mcp_config.add_argument(
        "--executable",
        default="power-mcp",
        help="Public MCP launcher (default: power-mcp)",
    )
    p_mcp_config.add_argument("--remove", action="store_true", help="Plan removal")
    p_mcp_config.add_argument("--apply", action="store_true", help="Apply the plan")
    p_mcp_config.add_argument(
        "--approved", action="store_true", help="Explicitly approve the config write"
    )
    p_mcp_config.add_argument("--plan-output", default=None, help="Write the plan to JSON")
    p_mcp_config.set_defaults(func=_cmd_integrations)

    p_skill_check = integration_sub.add_parser(
        "skill-check", help="Read-only check of a packaged POWER Skill installation"
    )
    p_skill_check.add_argument(
        "--target",
        default=str(Path.home() / ".agents" / "skills" / "power"),
        help="Skill target directory",
    )
    p_skill_check.set_defaults(func=_cmd_integrations)

    p_skill_install = integration_sub.add_parser(
        "skill-install", help="Plan or atomically install the packaged POWER Skill"
    )
    p_skill_install.add_argument(
        "--target",
        default=str(Path.home() / ".agents" / "skills" / "power"),
        help="Skill target directory",
    )
    p_skill_install.add_argument("--apply", action="store_true", help="Apply the plan")
    p_skill_install.add_argument(
        "--approved", action="store_true", help="Explicitly approve the Skill write"
    )
    p_skill_install.set_defaults(func=_cmd_integrations)

    p_install = integration_sub.add_parser(
        "install", help="Plan or install an exact wheel pair into the managed native venv"
    )
    p_install.add_argument(
        "--home", default=None, help="Disposable HOME root for the managed profile"
    )
    p_install.add_argument("--power-wheel", required=True, help="Exact POWER framework wheel")
    p_install.add_argument("--gui-wheel", default=None, help="Optional exact POWER-GUI wheel")
    p_install.add_argument("--no-deps", action="store_true", help="Skip dependency resolution")
    p_install.add_argument("--apply", action="store_true", help="Apply the plan")
    p_install.add_argument(
        "--approved", action="store_true", help="Explicitly approve the native install"
    )
    p_install.set_defaults(func=_cmd_integrations)

    p_connect = subparsers.add_parser(
        "connect", help="Plan or apply a conflict-safe local MCP client connection"
    )
    p_connect.add_argument("path", help="Path to the POWER vault")
    p_connect.add_argument(
        "--client",
        choices=["auto", "codex", "opencode", "gemini", "claude"],
        default="auto",
        help="Client to configure (default: detect an existing supported client config)",
    )
    p_connect.add_argument(
        "--config",
        default=None,
        help="Explicit client config path; required when the config does not exist yet",
    )
    p_connect.add_argument(
        "--executable",
        default=sys.executable,
        help="Python executable used by the local MCP server command",
    )
    p_connect.add_argument(
        "--remove", action="store_true", help="Plan removal of the POWER-owned entry"
    )
    p_connect.add_argument("--apply", action="store_true", help="Apply the plan after --approved")
    p_connect.add_argument(
        "--approved", action="store_true", help="Explicitly approve the requested config write"
    )
    p_connect.add_argument(
        "--plan-file", default=None, help="Read an exact previously generated plan from JSON"
    )
    p_connect.add_argument(
        "--plan-output", default=None, help="Write the content-free plan to this JSON path"
    )
    p_connect.set_defaults(func=_cmd_connect)

    p_memory = subparsers.add_parser("memory", help="Human-governed transactional memory workflow")
    memory_sub = p_memory.add_subparsers(dest="memory_command", required=True)
    p_context = memory_sub.add_parser("context")
    p_context.add_argument("path")
    p_context.add_argument("query")
    p_propose = memory_sub.add_parser("propose")
    p_propose.add_argument("path")
    p_propose.add_argument("note_path")
    p_propose.add_argument(
        "content",
        nargs="?",
        help="Deprecated positional content is rejected to keep secrets out of argv",
    )
    p_propose.add_argument("--content-file", help="Read proposal content from a local file")
    p_propose.add_argument(
        "--content-stdin", action="store_true", help="Read proposal content from stdin"
    )
    p_apply = memory_sub.add_parser("apply")
    p_apply.add_argument("path")
    p_apply.add_argument(
        "proposal",
        nargs="?",
        help="Deprecated positional proposal JSON is rejected to keep secrets out of argv",
    )
    p_apply.add_argument("--proposal-file", help="Read durable proposal JSON from a local file")
    p_apply.add_argument(
        "--proposal-stdin", action="store_true", help="Read durable proposal JSON from stdin"
    )
    p_apply.add_argument("--approved", action="store_true")
    p_validate = memory_sub.add_parser("validate")
    p_validate.add_argument("path")
    p_history = memory_sub.add_parser("history")
    p_history.add_argument("path")
    p_memory.set_defaults(func=_cmd_memory)

    p_handoff = subparsers.add_parser(
        "handoff", help="Persist and advance a durable cross-agent work packet"
    )
    handoff_sub = p_handoff.add_subparsers(dest="handoff_command", required=True)
    p_handoff_create = handoff_sub.add_parser("create")
    p_handoff_create.add_argument("path")
    p_handoff_create.add_argument("--task-id", required=True)
    p_handoff_create.add_argument("--objective", required=True)
    p_handoff_create.add_argument("--owner", required=True)
    p_handoff_create.add_argument("--actor", required=True)
    p_handoff_create.add_argument("--scope", nargs="*", default=[])
    p_handoff_create.add_argument(
        "--authority", choices=["read-only", "propose", "apply"], default="read-only"
    )
    p_handoff_create.add_argument("--source-revision", default="unknown")
    p_handoff_create.add_argument("--next-action", default="inspect")
    p_handoff_create.add_argument(
        "--profile", choices=["standard", "maintenance"], default="standard"
    )
    p_handoff_create.add_argument("--required-approval", default=None)
    p_handoff_create.add_argument("--idempotency-key", default=None)
    p_handoff_create.set_defaults(func=_cmd_handoff)

    p_handoff_list = handoff_sub.add_parser("list")
    p_handoff_list.add_argument("path")
    p_handoff_list.set_defaults(func=_cmd_handoff)

    p_handoff_show = handoff_sub.add_parser("show")
    p_handoff_show.add_argument("path")
    p_handoff_show.add_argument("--task-id", required=True)
    p_handoff_show.set_defaults(func=_cmd_handoff)

    for handoff_action in ("resume", "checkpoint", "input-required", "complete", "fail", "cancel"):
        transition = handoff_sub.add_parser(handoff_action)
        transition.add_argument("path")
        transition.add_argument("--task-id", required=True)
        transition.add_argument("--idempotency-key", required=True)
        transition.add_argument("--actor", required=True)
        transition.add_argument("--expected-revision", required=True, type=int)
        transition.add_argument("--approved", action="store_true")
        transition.add_argument("--next-action", default=None)
        transition.add_argument("--blocker", default=None)
        transition.add_argument("--required-approval", default=None)
        transition.add_argument("--receipt-id", default=None)
        transition.add_argument("--completion-postcondition", default=None)
        transition.add_argument("--changed-artifacts", nargs="*", default=None)
        transition.add_argument("--open-gates", nargs="*", default=None)
        transition.add_argument("--phase", default=None)
        transition.set_defaults(func=_cmd_handoff)

    p_task = subparsers.add_parser("task", help="Manage canonical Task v2 records")
    task_sub = p_task.add_subparsers(dest="task_command", required=True)
    task_states = [
        "backlog",
        "ready",
        "submitted",
        "working",
        "input-required",
        "auth-required",
        "blocked",
        "completed",
        "failed",
        "canceled",
        "rejected",
    ]

    p_task_list = task_sub.add_parser("list")
    p_task_list.add_argument("path")
    p_task_list.add_argument("--state", choices=task_states, default=None)
    p_task_list.add_argument("--owner", default=None)
    p_task_list.add_argument("--assignee", default=None)
    p_task_list.add_argument("--limit", type=_positive_int, default=100)
    p_task_list.add_argument("--offset", type=_non_negative_int, default=0)
    p_task_list.set_defaults(func=_cmd_task)

    p_task_read = task_sub.add_parser("read")
    p_task_read.add_argument("path")
    p_task_read.add_argument("--task-id", required=True)
    p_task_read.set_defaults(func=_cmd_task)

    p_task_create = task_sub.add_parser("create")
    p_task_create.add_argument("path")
    p_task_create.add_argument("--task-id", required=True)
    p_task_create.add_argument("--title", required=True)
    p_task_create.add_argument("--objective", default="")
    p_task_create.add_argument("--owner", default="local")
    p_task_create.add_argument("--assignee", default=None)
    p_task_create.add_argument("--state", choices=task_states, default="backlog")
    p_task_create.add_argument(
        "--priority", choices=["low", "normal", "high", "critical"], default="normal"
    )
    p_task_create.add_argument(
        "--authority", choices=["read-only", "propose", "apply"], default="read-only"
    )
    p_task_create.add_argument(
        "--kind",
        choices=["human", "agent", "maintenance", "fleet", "federated"],
        default="human",
    )
    p_task_create.add_argument("--scope", nargs="*", default=[])
    p_task_create.add_argument("--dependencies", nargs="*", default=[])
    p_task_create.add_argument("--source-revision", default="")
    p_task_create.add_argument("--next-action", default="inspect")
    p_task_create.add_argument("--open-gates", nargs="*", default=[])
    p_task_create.add_argument("--due-at", default=None)
    p_task_create.add_argument("--actor", required=True)
    p_task_create.add_argument("--idempotency-key", required=True)
    p_task_create.set_defaults(func=_cmd_task)

    p_task_transition = task_sub.add_parser("transition")
    p_task_transition.add_argument("path")
    p_task_transition.add_argument("--task-id", required=True)
    p_task_transition.add_argument("--state", choices=task_states, required=True)
    p_task_transition.add_argument("--expected-revision", type=_positive_int, required=True)
    p_task_transition.add_argument("--actor", required=True)
    p_task_transition.add_argument("--idempotency-key", required=True)
    p_task_transition.add_argument("--receipt-id", default=None)
    p_task_transition.add_argument("--next-action", default=None)
    p_task_transition.add_argument("--assignee", default=None)
    p_task_transition.add_argument("--open-gates", nargs="*", default=None)
    p_task_transition.add_argument("--error-ref", default=None)
    p_task_transition.add_argument("--completion-postcondition", default=None)
    p_task_transition.add_argument("--completion-artifacts", nargs="*", default=None)
    p_task_transition.set_defaults(func=_cmd_task)

    p_task_events = task_sub.add_parser("events")
    p_task_events.add_argument("path")
    p_task_events.add_argument("--task-id", required=True)
    p_task_events.add_argument("--since-sequence", type=_non_negative_int, default=0)
    p_task_events.set_defaults(func=_cmd_task)

    p_sync = subparsers.add_parser(
        "sync", help="Build the search index for the vault (FTS + dense embeddings)"
    )
    p_sync.add_argument("path", help="Path to the vault directory")
    p_sync.add_argument(
        "--fts-only",
        action="store_true",
        default=False,
        help="Only build the lightweight FTS index (skip embedding generation)",
    )
    p_sync.add_argument(
        "--accept-dense-loss",
        action="store_true",
        default=False,
        help=(
            "Allow --fts-only to replace an existing dense index, discarding "
            "embeddings and disabling semantic/hybrid/reranked search"
        ),
    )
    p_sync.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force a full rebuild of dense embeddings (required after changing the embedding model/dimension)",
    )
    sync_coverage = p_sync.add_mutually_exclusive_group()
    sync_coverage.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Fail when any note is excluded (the default coverage policy)",
    )
    sync_coverage.add_argument(
        "--allow-partial",
        action="store_true",
        default=False,
        help="Accept excluded notes and exit zero with a complete exclusion receipt",
    )
    p_sync.set_defaults(func=_cmd_sync)

    p_rot = subparsers.add_parser("rot", help="Run ROT (Redundant, Outdated, Trivial) audit")
    p_rot.add_argument("path", help="Path to the vault directory")
    p_rot.add_argument(
        "--extended",
        action="store_true",
        default=False,
        help="Enable extended A2 scoring (content dedup, link rot, freshness, usage)",
    )
    p_rot.set_defaults(func=_cmd_rot)

    p_archive = subparsers.add_parser(
        "archive",
        help="Move stale/expired notes to 04_Archive",
    )
    p_archive.add_argument("path", help="Path to the vault directory")
    p_archive.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Simulate without moving (default: true)",
    )
    p_archive.add_argument(
        "--no-dry-run",
        action="store_false",
        dest="dry_run",
        help="Actually move files",
    )
    p_archive.set_defaults(func=_cmd_archive)

    p_status = subparsers.add_parser("status", help="Show vault status dashboard")
    p_status.add_argument(
        "path", nargs="?", default=None, help="Path to the vault directory (optional)"
    )
    p_status.set_defaults(func=_cmd_status)

    p_control = subparsers.add_parser(
        "control-plane", help="Preview or materialize the human-visible POWER status"
    )
    p_control.add_argument("path", help="Path to the vault directory")
    p_control.add_argument(
        "--apply", action="store_true", help="Write POWER_STATUS.md (default is read-only preview)"
    )
    p_control.add_argument(
        "--obsidian-base",
        action="store_true",
        help="Preview or also write the optional POWER Control.base asset",
    )
    p_control.add_argument(
        "--remove-obsidian-base",
        action="store_true",
        help="Remove only the generated POWER Control.base asset",
    )
    p_control.set_defaults(func=_cmd_control_plane)

    p_maintenance = subparsers.add_parser(
        "maintenance", help="Preview or apply hash-bound reversible maintenance"
    )
    p_maintenance.add_argument("path", help="Path to the vault directory")
    p_maintenance.add_argument(
        "--apply", action="store_true", help="Apply safe_auto actions with explicit approval"
    )
    p_maintenance.set_defaults(func=_cmd_maintenance)

    p_migrate_state = subparsers.add_parser(
        "migrate-state", help="Preview the read-only vault state-plane migration inventory"
    )
    p_migrate_state.add_argument("path", help="Path to the vault directory")
    p_migrate_state.set_defaults(func=_cmd_migrate_state)

    p_cron = subparsers.add_parser(
        "cron",
        help="Run automated maintenance: lint + index + rot audit",
    )
    p_cron.add_argument("path", help="Path to the vault directory")
    p_cron.set_defaults(func=_cmd_cron)

    p_heal = subparsers.add_parser(
        "heal",
        help="Heal missing/invalid frontmatter in vault notes",
    )
    p_heal.add_argument("path", help="Path to the vault directory")
    p_heal.add_argument(
        "--no-dry-run",
        action="store_true",
        default=False,
        help="Actually apply fixes (default: dry run)",
    )
    p_heal.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Heal at most N notes then stop (useful for large vaults)",
    )
    p_heal.set_defaults(func=_cmd_heal)

    p_md = subparsers.add_parser(
        "markdown-check",
        help="Check markdown quality issues across the vault",
    )
    p_md.add_argument("path", help="Path to the vault directory")
    p_md.set_defaults(func=_cmd_markdown_check)

    p_suggest = subparsers.add_parser(
        "suggest-related",
        help="Auto-suggest related notes via keyword/tag overlap",
    )
    p_suggest.add_argument("path", help="Path to the vault directory")
    p_suggest.add_argument(
        "--target",
        default=None,
        help="Specific note path to find relations for (optional)",
    )
    p_suggest.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Max suggestions (default: 5)",
    )
    p_suggest.add_argument(
        "--v2",
        action="store_true",
        default=False,
        help="Use Graph RAG v2 (weighted, explicit-link-aware) suggester",
    )
    p_suggest.set_defaults(func=_cmd_suggest_related)

    p_synth = subparsers.add_parser(
        "synthesize",
        help="Auto-ingest a session synthesis note (Phase 3 Auto-Ingest Loop)",
    )
    p_synth.add_argument("path", help="Path to the vault directory")
    p_synth.add_argument("--name", required=True, help="Note filename (e.g. session_2026.md)")
    p_synth.add_argument("--title", required=True, help="Note title")
    p_synth.add_argument("--description", required=True, help="Note description")
    p_synth.add_argument("--content", required=True, help="Note body content")
    p_synth.add_argument(
        "--note-type",
        default="Daily Log",
        help="OKF note type (default: Daily Log)",
    )
    p_synth.add_argument("--tags", nargs="*", default=[], help="Space-separated tags")
    p_synth.add_argument(
        "--related", nargs="*", default=[], help="Space-separated related note paths"
    )
    p_synth.add_argument("--owner", default=None, help="Note owner")
    p_synth.set_defaults(func=_cmd_synthesize)

    p_rename = subparsers.add_parser(
        "rename",
        help="Rename a vault note and update related paths in other notes",
    )
    p_rename.add_argument("path", help="Path to the vault directory")
    p_rename.add_argument("--old", required=True, help="Old relative path of the note")
    p_rename.add_argument("--new", required=True, help="New relative path of the note")
    p_rename.add_argument(
        "--no-dry-run",
        action="store_true",
        default=False,
        help="Actually apply changes (default: dry run)",
    )
    p_rename.set_defaults(func=_cmd_rename)

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        stream=sys.stderr,
    )

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))
