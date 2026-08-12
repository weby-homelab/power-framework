"""Cheap, deduplicated health observations for session-start checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from .doctor import run_doctor

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

HealthSeverity = Literal["info", "warning", "error"]
HealthAction = Literal["notify", "recovered"]


@dataclass(frozen=True)
class HealthNotification:
    """One content-free state transition emitted by the health loop."""

    code: str
    severity: HealthSeverity
    action: HealthAction
    at: datetime
    occurrence: int

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "action": self.action,
            "at": self.at.astimezone(UTC).isoformat(),
            "occurrence": self.occurrence,
        }


@dataclass(frozen=True)
class HealthCycle:
    """Bounded result of one cheap health observation."""

    status: Literal["ready", "degraded"]
    active_codes: tuple[str, ...]
    notifications: tuple[HealthNotification, ...]
    suppressed: int = 0
    model_probe: bool = False
    writes_performed: bool = False
    schema_version: str = "power.health-cycle.v1"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "active_codes": list(self.active_codes),
            "notifications": [notification.as_dict() for notification in self.notifications],
            "suppressed": self.suppressed,
            "model_probe": self.model_probe,
            "writes_performed": self.writes_performed,
        }


@dataclass
class _IssueState:
    severity: HealthSeverity
    occurrence: int = 0
    notifications_sent: int = 0
    last_notified: datetime | None = None


class HealthLoop:
    """Keep notification state in memory and never mutate vault content."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        base_backoff: timedelta = timedelta(hours=1),
        max_backoff: timedelta = timedelta(days=7),
    ) -> None:
        if base_backoff <= timedelta(0) or max_backoff < base_backoff:
            raise ValueError("backoff limits must be positive and ordered")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff
        self._issues: dict[str, _IssueState] = {}

    def observe(
        self,
        issues: Iterable[tuple[str, HealthSeverity]],
        *,
        now: datetime | None = None,
    ) -> HealthCycle:
        """Observe issue codes and emit only new/backoff-eligible transitions."""
        timestamp = (now or self._clock()).astimezone(UTC)
        current: dict[str, HealthSeverity] = {}
        for code, severity in issues:
            normalized = code.strip()
            if normalized and severity in {"info", "warning", "error"}:
                current[normalized] = severity

        notifications: list[HealthNotification] = []
        suppressed = 0
        for code in sorted(current):
            severity = current[code]
            state = self._issues.setdefault(code, _IssueState(severity=severity))
            state.severity = severity
            state.occurrence += 1
            backoff = min(
                self._base_backoff * (2 ** min(31, state.notifications_sent)),
                self._max_backoff,
            )
            if state.last_notified is not None and timestamp < state.last_notified + backoff:
                suppressed += 1
                continue
            state.last_notified = timestamp
            state.notifications_sent += 1
            notifications.append(
                HealthNotification(code, severity, "notify", timestamp, state.occurrence)
            )

        for code in sorted(set(self._issues) - set(current)):
            state = self._issues.pop(code)
            notifications.append(
                HealthNotification(code, state.severity, "recovered", timestamp, state.occurrence)
            )

        return HealthCycle(
            status="degraded" if current else "ready",
            active_codes=tuple(sorted(current)),
            notifications=tuple(notifications),
            suppressed=suppressed,
        )

    def run_cheap(self, vault_dir: Path) -> HealthCycle:
        """Run default doctor only; no model, network, or content mutation."""
        report = run_doctor(Path(vault_dir), probe_embedding=False)
        issues: list[tuple[str, HealthSeverity]] = []
        for issue in report.get("issues", []):
            if not isinstance(issue, dict) or issue.get("severity") not in {"warning", "error"}:
                continue
            issues.append(
                (
                    str(issue.get("code", "unknown")),
                    cast("HealthSeverity", str(issue["severity"])),
                )
            )
        return self.observe(issues)


__all__ = ["HealthCycle", "HealthLoop", "HealthNotification"]
