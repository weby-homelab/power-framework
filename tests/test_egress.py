"""Negative regression coverage for the fail-closed remote-egress contract."""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from power_framework.core import egress
from power_framework.core.egress import (
    EgressDeniedError,
    EgressOperation,
    SafeHttpResponse,
    require_remote_egress,
    safe_http_request,
    validate_llm_endpoint,
    validate_local_ollama_endpoint,
)
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


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/metadata",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/metadata",
        "http://[fe80::1]/metadata",
        "http://[fc00::1]/metadata",
        "http://[::ffff:127.0.0.1]/metadata",
        "file:///etc/passwd",
        "http://user:password@example.com/",
    ],
)
def test_endpoint_policy_rejects_unsafe_literal_urls(url: str) -> None:
    with pytest.raises(EgressDeniedError):
        egress.validate_remote_endpoint(url, require_https=False)


def test_endpoint_policy_rejects_dns_failure_and_private_dual_stack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def dns_failure(*_args, **_kwargs):
        raise socket.gaierror("synthetic DNS failure")

    monkeypatch.setattr(socket, "getaddrinfo", dns_failure)
    endpoint = egress.validate_remote_endpoint("https://example.com", require_https=True)
    with pytest.raises(EgressDeniedError, match="DNS resolution failed"):
        egress.resolve_public_endpoint(endpoint)

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0)),
        ],
    )
    with pytest.raises(EgressDeniedError, match="non-public"):
        egress.resolve_public_endpoint(endpoint)


def test_llm_custom_origin_requires_exact_explicit_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(EgressDeniedError, match="explicit allowlist"):
        validate_llm_endpoint("https://api.example.com/api/v1")
    monkeypatch.setenv("POWER_LLM_ALLOWED_ORIGINS", "https://api.example.com")
    assert (
        validate_llm_endpoint("https://api.example.com/api/v1").origin == "https://api.example.com"
    )


@pytest.mark.parametrize("path", ["/api/v1evil", "/api/v10", "/api/v1evil/private"])
def test_openrouter_endpoint_requires_exact_api_v1_path(path: str) -> None:
    with pytest.raises(EgressDeniedError, match="under /api/v1"):
        validate_llm_endpoint(f"https://openrouter.ai{path}")


def test_openrouter_endpoint_allows_paths_below_api_v1() -> None:
    assert validate_llm_endpoint("https://openrouter.ai/api/v1/chat/completions").path == (
        "/api/v1/chat/completions"
    )


def test_bearer_requires_explicit_origin_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(egress, "resolve_public_endpoint", lambda _endpoint: ("93.184.216.34",))
    monkeypatch.setattr(
        egress,
        "_request_once",
        lambda endpoint, _address, **_kwargs: SafeHttpResponse(
            endpoint.original_url, 200, {}, b"ok"
        ),
    )
    with pytest.raises(EgressDeniedError, match="explicit endpoint allowlist"):
        safe_http_request("https://example.com/api", headers={"Authorization": "Bearer token"})


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:11434", "http://[::1]:11434", "http://localhost:11434"],
)
def test_local_ollama_loopback_endpoints_remain_supported(url: str) -> None:
    validate_local_ollama_endpoint(url)


def test_bearer_is_not_reintroduced_after_cross_origin_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, str]] = []

    def fake_request(endpoint, _pinned_address, *, headers, **_kwargs):
        captured.append(dict(headers or {}))
        if len(captured) == 1:
            return SafeHttpResponse(
                endpoint.original_url, 302, {"location": "https://other.example"}, b""
            )
        if len(captured) == 2:
            return SafeHttpResponse(
                endpoint.original_url, 302, {"location": "https://example.com/api/final"}, b""
            )
        return SafeHttpResponse(endpoint.original_url, 200, {}, b"ok")

    monkeypatch.setattr(egress, "resolve_public_endpoint", lambda _endpoint: ("93.184.216.34",))
    monkeypatch.setattr(egress, "_request_once", fake_request)
    response = safe_http_request(
        "https://example.com/api/start",
        headers={"Authorization": "Bearer token"},
        allowed_origins=frozenset({"https://example.com", "https://other.example"}),
        max_redirects=2,
    )
    assert response.status == 200
    assert captured[0]["Authorization"] == "Bearer token"
    assert all(key.lower() != "authorization" for headers in captured[1:] for key in headers)


def test_redirect_to_private_is_rejected_before_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_request(endpoint, pinned_address, **_kwargs):
        calls.append(endpoint.original_url)
        return SafeHttpResponse(
            endpoint.original_url,
            302,
            {"location": "http://127.0.0.1/metadata"},
            b"",
        )

    monkeypatch.setattr(egress, "resolve_public_endpoint", lambda _endpoint: ("93.184.216.34",))
    monkeypatch.setattr(egress, "_request_once", fake_request)
    with pytest.raises(EgressDeniedError, match="not public"):
        safe_http_request("https://example.com", require_https=False, max_redirects=2)
    assert calls == ["https://example.com"]


def test_cross_origin_redirect_drops_bearer_header(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict[str, str]] = []

    def fake_request(endpoint, _pinned_address, *, headers, **_kwargs):
        captured.append(dict(headers or {}))
        if len(captured) == 1:
            return SafeHttpResponse(
                endpoint.original_url, 302, {"location": "https://other.example"}, b""
            )
        return SafeHttpResponse(endpoint.original_url, 200, {}, b"ok")

    monkeypatch.setattr(egress, "resolve_public_endpoint", lambda _endpoint: ("93.184.216.34",))
    monkeypatch.setattr(egress, "_request_once", fake_request)
    response = safe_http_request(
        "https://example.com/api",
        headers={"Authorization": "Bearer secret"},
        allowed_origins=frozenset({"https://example.com", "https://other.example"}),
        max_redirects=1,
    )
    assert response.status == 200
    assert captured[0]["Authorization"] == "Bearer secret"
    assert all(key.lower() != "authorization" for key in captured[1])
