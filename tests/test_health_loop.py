"""Health-loop deduplication, backoff, and cheap-path safety tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from power_framework.core.health_loop import HealthLoop

if TYPE_CHECKING:
    from pathlib import Path


def test_repeated_issue_is_deduplicated_with_exponential_backoff() -> None:
    start = datetime(2026, 8, 11, tzinfo=UTC)
    loop = HealthLoop(base_backoff=timedelta(hours=1), max_backoff=timedelta(days=1))

    first = loop.observe([("coverage_drift", "warning")], now=start)
    immediate = loop.observe([("coverage_drift", "warning")], now=start + timedelta(minutes=30))
    after_backoff = loop.observe(
        [("coverage_drift", "warning")], now=start + timedelta(hours=2, minutes=1)
    )

    assert [item.action for item in first.notifications] == ["notify"]
    assert immediate.notifications == ()
    assert immediate.suppressed == 1
    assert [item.action for item in after_backoff.notifications] == ["notify"]
    assert after_backoff.notifications[0].occurrence == 3


def test_recovery_emits_one_transition_and_resets_state() -> None:
    start = datetime(2026, 8, 11, tzinfo=UTC)
    loop = HealthLoop()
    loop.observe([("provider_missing", "error")], now=start)

    recovered = loop.observe([], now=start + timedelta(minutes=1))
    reappeared = loop.observe([("provider_missing", "error")], now=start + timedelta(minutes=2))

    assert recovered.notifications[0].action == "recovered"
    assert reappeared.notifications[0].occurrence == 1


def test_thirty_day_stream_has_no_duplicate_notifications_per_cycle() -> None:
    start = datetime(2026, 8, 11, tzinfo=UTC)
    loop = HealthLoop()
    for offset in range(0, 30 * 24, 6):
        cycle = loop.observe(
            [("lock_drift", "warning"), ("schema_drift", "error")],
            now=start + timedelta(hours=offset),
        )
        assert len({item.code for item in cycle.notifications}) == len(cycle.notifications)


def test_cheap_run_requests_no_provider_and_performs_no_write(tmp_path: Path, monkeypatch) -> None:
    called: dict[str, object] = {}

    def fake_doctor(path: Path, *, probe_embedding: bool) -> dict[str, object]:
        called["path"] = path
        called["probe_embedding"] = probe_embedding
        return {"issues": [{"code": "lock_drift", "severity": "warning"}]}

    monkeypatch.setattr("power_framework.core.health_loop.run_doctor", fake_doctor)
    result = HealthLoop().run_cheap(tmp_path)

    assert called == {"path": tmp_path, "probe_embedding": False}
    assert result.model_probe is False
    assert result.writes_performed is False
    assert result.active_codes == ("lock_drift",)
    assert not list(tmp_path.iterdir())
