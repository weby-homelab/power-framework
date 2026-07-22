"""
P.O.W.E.R. Vault Linter.

Checks for:
  - Broken links (wiki [[link]], GFM, embed)
  - Missing/invalid OKF frontmatter
  - Orphan notes (no inbound links)
  - Stale / expired notes (freshness governance)
  - ROT (Redundant, Outdated, Trivial) analysis
  - Auto-archiving of stale notes
  - Content deduplication (TF-Vector cosine similarity)
  - Link rot (external HTTP health)
  - Freshness scoring (type-based decay)
  - Usage tracking (SQLite access counter)
"""

from __future__ import annotations

import logging
import re
import shutil
from datetime import date as date_type
from datetime import datetime, timezone
from pathlib import Path

from .ignore import should_skip
from .parser import (
    has_frontmatter,
    has_type_field,
    parse_frontmatter,
    read_file_content,
)
from .utils import clean_note_name, is_excluded_orphan

logger = logging.getLogger(__name__)

WIKI_LINK_PATTERN = re.compile(r"\[\[(.*?)\]\]")
GFM_LINK_PATTERN = re.compile(r"\[.*?\]\(((?![a-zA-Z][a-zA-Z0-9+.-]*://)[^)]*\.md)(?:#.*?)?\)")
EMBED_LINK_PATTERN = re.compile(r"!\[\[(.*?)\]\]")

TRIVIAL_BODY_MIN_CHARS = 50
TITLE_SIMILARITY_THRESHOLD = 0.6


class LintResult:
    """Container for lint check results."""

    def __init__(self) -> None:
        self.total_notes: int = 0
        self.untyped_files: list[tuple[str, str]] = []
        self.broken_links: list[tuple[str, str]] = []
        self.orphans: list[str] = []
        self.stale_notes: list[tuple[str, str]] = []

    @property
    def has_issues(self) -> bool:
        return bool(self.untyped_files or self.broken_links or self.orphans or self.stale_notes)

    @property
    def has_blocking_issues(self) -> bool:
        """Return whether lint found invalid metadata, broken links, or expired notes."""
        return bool(self.untyped_files or self.broken_links or self.stale_notes)

    def format_report(self, vault_dir: Path) -> str:
        """Generate a human-readable lint report."""
        today = datetime.now(timezone.utc).date()
        lines = [
            "=== P.O.W.E.R. Health Lint Report ===",
            f"Vault scanned: {vault_dir}",
            f"Date: {today.isoformat()}",
            f"Total markdown notes: {self.total_notes}",
            "",
        ]

        if self.untyped_files:
            lines.append(f"WARNING: Missing/Invalid OKF Metadata ({len(self.untyped_files)}):")
            for rp, reason in sorted(self.untyped_files):
                lines.append(f"  - {rp}: {reason}")
            lines.append("")

        if self.broken_links:
            lines.append(f"ERROR: Broken links found ({len(self.broken_links)}):")
            for rp, target in sorted(self.broken_links):
                lines.append(f"  - In {rp}: link to [[{target}]] cannot be resolved")
            lines.append("")

        if self.orphans:
            lines.append(f"WARNING: Orphan notes (no inbound links) ({len(self.orphans)}):")
            lines.extend(f"  - {rp}" for rp in sorted(self.orphans))
            lines.append("")

        if self.stale_notes:
            lines.append(f"WARNING: Stale / expired notes ({len(self.stale_notes)}):")
            for rp, reason in sorted(self.stale_notes):
                lines.append(f"  - {rp}: {reason}")
            lines.append("")

        if not self.has_issues:
            lines.append("OK: Vault is completely healthy! Zero errors found.")

        return "\n".join(lines)


