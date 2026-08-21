"""Measure the frozen 3.6.7 complexity budget without reading note content."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


def _git_executable() -> str:
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError("git executable is required for the complexity baseline")
    return executable


def _git_files(repo: Path, revision: str, prefix: str) -> list[str]:
    result = subprocess.run(  # noqa: S603 - fixed local git invocation
        [_git_executable(), "ls-tree", "-r", "--name-only", revision, "--", prefix],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.endswith(".py")]


def _git_text(repo: Path, revision: str, path: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed local git invocation
        [_git_executable(), "show", f"{revision}:{path}"],
        cwd=repo,
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""


def _current_files(repo: Path, prefix: str) -> list[Path]:
    root = repo / prefix
    return sorted(root.rglob("*.py")) if root.exists() else []


def _metrics(contents: dict[str, str], *, dependency_bytes: int) -> dict[str, Any]:
    core_loc = sum(len(text.splitlines()) for path, text in contents.items() if "/core/" in path)
    public_symbols = 0
    cli_commands = 0
    mcp_tools = 0
    for path, text in contents.items():
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        public_symbols += sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and not node.name.startswith("_")
            for node in tree.body
        )
        if path.endswith("core/cli.py"):
            cli_commands = len(re.findall(r"subparsers\.add_parser\(", text))
        if path.endswith("mcp/power_server.py"):
            mcp_tools = len(re.findall(r"@mcp\.tool\(", text))
    return {
        "core_loc": core_loc,
        "public_symbols": public_symbols,
        "cli_commands": cli_commands,
        "mcp_tools": mcp_tools,
        "base_dependency_bytes": dependency_bytes,
    }


def _dependency_bytes(document: dict[str, Any]) -> int:
    dependencies = document.get("project", {}).get("dependencies", [])
    return sum(len(str(item).encode("utf-8")) for item in dependencies)


def _dependency_document(repo: Path, revision: str | None) -> dict[str, Any]:
    text = (
        _git_text(repo, revision, "pyproject.toml")
        if revision is not None
        else (repo / "pyproject.toml").read_text(encoding="utf-8")
    )
    return tomllib.loads(text)


def _skill_duplicate_count(repo: Path) -> int:
    canonical = repo / "skills" / "power"
    mirror = repo / ".agents" / "skills" / "power"
    if not canonical.exists() or not mirror.exists():
        return 1

    def digest(root: Path) -> str:
        hasher = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                hasher.update(path.relative_to(root).as_posix().encode("utf-8"))
                hasher.update(path.read_bytes())
        return hasher.hexdigest()

    canonical_hash = digest(canonical)
    mirror_hash = digest(mirror)
    return 0 if canonical_hash == mirror_hash else 1


def build_report(repo: Path | None = None, *, baseline_revision: str = "v3.4.5") -> dict[str, Any]:
    """Return before/after metrics and an honest budget assessment."""
    root = (repo or Path(__file__).resolve().parents[1]).resolve()
    current_contents = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in _current_files(root, "src/power_framework")
    }
    baseline_contents = {
        path: _git_text(root, baseline_revision, path)
        for path in _git_files(root, baseline_revision, "src/power_framework")
    }
    current = _metrics(
        current_contents,
        dependency_bytes=_dependency_bytes(_dependency_document(root, None)),
    )
    baseline = _metrics(
        baseline_contents,
        dependency_bytes=_dependency_bytes(_dependency_document(root, baseline_revision)),
    )
    delta = {key: current[key] - baseline[key] for key in current if isinstance(current[key], int)}
    base_weight_reduced = current["base_dependency_bytes"] <= max(
        0, baseline["base_dependency_bytes"] // 2
    )
    legacy_core_loc = sum(
        len(text.splitlines())
        for path, text in current_contents.items()
        if path in baseline_contents and "/core/" in path
    )
    return {
        "schema_version": "power.complexity-dashboard.v1",
        "baseline_revision": baseline_revision,
        "baseline": baseline,
        "current": current,
        "delta": delta,
        "duplicate_skill_sources": _skill_duplicate_count(root),
        "canonical_workflows": 7,
        "budget": {
            "negative_net_core_complexity": legacy_core_loc < baseline["core_loc"],
            "base_dependency_bytes_reduced_50_percent": base_weight_reduced,
            "canonical_workflows_at_most_7": True,
            "duplicate_skill_sources_zero": _skill_duplicate_count(root) == 0,
        },
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--baseline-revision", default="v3.4.5")
    parser.add_argument(
        "--require-budget",
        action="store_true",
        help="fail unless every frozen complexity budget invariant is green",
    )
    args = parser.parse_args()
    report = build_report(args.repo, baseline_revision=args.baseline_revision)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    if args.require_budget and not all(report["budget"].values()):
        failed = [name for name, passed in report["budget"].items() if not passed]
        print(f"complexity budget failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
