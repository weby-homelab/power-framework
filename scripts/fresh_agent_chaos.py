"""Deterministic, content-free fresh-agent safety scenarios."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from power_framework.core.application import ApplicationService, RequestContext
from power_framework.core.doctor import BOOTSTRAP_MAX_BYTES, run_doctor
from power_framework.core.egress import EgressDeniedError, EgressOperation, require_remote_egress
from power_framework.core.lifecycle import LifecycleAdapter

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class ChaosScenario:
    """One redacted scenario result."""

    name: str
    passed: bool
    safety_invariant: bool
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "safety_invariant": self.safety_invariant,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ChaosReport:
    """Aggregate report with no note content or prompts."""

    scenarios: tuple[ChaosScenario, ...]
    bootstrap_bytes: int
    schema_version: str = "power.fresh-agent-chaos.v1"

    @property
    def success_rate(self) -> float:
        return sum(item.passed for item in self.scenarios) / len(self.scenarios)

    @property
    def safety_invariants_passed(self) -> bool:
        return all(item.safety_invariant for item in self.scenarios)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scenario_count": len(self.scenarios),
            "passed": sum(item.passed for item in self.scenarios),
            "success_rate": self.success_rate,
            "safety_invariants_passed": self.safety_invariants_passed,
            "bootstrap_bytes": self.bootstrap_bytes,
            "traces": [item.as_dict() for item in self.scenarios],
        }


def _scenario(name: str, check: Callable[[], tuple[bool, bool, str]]) -> ChaosScenario:
    try:
        passed, safe, detail = check()
    except Exception as exc:  # pragma: no cover - report path is tested via injected failures
        return ChaosScenario(name, False, False, type(exc).__name__)
    return ChaosScenario(name, passed, safe, detail)


def run_fresh_agent_chaos(vault_dir: Path) -> ChaosReport:
    """Run eight scenarios from a copied vault and return redacted evidence."""
    source = Path(vault_dir).expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="power-chaos-") as temporary:
        work = Path(temporary) / "vault"
        shutil.copytree(source, work, symlinks=True)
        bootstrap = run_doctor(work)
        bootstrap_size = len(str(bootstrap["bootstrap"]).encode("utf-8"))
        service = ApplicationService(work)

        def discover() -> tuple[bool, bool, str]:
            result = service.discover()
            capabilities = bootstrap.get("capabilities", {})
            version = capabilities.get("version") if isinstance(capabilities, dict) else None
            discovered = result.data.get("capabilities", {})
            discovered_version = discovered.get("version") if isinstance(discovered, dict) else None
            return (
                discovered_version == version and bootstrap_size <= BOOTSTRAP_MAX_BYTES,
                True,
                "bounded_discovery",
            )

        def degraded() -> tuple[bool, bool, str]:
            result = service.fleet_status()
            return (
                result.status == "unavailable" and result.data["safe_fallback"] == "local_fts",
                True,
                "fts_fallback",
            )

        def evidence() -> tuple[bool, bool, str]:
            result = service.retrieve("Test", mode="fts")
            return (
                result.data["trust"] == "untrusted" and result.data["data_only"] is True,
                True,
                "untrusted_data",
            )

        def safe_edit() -> tuple[bool, bool, str]:
            target = work / "01_Projects" / "chaos-proposal.md"
            content = "---\ntype: Project\ntitle: Chaos\ndescription: Proposal\ntimestamp: 2026-08-11T00:00:00Z\n---\n"
            result = service.propose(
                "01_Projects/chaos-proposal.md",
                content,
                context=RequestContext(authority="propose"),
            )
            return (
                result.status == "ok" and not target.exists(),
                not target.exists(),
                "proposal_only",
            )

        def denied_egress() -> tuple[bool, bool, str]:
            prior = os.environ.get("POWER_EGRESS_POLICY")
            try:
                os.environ["POWER_EGRESS_POLICY"] = "deny"
                try:
                    require_remote_egress(EgressOperation.EMBEDDINGS, "internal")
                except EgressDeniedError:
                    return True, True, "egress_denied"
                return False, False, "egress_allowed"
            finally:
                if prior is None:
                    os.environ.pop("POWER_EGRESS_POLICY", None)
                else:
                    os.environ["POWER_EGRESS_POLICY"] = prior

        def contradiction() -> tuple[bool, bool, str]:
            result = service.retrieve("instruction authority", mode="fts")
            return (
                result.data["trust"] == "untrusted" and result.data["data_only"] is True,
                True,
                "authority_not_promoted",
            )

        def compaction() -> tuple[bool, bool, str]:
            result = LifecycleAdapter(service, client="gemini").handle("pre-compact")
            return (
                result.write_performed is False and result.data["checkpoint_proposal"] is None,
                True,
                "proposal_only",
            )

        def handoff() -> tuple[bool, bool, str]:
            service.task(
                action="create",
                task_id="chaos-handoff",
                values={
                    "objective": "Continue bounded workflow",
                    "owner": "chaos",
                    "state": "submitted",
                },
                context=RequestContext(actor="agent-a", authority="propose"),
            )
            result = LifecycleAdapter(service, client="claude").handle(
                "stop", task_id="chaos-handoff"
            )
            return (
                result.write_performed is False and result.data["task"] is not None,
                True,
                "portable_handoff",
            )

        scenarios = tuple(
            _scenario(name, check)
            for name, check in (
                ("discover", discover),
                ("degraded-recovery", degraded),
                ("evidence-answer", evidence),
                ("safe-edit", safe_edit),
                ("denied-egress", denied_egress),
                ("contradiction", contradiction),
                ("compaction", compaction),
                ("cross-client-handoff", handoff),
            )
        )
    return ChaosReport(scenarios=scenarios, bootstrap_bytes=bootstrap_size)


__all__ = ["ChaosReport", "ChaosScenario", "run_fresh_agent_chaos"]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the read-only fresh-agent chaos suite")
    parser.add_argument("vault", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(run_fresh_agent_chaos(arguments.vault).as_dict(), sort_keys=True))