class ROTResult:
    """Container for ROT (Redundant, Outdated, Trivial) audit results, plus extended A2 scoring."""

    def __init__(self) -> None:
        self.redundant: list[tuple[str, str, float]] = []
        self.outdated: list[tuple[str, str]] = []
        self.trivial: list[tuple[str, int]] = []
        self.content_dedup: list[tuple[str, str, float]] = []
        self.link_rot: dict[str, list[tuple[str, int]]] = {}
        self.freshness_scores: dict[str, float] = {}
        self.usage_counts: dict[str, int] = {}
        self.semantic_contradictions: list[tuple[str, str, str]] = []

    @property
    def has_issues(self) -> bool:
        return bool(
            self.redundant
            or self.outdated
            or self.trivial
            or self.content_dedup
            or self.link_rot
            or self.semantic_contradictions
        )

    @property
    def total_issues(self) -> int:
        return (
            len(self.redundant)
            + len(self.outdated)
            + len(self.trivial)
            + len(self.content_dedup)
            + len(self.link_rot)
            + len(self.semantic_contradictions)
        )

    def format_report(self, vault_dir: Path) -> str:
        """Generate a human-readable ROT audit report, including extended A2 metrics."""
        today = datetime.now(timezone.utc).date()
        lines = [
            "=== P.O.W.E.R. ROT Audit Report ===",
            f"Vault scanned: {vault_dir}",
            f"Date: {today.isoformat()}",
            "",
        ]

        if self.redundant:
            lines.append(f"REDUNDANT: Similar / duplicate titles ({len(self.redundant)} pairs):")
            for a, b, score in sorted(self.redundant):
                pct = int(score * 100)
                lines.append(f"  - [{pct}% similar] {a} <-> {b}")
            lines.append("")

        if self.content_dedup:
            lines.append(f"CONTENT DEDUP: Similar body content ({len(self.content_dedup)} pairs):")
            for a, b, score in sorted(self.content_dedup):
                pct = int(score * 100)
                lines.append(f"  - [{pct}% similar content] {a} <-> {b}")
            lines.append("")

        if self.outdated:
            lines.append(f"OUTDATED: Expired / stale notes ({len(self.outdated)}):")
            for rp, reason in sorted(self.outdated):
                lines.append(f"  - {rp}: {reason}")
            lines.append("")

        if self.trivial:
            lines.append(f"TRIVIAL: Notes with very short body content ({len(self.trivial)}):")
            for rp, length in sorted(self.trivial):
                lines.append(f"  - {rp}: only {length} chars of body content")
            lines.append("")

        if self.link_rot:
            total_broken = sum(len(urls) for urls in self.link_rot.values())
            lines.append(
                f"LINK ROT: Broken external links ({total_broken}) in {len(self.link_rot)} notes:"
            )
            for rp, urls in sorted(self.link_rot.items()):
                for url, status in urls:
                    status_label = "ERR" if status == -1 else str(status)
                    lines.append(f"  - {rp}: {url} ({status_label})")
            lines.append("")

        if self.freshness_scores:
            stale_notes = [(p, s) for p, s in self.freshness_scores.items() if s < 0.3]
            if stale_notes:
                lines.append(f"FRESHNESS: Stale notes (score < 0.3) ({len(stale_notes)}):")
                for rp, score in sorted(stale_notes, key=lambda x: x[1]):
                    lines.append(f"  - {rp}: freshness {score:.2f}")
                lines.append("")

        if self.semantic_contradictions:
            lines.append(f"SEMANTIC CONTRADICTIONS: ({len(self.semantic_contradictions)} pairs):")
            for a, b, reason in sorted(self.semantic_contradictions):
                lines.append(f"  - {a} <-> {b}: {reason}")
            lines.append("")

        if self.usage_counts:
            unused = [p for p, c in self.usage_counts.items() if c == 0]
            if unused:
                lines.append(f"USAGE: Never-accessed notes ({len(unused)}):")
                lines.extend(f"  - {rp}" for rp in sorted(unused)[:20])
                if len(unused) > 20:
                    lines.append(f"  ... and {len(unused) - 20} more")
                lines.append("")

        if not self.has_issues:
            lines.append("OK: No ROT issues found. Vault is clean!")

        return "\n".join(lines)


