"""Negative regression coverage for the fail-closed remote-egress contract."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from power_framework.core.egress import EgressDeniedError, EgressOperation, require_remote_egress
from power_framework.core.query_expansion import QueryExpander
from power_framework.core.rot_scoring import LinkRotChecker


@pytest.mark.parametrize("operation", list(EgressOperation))
def test_remote_egress_denies_all_operations_by_default(operation: EgressOperation) -> None:
    with pytest.raises(EgressDeniedError, match="POWER_EGRESS_POLICY=deny"):
        require_remote_egress(operation, "internal")


def test_sensitive_egress_requires_the_explicit_sensitive_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-internal")
    with pytest.raises(EgressDeniedError):
        require_remote_egress(EgressOperation.RERANKING, "sensitive")
    monkeypatch.setenv("POWER_EGRESS_POLICY", "allow-sensitive")
    require_remote_egress(EgressOperation.RERANKING, "sensitive")


def test_query_expansion_does_not_open_network_when_policy_denies() -> None:
    expander = QueryExpander(use_llm=True, api_key="test-key")
    with patch("urllib.request.urlopen") as request:
        variants = expander.expand("internal deployment credential")
    request.assert_not_called()
    assert "internal deployment credential" in variants


def test_link_rot_does_not_open_network_when_policy_denies() -> None:
    with patch("urllib.request.urlopen") as request:
        assert LinkRotChecker()._head_status("https://example.com") == -1
    request.assert_not_called()
