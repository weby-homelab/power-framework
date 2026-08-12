"""Portable, read-only lifecycle adapters for agent session boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .application import ApplicationEnvelope, ApplicationService, RequestContext

LifecycleEvent = Literal["session-start", "post-write", "pre-compact", "stop"]
LifecycleMaturity = Literal["native-adapter", "portable-mcp-skill"]
_EVENTS: tuple[LifecycleEvent, ...] = (
    "session-start",
    "post-write",
    "pre-compact",
    "stop",
)
_CLIENTS = frozenset({"codex", "opencode", "gemini", "claude", "portable"})


@dataclass(frozen=True)
class LifecycleCapability:
    """Explicit support level for one client/event pair."""

    event: LifecycleEvent
    client: str
    supported: bool
    maturity: LifecycleMaturity
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "event": self.event,
            "client": self.client,
            "supported": self.supported,
            "maturity": self.maturity,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LifecycleEnvelope:
    """Content-free result for an adapter event."""

    event: LifecycleEvent
    client: str
    capability: LifecycleCapability
    data: dict[str, object]
    receipt: dict[str, object]
    write_performed: bool = False
    schema_version: str = "power.lifecycle.v1"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "event": self.event,
            "client": self.client,
            "capability": self.capability.as_dict(),
            "data": self.data,
            "receipt": self.receipt,
            "write_performed": self.write_performed,
        }


def capability_matrix() -> list[LifecycleCapability]:
    """Return the four-event contract for every supported client profile."""
    return [
        LifecycleCapability(
            event=event,
            client=client,
            supported=True,
            maturity="portable-mcp-skill",
            reason="shared read-only lifecycle contract; native hooks are optional",
        )
        for client in sorted(_CLIENTS)
        for event in _EVENTS
    ]


class LifecycleAdapter:
    """Call application use cases only; never perform a silent semantic write."""

    def __init__(self, service: ApplicationService, *, client: str = "portable") -> None:
        if client not in _CLIENTS:
            raise ValueError(f"unsupported lifecycle client: {client}")
        self.service = service
        self.client = client

    def capability(self, event: LifecycleEvent) -> LifecycleCapability:
        if event not in _EVENTS:
            raise ValueError(f"unsupported lifecycle event: {event}")
        return LifecycleCapability(
            event=event,
            client=self.client,
            supported=True,
            maturity="portable-mcp-skill",
            reason="shared read-only lifecycle contract; native hooks are optional",
        )

    def handle(
        self,
        event: LifecycleEvent,
        *,
        task_id: str | None = None,
        expected_after_sha256: str | None = None,
        context: RequestContext | None = None,
    ) -> LifecycleEnvelope:
        """Handle one event with a read-only application call.

        ``pre-compact`` returns a checkpoint proposal only. Applying that
        proposal remains a separate, explicitly approved handoff operation.
        """
        capability = self.capability(event)
        request = context or RequestContext(actor=f"lifecycle:{self.client}")
        application_result: ApplicationEnvelope
        data: dict[str, object]
        task_available = bool(task_id)
        if event == "session-start":
            application_result = self.service.discover(context=request)
            data = {"discovery": application_result.data}
        elif event == "post-write":
            application_result = self.service.receipt(limit=16, context=request)
            receipts_raw = application_result.data.get("receipts", [])
            receipts = receipts_raw if isinstance(receipts_raw, list) else []
            verified = expected_after_sha256 is None or any(
                isinstance(receipt, dict) and receipt.get("after_sha256") == expected_after_sha256
                for receipt in receipts
            )
            data = {
                "verified": verified,
                "receipt_count": len(receipts) if isinstance(receipts, list) else 0,
                "expected_after_sha256": expected_after_sha256,
            }
        elif event == "pre-compact":
            if task_id:
                try:
                    application_result = self.service.task(
                        action="read", task_id=task_id, context=request
                    )
                except FileNotFoundError:
                    task_available = False
                    application_result = self.service.discover(context=request)
            else:
                task_available = False
                application_result = self.service.discover(context=request)
            data = {
                "task": application_result.data if task_available else None,
                "checkpoint_proposal": (
                    {
                        "task_id": task_id,
                        "action": "checkpoint",
                        "approval_required": True,
                        "write_performed": False,
                    }
                    if task_available
                    else None
                ),
            }
        else:
            if task_id:
                try:
                    application_result = self.service.task(
                        action="read", task_id=task_id, context=request
                    )
                except FileNotFoundError:
                    task_available = False
                    application_result = self.service.discover(context=request)
            else:
                task_available = False
                application_result = self.service.discover(context=request)
            data = {
                "task": application_result.data if task_available else None,
                "drift_check": "read-only-discovery",
            }
        return LifecycleEnvelope(
            event=event,
            client=self.client,
            capability=capability,
            data=data,
            receipt=application_result.receipt.as_dict(),
        )


__all__ = [
    "LifecycleAdapter",
    "LifecycleCapability",
    "LifecycleEnvelope",
    "capability_matrix",
]