def _tokenize_for_similarity(text: str) -> set[str]:
    """Split text into lowercase word tokens for similarity comparison."""
    return set(re.findall(r"[a-z0-9а-яєіїґ']+", text.lower()))  # noqa: RUF001


def _title_similarity(title_a: str, title_b: str) -> float:
    """Compute Jaccard similarity between two title token sets."""
    tokens_a = _tokenize_for_similarity(title_a)
    tokens_b = _tokenize_for_similarity(title_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _get_body_content(raw_content: str) -> str:
    """Extract body content (after frontmatter) from raw markdown."""
    match = re.match(r"^---.*?---\n(.*)", raw_content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw_content.strip()


def _extract_links(content: str) -> list[str]:
    """Extract all internal link targets from markdown content."""
    targets: list[str] = []

    for match in WIKI_LINK_PATTERN.findall(content):
        target = match.split("|")[0].split("#")[0].strip()
        if target:
            targets.append(clean_note_name(Path(target).name))

    for match in EMBED_LINK_PATTERN.findall(content):
        target = match.split("|")[0].split("#")[0].strip()
        if target:
            targets.append(clean_note_name(Path(target).name))

    for match in GFM_LINK_PATTERN.findall(content):
        target = Path(match).name
        if target:
            targets.append(clean_note_name(target))

    return targets


def run_lint_vault(vault_dir: Path) -> LintResult:
    """
    Run full health lint on the vault.

    Checks for:
    1. Missing/invalid OKF frontmatter
    2. Broken internal links
    3. Orphan notes (no inbound links)
    """
    result = LintResult()

    all_files: dict[str, Path] = {}
    rel_paths: dict[str, str] = {}
    links: dict[str, list[str]] = {}
    orphan_exempt_paths: set[str] = set()

    for filepath in vault_dir.rglob("*.md"):
        rel = filepath.relative_to(vault_dir)
        if should_skip(vault_dir, str(rel)):
            continue

        clean = clean_note_name(filepath.name)

        all_files[clean] = filepath
        rel_paths[clean] = str(filepath.relative_to(vault_dir))

    result.total_notes = len(all_files)

    for clean_name, abs_path in all_files.items():
        rel_path = rel_paths[clean_name]

        try:
            content = read_file_content(abs_path)
        except Exception:  # noqa: S112
            continue

        if not has_frontmatter(content):
            result.untyped_files.append((rel_path, "No YAML frontmatter block"))
            links[rel_path] = _extract_links(content)
            continue
        if not has_type_field(content):
            result.untyped_files.append((rel_path, "Missing required 'type' field"))
            links[rel_path] = _extract_links(content)
            continue

        # Freshness check — detect stale / expired notes
        fm = parse_frontmatter(content)
        if fm and str(fm.get("status", "")).strip().lower() == "archived":
            orphan_exempt_paths.add(rel_path)
        if fm and "expiry" in fm:
            try:
                expiry_val = fm["expiry"]
                if (
                    isinstance(expiry_val, date_type)
                    and expiry_val < datetime.now(timezone.utc).date()
                ):
                    result.stale_notes.append((rel_path, f"Expired on {expiry_val.isoformat()}"))
            except (ValueError, TypeError):
                # Ignore invalid date formats; handled by schema validation.
                pass

        file_links = _extract_links(content)
        links[rel_path] = file_links

    for rel_path, targets in links.items():
        for target in targets:
            if target not in all_files:
                direct_file = vault_dir / f"{target}.md"
                if not direct_file.exists():
                    result.broken_links.append((rel_path, target))

    inbound_counts: dict[str, int] = dict.fromkeys(links, 0)
    for targets in links.values():
        for target in targets:
            if target in all_files:
                target_rel = rel_paths[target]
                inbound_counts[target_rel] += 1

    for rel_path, count in inbound_counts.items():
        filename = rel_path.rsplit("/", 1)[-1] if "/" in rel_path else rel_path
        if (
            count == 0
            and rel_path not in orphan_exempt_paths
            and not is_excluded_orphan(filename, rel_path)
        ):
            result.orphans.append(rel_path)

    return result


def run_lint_report(vault_dir: Path) -> str:
    """Run lint and return formatted report string."""
    result = run_lint_vault(vault_dir)
    return result.format_report(vault_dir)


def run_rot_audit(vault_dir: Path, extended: bool = False) -> ROTResult:
    """
    Run ROT (Redundant, Outdated, Trivial) audit on the vault.

    Checks for:
    1. Redundant — notes with similar/duplicate titles (Jaccard > threshold)
    2. Outdated — notes with expired 'expiry' field
    3. Trivial — notes with very short body content (< TRIVIAL_BODY_MIN_CHARS)

    When extended=True, also runs A2 scoring:
    - Content dedup via TF-Vector
    - Link rot checks (HTTP HEAD)
    - Freshness scoring (type-based decay)
    - Usage tracking
    """
    result = ROTResult()

    title_map: dict[str, tuple[str, str]] = {}
    stale_list: list[tuple[str, str]] = []

    for filepath in vault_dir.rglob("*.md"):
        rel = filepath.relative_to(vault_dir)
        if should_skip(vault_dir, str(rel)):
            continue
        if filepath.name in ("index.md", "log.md", "_index.md"):
            continue

        try:
            content = read_file_content(filepath)
        except Exception:  # noqa: S112
            continue

        fm = parse_frontmatter(content)
        if fm is None:
            continue

        title = str(fm.get("title", ""))
        rel_path = str(rel)

        # Track titles for redundancy check
        if title:
            title_map[rel_path] = (title, content)

        # Track outdated
        if "expiry" in fm:
            try:
                expiry_val = fm["expiry"]
                if (
                    isinstance(expiry_val, date_type)
                    and expiry_val < datetime.now(timezone.utc).date()
                ):
                    stale_list.append((rel_path, f"Expired on {expiry_val.isoformat()}"))
            except (ValueError, TypeError):
                # Ignore invalid date formats; handled by schema validation.
                pass

        # Track trivial (body content < threshold)
        body = _get_body_content(content)
        body_len = len(body)
        if 0 < body_len < TRIVIAL_BODY_MIN_CHARS:
            result.trivial.append((rel_path, body_len))

    result.outdated = stale_list

    # Redundancy check — pairwise title similarity
    sorted_titles = sorted(title_map.items())
    checked_pairs: set[tuple[str, str]] = set()
    for i in range(len(sorted_titles)):
        for j in range(i + 1, len(sorted_titles)):
            path_a, (title_a, _) = sorted_titles[i]
            path_b, (title_b, _) = sorted_titles[j]
            pair_key = (path_a, path_b) if path_a < path_b else (path_b, path_a)
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)
            sim = _title_similarity(title_a, title_b)
            if sim >= TITLE_SIMILARITY_THRESHOLD:
                result.redundant.append((path_a, path_b, sim))

    # Extended A2 scoring
    if extended:
        from .rot_scoring import (
            ContentDedupDetector,
            ContradictionDetector,
            FreshnessScorer,
            LinkRotChecker,
            UsageTracker,
        )

        try:
            dedup = ContentDedupDetector()
            result.content_dedup = dedup.detect(vault_dir)
        except Exception as exc:
            logger.warning("Content dedup failed: %s", exc)

        try:
            contra = ContradictionDetector()
            result.semantic_contradictions = contra.detect(vault_dir)
        except Exception as exc:
            logger.warning("Contradiction detection failed: %s", exc)

        try:
            link_checker = LinkRotChecker()
            result.link_rot = link_checker.check_all(vault_dir)
        except Exception as exc:
            logger.warning("Link rot check failed: %s", exc)

        try:
            scorer = FreshnessScorer()
            result.freshness_scores = scorer.score_all(vault_dir)
        except Exception as exc:
            logger.warning("Freshness scoring failed: %s", exc)

        try:
            tracker = UsageTracker(vault_dir)
            result.usage_counts = tracker.get_all_counts()
        except Exception as exc:
            logger.warning("Usage tracking failed: %s", exc)

    return result


def run_rot_report(vault_dir: Path, extended: bool = False) -> str:
    """Run ROT audit and return formatted report string."""
    result = run_rot_audit(vault_dir, extended=extended)
    return result.format_report(vault_dir)


def archive_stale_notes(vault_dir: Path, dry_run: bool = True) -> str:
    """
    Move stale / expired notes to 04_Archive.

    Uses the same stale detection as the linter:
      - Notes with 'expiry' date in the past
      - Notes already in 04_Archive are skipped

    Args:
        vault_dir: Path to the vault root
        dry_run: If True, only simulate (no actual moves)

    Returns: Summary string of actions taken
    """
    archive_dir = vault_dir / "04_Archive"
    today = datetime.now(timezone.utc).date()
    moved: list[str] = []
    errors: list[str] = []

    for filepath in vault_dir.rglob("*.md"):
        rel = filepath.relative_to(vault_dir)
        if should_skip(vault_dir, str(rel)):
            continue
        if filepath.name in ("index.md", "log.md", "_index.md"):
            continue
        # Skip notes already in archive
        rel_str = str(rel)
        if rel_str.startswith("04_Archive/"):
            continue

        try:
            content = read_file_content(filepath)
        except Exception:  # noqa: S112
            continue

        fm = parse_frontmatter(content)
        if fm is None:
            continue

        is_archived_status = str(fm.get("status", "")).strip().lower() == "archived"

        is_expired = False
        if "expiry" in fm:
            try:
                expiry_val = fm["expiry"]
                if isinstance(expiry_val, date_type) and expiry_val < today:
                    is_expired = True
            except (ValueError, TypeError):
                # Ignore invalid date formats; handled by schema validation.
                pass

        if not is_archived_status and not is_expired:
            continue

        # Determine target path in archive
        rel_obj = Path(rel_str)
        archive_target = archive_dir / rel_obj.name

        if archive_target.exists():
            errors.append(f"  {rel_str} -> SKIP (already exists in archive)")
            continue

        if dry_run:
            moved.append(f"  {rel_str} -> {archive_target.relative_to(vault_dir)}")
        else:
            archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(filepath), str(archive_target))
            moved.append(f"  {rel_str} -> {archive_target.relative_to(vault_dir)}")

    lines = [
        "=== Archive Stale Notes ===",
        f"Mode: {'DRY RUN' if dry_run else 'LIVE'}",
        f"Date: {today.isoformat()}",
        "",
    ]

    if moved:
        lines.append(f"Notes to archive ({len(moved)}):")
        lines.extend(moved)
        lines.append("")
    else:
        lines.append("No stale notes found.")
        lines.append("")

    if errors:
        lines.append(f"Errors ({len(errors)}):")
        lines.extend(errors)
        lines.append("")

    if not dry_run:
        lines.append(f"Archived {len(moved)} note(s) to 04_Archive/.")

    return "\n".join(lines)


