"""
P.O.W.E.R. Vault Linter.

Checks for:
  - Broken links (wiki [[link]], GFM, embed)
  - Missing/invalid OKF frontmatter
  - Orphan notes (no inbound links)
  - Stale / expired notes (freshness governance)
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .parser import has_frontmatter, has_type_field, parse_frontmatter, read_file_content
from .utils import EXCLUDED_DIRS, clean_note_name, is_excluded_orphan

WIKI_LINK_PATTERN = re.compile(r"\[\[(.*?)\]\]")
GFM_LINK_PATTERN = re.compile(r"\[.*?\]\(((?![a-zA-Z][a-zA-Z0-9+.-]*://)[^)]*\.md)(?:#.*?)?\)")
EMBED_LINK_PATTERN = re.compile(r"!\[\[(.*?)\]\]")


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

    def format_report(self, vault_dir: Path) -> str:
        """Generate a human-readable lint report."""
        today = date.today()
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


def _extract_links(content: str) -> list[str]:
    """Extract all internal link targets from markdown content."""
    targets: list[str] = []

    for match in WIKI_LINK_PATTERN.findall(content):
        target = match.split("|")[0].split("#")[0].strip()
        if target:
            targets.append(clean_note_name(target))

    for match in EMBED_LINK_PATTERN.findall(content):
        target = match.split("|")[0].split("#")[0].strip()
        if target:
            targets.append(clean_note_name(target))

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

    for filepath in vault_dir.rglob("*.md"):
        rel = filepath.relative_to(vault_dir)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
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
        if fm and "expiry" in fm:
            try:
                expiry_val = fm["expiry"]
                if isinstance(expiry_val, date) and expiry_val < date.today():
                    result.stale_notes.append(
                        (rel_path, f"Expired on {expiry_val.isoformat()}")
                    )
            except (ValueError, TypeError):
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
        if count == 0 and not is_excluded_orphan(filename, rel_path):
            result.orphans.append(rel_path)

    return result


def run_lint_report(vault_dir: Path) -> str:
    """Run lint and return formatted report string."""
    result = run_lint_vault(vault_dir)
    return result.format_report(vault_dir)
