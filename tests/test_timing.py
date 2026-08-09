"""Tests for opt-in, content-free retrieval timing receipts."""

from power_framework.core.timing import collect_timings, timing_span


def test_timing_receipt_is_stable_and_content_free() -> None:
    with collect_timings() as receipt:
        with timing_span("sqlite_read"):
            pass
        with timing_span("sqlite_read"):
            pass

    payload = receipt.as_dict()
    assert payload["schema_version"] == "power.retrieval-timings.v1"
    assert payload["inclusive"] is True
    assert payload["span_counts"] == {"sqlite_read": 2}
    assert set(payload) == {"schema_version", "inclusive", "components_ms", "span_counts"}


def test_timing_span_is_noop_without_a_collector() -> None:
    with timing_span("not_recorded"):
        pass