def run_status_report(vault_dir: Path) -> str:
    """Generate a high-density, visual status report of the vault's structure, health, and knowledge graph RAG connectivity."""

    from .ignore import should_skip
    from .models import NoteFile
    from .parser import validate_metadata
    from .relations import KnowledgeGraph

    today = datetime.now(timezone.utc).date()

    total_files = 0
    non_compliant = 0
    non_compliant_list = []

    notes_by_folder = {
        "01_Projects": 0,
        "02_Areas": 0,
        "03_Resources": 0,
        "04_Archive": 0,
        "06_Daily_Logs": 0,
        "Other": 0,
    }

    note_files = []
    total_external_links = 0
    external_link_pattern = re.compile(r"\[.*?\]\(((?:https?|ftp)://[^\s)]+)\)")

    for filepath in vault_dir.rglob("*.md"):
        if filepath.name in ("index.md", "log.md", "_index.md"):
            continue

        rel_path = filepath.relative_to(vault_dir)
        rel_path_str = str(rel_path)

        if should_skip(vault_dir, rel_path_str):
            continue

        total_files += 1

        # Categorize by top folder
        top_folder = rel_path.parts[0] if rel_path.parts else ""
        if top_folder in notes_by_folder:
            notes_by_folder[top_folder] += 1
        else:
            notes_by_folder["Other"] += 1

        try:
            content = read_file_content(filepath)
            fm = validate_metadata(content)

            # Count external links
            urls = external_link_pattern.findall(content)
            total_external_links += len(urls)

            if fm is None:
                non_compliant += 1
                non_compliant_list.append(rel_path_str)
                continue

            note_obj = NoteFile(str(filepath), rel_path_str, fm, content)
            note_files.append(note_obj)

        except Exception:
            non_compliant += 1
            non_compliant_list.append(rel_path_str)

    # Build Knowledge Graph
    kg = KnowledgeGraph.from_notes(note_files)
    nodes_count = len(kg._nodes)
    edges_count = len(kg._edges)

    # Run linter
    lint_result = run_lint_vault(vault_dir)

    # ANSI color codes
    cyan = "\033[36m"
    green = "\033[32m"
    yellow = "\033[33m"
    red = "\033[31m"
    bold = "\033[1m"
    reset = "\033[0m"

    compliant = total_files - non_compliant
    compliance_rate = (compliant / total_files * 100) if total_files > 0 else 0

    lines = [
        f"{bold}=== P.O.W.E.R. Obsidian Vault Status ==={reset}",
        f"Vault Root: {vault_dir}",
        f"Date:       {today.isoformat()}",
        "",
        f"{cyan}{bold}📂 STRUCTURE & CAPACITY:{reset}",
        f"  • Total Markdown Notes:  {bold}{total_files}{reset}",
        f"  • OKF Compliant Notes:   {green if compliance_rate >= 90 else yellow}{bold}{compliant} ({compliance_rate:.1f}%){reset}",
        f"  • Non-Compliant Notes:   {red if non_compliant > 0 else green}{bold}{non_compliant}{reset}",
    ]

    if non_compliant > 0:
        lines.append(f"    {yellow}⚠️ Fix using 'power heal' to auto-add frontmatter.{reset}")

    lines.extend(
        [
            "",
            f"{cyan}{bold}📊 PARA CATEGORIES:{reset}",
            f"  • 01_Projects:           {bold}{notes_by_folder['01_Projects']}{reset} notes",
            f"  • 02_Areas:              {bold}{notes_by_folder['02_Areas']}{reset} notes",
            f"  • 03_Resources:          {bold}{notes_by_folder['03_Resources']}{reset} notes",
            f"  • 04_Archive:            {bold}{notes_by_folder['04_Archive']}{reset} notes",
            f"  • 06_Daily_Logs:         {bold}{notes_by_folder['06_Daily_Logs']}{reset} notes",
        ]
    )
    if notes_by_folder["Other"] > 0:
        lines.append(f"  • Other / Root:          {bold}{notes_by_folder['Other']}{reset} notes")

    lines.extend(
        [
            "",
            f"{cyan}{bold}🕸️ KNOWLEDGE GRAPH (Graph RAG):{reset}",
            f"  • Total Graph Nodes:     {bold}{nodes_count}{reset} note files",
            f"  • Typed Relations:       {bold}{edges_count}{reset} connections",
        ]
    )

    # Health lint issues
    broken_wiki = len(lint_result.broken_links)
    orphans = len(lint_result.orphans)
    stale = len(lint_result.stale_notes)

    lines.extend(
        [
            "",
            f"{cyan}{bold}🏥 HEALTH & STALENESS:{reset}",
            f"  • Broken Wiki Links:     {red if broken_wiki > 0 else green}{bold}{broken_wiki}{reset}",
            f"  • Orphan Notes:          {yellow if orphans > 0 else green}{bold}{orphans}{reset}",
            f"  • Expired / Stale Notes: {yellow if stale > 0 else green}{bold}{stale}{reset}",
            f"  • External Web Links:    {bold}{total_external_links}{reset} total references",
        ]
    )

    return "\n".join(lines)
