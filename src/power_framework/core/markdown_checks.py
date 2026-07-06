"""
P.O.W.E.R. Markdown Quality Checks.

Detects and optionally fixes common markdown quality issues:
  - Trailing whitespace
  - Inconsistent list markers (mixing - and *)
  - Header level jumps (e.g., h1 -> h3 without h2)
  - Code blocks without language hints
"""

from __future__ import annotations

import re

TRAILING_WS_PATTERN = re.compile(r"[ \t]+$", re.MULTILINE)
HEADER_PATTERN = re.compile(r"^(#{1,6})\s", re.MULTILINE)
CODE_BLOCK_PATTERN = re.compile(r"^```(\w*)$", re.MULTILINE)


def check_trailing_whitespace(content: str) -> list[dict]:
    """Detect lines with trailing whitespace."""
    issues: list[dict] = []
    for i, line in enumerate(content.split("\n"), 1):
        if TRAILING_WS_PATTERN.search(line) and line.strip():
            issues.append(
                {
                    "line": i,
                    "type": "trailing-whitespace",
                    "context": line.rstrip()[:60],
                }
            )
    return issues


def fix_trailing_whitespace(content: str) -> str:
    """Remove trailing whitespace from all lines."""
    return TRAILING_WS_PATTERN.sub("", content)


def check_list_markers(content: str) -> list[dict]:
    """Detect inconsistent list markers at the same indent level."""
    issues: list[dict] = []
    indent_markers: dict[int, set[str]] = {}
    in_code = False

    for line in content.split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue

        stripped = line.lstrip()
        if not stripped:
            continue
        indent = len(line) - len(stripped)
        if stripped.startswith("- "):
            indent_markers.setdefault(indent, set()).add("-")
        elif stripped.startswith("* "):
            indent_markers.setdefault(indent, set()).add("*")

    for indent, markers in indent_markers.items():
        if len(markers) > 1:
            issues.append(
                {
                    "line": 1,
                    "type": "inconsistent-list-markers",
                    "context": f"Indent level {indent} uses {', '.join(sorted(markers))}",
                }
            )

    return issues


def fix_list_markers(content: str, preferred: str = "-") -> str:
    """Standardize list markers to the preferred character, skipping code blocks."""
    lines = content.split("\n")
    fixed: list[str] = []
    in_code = False

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_code = not in_code
            fixed.append(line)
            continue
        if not in_code and (stripped.startswith("* ") or stripped.startswith("- ")):
            indent = line[: len(line) - len(stripped)]
            fixed.append(f"{indent}{preferred} {stripped[2:]}")
        else:
            fixed.append(line)

    return "\n".join(fixed)


def check_header_jumps(content: str) -> list[dict]:
    """Detect header jumps (e.g., h1 -> h3 without h2)."""
    issues: list[dict] = []
    seen_levels: set[int] = set()

    for i, line in enumerate(content.split("\n"), 1):
        match = HEADER_PATTERN.match(line)
        if match:
            level = len(match.group(1))
            if seen_levels:
                prev_max = max(seen_levels)
                if level > prev_max + 1 and prev_max > 0:
                    issues.append(
                        {
                            "line": i,
                            "type": "header-jump",
                            "context": f"h{prev_max} -> h{level} (skipped h{level - 1})",
                        }
                    )
            seen_levels.add(level)

    return issues


def check_code_block_language(content: str) -> list[dict]:
    """Detect fenced code blocks without a language hint."""
    issues: list[dict] = []
    in_code = False
    for i, line in enumerate(content.split("\n"), 1):
        match = CODE_BLOCK_PATTERN.match(line)
        if match:
            if not in_code:
                in_code = True
                if not match.group(1):
                    issues.append(
                        {
                            "line": i,
                            "type": "missing-code-language",
                            "context": "Code block without language hint",
                        }
                    )
            else:
                in_code = False
    return issues


def check_all(content: str) -> list[dict]:
    """Run all markdown quality checks. Returns combined list of issues."""
    issues: list[dict] = []
    issues.extend(check_trailing_whitespace(content))
    issues.extend(check_list_markers(content))
    issues.extend(check_header_jumps(content))
    issues.extend(check_code_block_language(content))
    return issues


def fix_all(content: str) -> tuple[str, list[str]]:
    """Fix all auto-fixable issues. Returns (fixed_content, list_of_changes)."""
    changes: list[str] = []

    tw = check_trailing_whitespace(content)
    if tw:
        content = fix_trailing_whitespace(content)
        changes.append(f"Fixed trailing whitespace on {len(tw)} line(s)")

    lm = check_list_markers(content)
    if lm:
        stars = content.count("\n* ") + (1 if content.startswith("* ") else 0)
        dashes = content.count("\n- ") + (1 if content.startswith("- ") else 0)
        preferred = "-" if dashes >= stars else "*"
        content = fix_list_markers(content, preferred=preferred)
        changes.append(f"Standardized list markers to '{preferred}'")

    return content, changes
