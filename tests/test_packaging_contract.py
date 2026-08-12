"""Packaging and lean-install import contracts."""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _project_metadata() -> dict[str, object]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        document = tomllib.load(handle)
    return document["project"]


def test_base_dependencies_are_free_of_optional_runtime_stacks() -> None:
    project = _project_metadata()
    base = {
        re.split(r'["<>=!~; ]', str(item), maxsplit=1)[0].lower()
        for item in project["dependencies"]
    }
    assert base == {"pydantic", "pyyaml", "pathspec", "defusedxml"}


def test_optional_profiles_are_explicit() -> None:
    project = _project_metadata()
    extras = project["optional-dependencies"]

    assert {"semantic", "rerank", "gpu", "fleet", "bench", "remote", "experimental"} <= set(extras)
    assert any(str(item).startswith("onnxruntime>=") for item in extras["semantic"])
    assert any(str(item).startswith("onnxruntime-gpu>=") for item in extras["gpu"])
    assert any(str(item).startswith("fastembed>=") for item in extras["rerank"])
    assert any(str(item).startswith("fastmcp>=") for item in extras["remote"])


def test_fts_path_runs_when_optional_neural_imports_are_blocked(tmp_path: Path) -> None:
    script = """
import importlib.abc
import sys
from pathlib import Path

blocked = {"onnxruntime", "tokenizers", "huggingface_hub", "numpy", "fastembed", "qwen3_embed"}

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in blocked:
            raise ModuleNotFoundError(fullname)
        return None

sys.meta_path.insert(0, Blocker())
vault = Path(sys.argv[1])
note = vault / "01_Projects" / "lean.md"
note.parent.mkdir(parents=True)
note.write_text(
    "---\\ntype: Project\\ntitle: Lean\\ndescription: Base FTS\\n"
    "timestamp: 2026-01-01T00:00:00\\n---\\n\\nlean-token\\n",
    encoding="utf-8",
)
from power_framework.core.searcher import search_vault

results = search_vault(vault, "lean-token")
assert results and results[0].actual_mode == "fts"
assert results[0].retrieval_contract == "fts_fallback"
print("lean-fts-ok")
"""
    result = subprocess.run(  # noqa: S603 - executable and script are fixed by this test.
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True,
        check=False,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "lean-fts-ok" in result.stdout
