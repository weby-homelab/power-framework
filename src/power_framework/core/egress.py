"""Central fail-closed policy for sending vault-derived data off-host."""

from __future__ import annotations

import http.client
import ipaddress
import os
import socket
import ssl
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit

from .models import Sensitivity

if TYPE_CHECKING:
    from collections.abc import Mapping


class EgressOperation(StrEnum):
    """Every POWER path that can contact a non-local service."""

    EMBEDDINGS = "embeddings"
    RERANKING = "reranking"
    QUERY_EXPANSION = "query_expansion"
    ROT = "rot"


class EgressDeniedError(PermissionError):
    """Raised before sensitive vault content can leave the local host."""


class EndpointPolicyError(EgressDeniedError):
    """Raised when an external endpoint cannot be proven safe to contact."""


class _PolicyLevel(IntEnum):
    DENY = 0
    PUBLIC = 1
    INTERNAL = 2
    SENSITIVE = 3


_LEVELS = {
    "deny": _PolicyLevel.DENY,
    "allow-public": _PolicyLevel.PUBLIC,
    "allow-internal": _PolicyLevel.INTERNAL,
    "allow-sensitive": _PolicyLevel.SENSITIVE,
}
_SENSITIVITY_LEVELS = {
    Sensitivity.PUBLIC.value: _PolicyLevel.PUBLIC,
    Sensitivity.INTERNAL.value: _PolicyLevel.INTERNAL,
    Sensitivity.SENSITIVE.value: _PolicyLevel.SENSITIVE,
}

DEFAULT_LLM_API_BASE = "https://openrouter.ai/api/v1"
DEFAULT_LLM_ORIGIN = "https://openrouter.ai"
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_ENDPOINT_LENGTH = 2048


@dataclass(frozen=True)
class ValidatedEndpoint:
    """Normalized endpoint data used by the pinned direct HTTP client."""

    original_url: str
    scheme: str
    hostname: str
    port: int
    path: str
    query: str
    origin: str

    @property
    def request_target(self) -> str:
        """Return the path/query sent after the pinned connection is opened."""
        target = self.path or "/"
        return f"{target}?{self.query}" if self.query else target

    @property
    def host_header(self) -> str:
        """Return a host header that preserves the configured hostname and port."""
        host = f"[{self.hostname}]" if ":" in self.hostname else self.hostname
        default_port = 443 if self.scheme == "https" else 80
        return host if self.port == default_port else f"{host}:{self.port}"


@dataclass(frozen=True)
class SafeHttpResponse:
    """Bounded response data returned by the direct endpoint client."""

    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes


def _is_unsafe_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Reject every non-public address, including IPv4-mapped IPv6 aliases."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return not address.is_global


def _parse_origin(value: str) -> str:
    """Normalize an exact HTTPS/HTTP origin from explicit configuration."""
    endpoint = _validate_endpoint_syntax(value, require_https=False)
    if endpoint.path not in {"", "/"} or endpoint.query:
        raise EndpointPolicyError("allowed endpoint origins must not contain a path or query")
    return endpoint.origin


def _validate_endpoint_syntax(url: str, *, require_https: bool) -> ValidatedEndpoint:
    """Validate URL syntax without performing DNS or network I/O."""
    if not isinstance(url, str) or not url or len(url) > _MAX_ENDPOINT_LENGTH:
        raise EndpointPolicyError("endpoint URL is missing or exceeds the length limit")
    if any(ord(character) < 32 or ord(character) == 127 for character in url):
        raise EndpointPolicyError("endpoint URL contains control characters")
    parsed = urlsplit(url)
    if parsed.scheme not in ({"https"} if require_https else {"http", "https"}):
        expected = "https" if require_https else "http or https"
        raise EndpointPolicyError(f"endpoint must use {expected}")
    if parsed.username is not None or parsed.password is not None:
        raise EndpointPolicyError("endpoint userinfo is forbidden")
    if parsed.fragment:
        raise EndpointPolicyError("endpoint fragments are forbidden")
    if not parsed.hostname:
        raise EndpointPolicyError("endpoint hostname is required")
    try:
        port = parsed.port
    except ValueError as exc:
        raise EndpointPolicyError("endpoint port is invalid") from exc
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    if not 1 <= port <= 65535:
        raise EndpointPolicyError("endpoint port is outside the valid range")
    hostname = parsed.hostname.rstrip(".").lower()
    if (
        not hostname
        or hostname in {"localhost", "localhost.localdomain"}
        or hostname.endswith(".localhost")
    ):
        raise EndpointPolicyError("localhost endpoints are forbidden")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise EndpointPolicyError("endpoint hostname is not valid IDNA") from exc
    else:
        if _is_unsafe_address(literal):
            raise EndpointPolicyError("endpoint address is not public")
    default_port = 443 if parsed.scheme == "https" else 80
    host_for_origin = f"[{hostname}]" if ":" in hostname else hostname
    origin = f"{parsed.scheme}://{host_for_origin}"
    if port != default_port:
        origin = f"{origin}:{port}"
    return ValidatedEndpoint(
        original_url=url,
        scheme=parsed.scheme,
        hostname=hostname,
        port=port,
        path=parsed.path,
        query=parsed.query,
        origin=origin,
    )


def validate_remote_endpoint(
    url: str,
    *,
    require_https: bool = True,
    allowed_origins: frozenset[str] | None = None,
    allow_query: bool = True,
) -> ValidatedEndpoint:
    """Validate a URL and optional exact-origin allowlist before DNS resolution."""
    endpoint = _validate_endpoint_syntax(url, require_https=require_https)
    if not allow_query and endpoint.query:
        raise EndpointPolicyError("endpoint query parameters are forbidden")
    if allowed_origins is not None and endpoint.origin not in allowed_origins:
        raise EndpointPolicyError("endpoint origin is not in the explicit allowlist")
    return endpoint


def resolve_public_endpoint(endpoint: ValidatedEndpoint) -> tuple[str, ...]:
    """Resolve all A/AAAA records and return stable public addresses only."""
    try:
        records = socket.getaddrinfo(
            endpoint.hostname,
            endpoint.port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise EndpointPolicyError("endpoint DNS resolution failed") from exc
    addresses: set[str] = set()
    for record in records:
        sockaddr = record[4]
        if not sockaddr:
            continue
        address_text = sockaddr[0]
        try:
            address = ipaddress.ip_address(address_text)
        except ValueError as exc:
            raise EndpointPolicyError("endpoint DNS returned an invalid address") from exc
        if _is_unsafe_address(address):
            raise EndpointPolicyError("endpoint DNS returned a non-public address")
        addresses.add(str(address))
    if not addresses:
        raise EndpointPolicyError("endpoint DNS returned no addresses")
    return tuple(sorted(addresses))


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that pins TCP to the already validated address."""

    def __init__(self, hostname: str, pinned_address: str, port: int, timeout: float) -> None:
        super().__init__(hostname, port=port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = pinned_address

    def connect(self) -> None:
        if getattr(self, "_tunnel_host", None):
            raise EndpointPolicyError("HTTP CONNECT proxy tunnels are forbidden")
        source_address = getattr(self, "source_address", None)
        context = getattr(self, "_context", None)
        if not isinstance(context, ssl.SSLContext):
            raise EndpointPolicyError("HTTPS context is unavailable")
        self.sock = socket.create_connection(
            (self._pinned_address, self.port),
            self.timeout,
            source_address,
        )
        self.sock = context.wrap_socket(self.sock, server_hostname=self.host)


def _request_once(
    endpoint: ValidatedEndpoint,
    pinned_address: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    body: bytes | None,
    timeout: float,
    max_bytes: int,
) -> SafeHttpResponse:
    """Perform one direct request using a resolved, pinned public address."""
    request_headers = {
        key: value for key, value in (headers or {}).items() if key.lower() != "host"
    }
    request_headers["Host"] = endpoint.host_header
    connection: http.client.HTTPConnection
    if endpoint.scheme == "https":
        connection = _PinnedHTTPSConnection(
            endpoint.hostname, pinned_address, endpoint.port, timeout
        )
    else:
        connection = http.client.HTTPConnection(pinned_address, endpoint.port, timeout=timeout)
    try:
        connection.request(
            method.upper(), endpoint.request_target, body=body, headers=request_headers
        )
        response = connection.getresponse()
        payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise EndpointPolicyError("endpoint response exceeds the size limit")
        return SafeHttpResponse(
            url=endpoint.original_url,
            status=response.status,
            headers={key.lower(): value for key, value in response.getheaders()},
            body=payload,
        )
    except EndpointPolicyError:
        raise
    except (OSError, http.client.HTTPException) as exc:
        raise EndpointPolicyError("endpoint request failed") from exc
    finally:
        connection.close()


def safe_http_request(
    url: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
    require_https: bool = True,
    allowed_origins: frozenset[str] | None = None,
    allow_query: bool = True,
    max_redirects: int = 0,
    timeout: float = 15.0,
    max_bytes: int = 1_048_576,
) -> SafeHttpResponse:
    """Perform bounded direct HTTP with per-hop syntax, DNS and origin checks."""
    if max_redirects < 0 or max_redirects > 5:
        raise EndpointPolicyError("redirect limit is outside the supported range")
    current_url = url
    initial_scheme: str | None = None
    visited: set[str] = set()
    for hop in range(max_redirects + 1):
        endpoint = validate_remote_endpoint(
            current_url,
            require_https=require_https,
            allowed_origins=allowed_origins,
            allow_query=allow_query,
        )
        if initial_scheme is None:
            initial_scheme = endpoint.scheme
        elif initial_scheme == "https" and endpoint.scheme != "https":
            raise EndpointPolicyError("HTTPS endpoint downgrade through redirect is forbidden")
        if endpoint.original_url in visited:
            raise EndpointPolicyError("endpoint redirect loop detected")
        visited.add(endpoint.original_url)
        request_headers = dict(headers or {})
        if (
            hop
            and endpoint.origin
            != validate_remote_endpoint(
                url,
                require_https=require_https,
                allowed_origins=allowed_origins,
                allow_query=allow_query,
            ).origin
        ):
            request_headers = {
                key: value
                for key, value in request_headers.items()
                if key.lower() != "authorization"
            }
        response = _request_once(
            endpoint,
            resolve_public_endpoint(endpoint)[0],
            method=method,
            headers=request_headers,
            body=body,
            timeout=timeout,
            max_bytes=max_bytes,
        )
        if response.status not in _REDIRECT_STATUSES:
            return response
        if hop >= max_redirects:
            raise EndpointPolicyError("endpoint redirect is not permitted")
        location = response.headers.get("location")
        if not location:
            raise EndpointPolicyError("endpoint redirect has no Location header")
        current_url = urljoin(current_url, location)
    raise EndpointPolicyError("endpoint redirect policy exhausted")


def configured_llm_origins() -> frozenset[str]:
    """Return the default OpenRouter origin plus explicitly approved custom origins."""
    raw = os.getenv("POWER_LLM_ALLOWED_ORIGINS", "")
    origins = {DEFAULT_LLM_ORIGIN}
    for item in raw.split(","):
        if item.strip():
            origins.add(_parse_origin(item.strip()))
    return frozenset(origins)


def validate_llm_endpoint(url: str) -> ValidatedEndpoint:
    """Validate an HTTPS LLM base against the explicit origin policy."""
    endpoint = validate_remote_endpoint(
        url,
        require_https=True,
        allowed_origins=configured_llm_origins(),
        allow_query=False,
    )
    if endpoint.origin == DEFAULT_LLM_ORIGIN and not endpoint.path.startswith("/api/v1"):
        raise EndpointPolicyError("OpenRouter endpoint must remain under /api/v1")
    return endpoint


def configured_egress_policy() -> str:
    """Return the explicit policy name; absent configuration always denies."""
    return os.getenv("POWER_EGRESS_POLICY", "deny").lower()


def require_remote_egress(operation: EgressOperation, sensitivity: str = "internal") -> None:
    """Permit a remote call only under a policy explicit enough for its data."""
    policy = configured_egress_policy()
    allowed = _LEVELS.get(policy)
    level = _SENSITIVITY_LEVELS.get(sensitivity.lower())
    if allowed is None:
        raise EgressDeniedError(
            "POWER_EGRESS_POLICY must be deny, allow-public, allow-internal, or allow-sensitive"
        )
    if level is None:
        raise EgressDeniedError(f"Unknown sensitivity '{sensitivity}' for {operation.value}")
    if allowed < level:
        raise EgressDeniedError(
            f"remote {operation.value} denied for {sensitivity} content by POWER_EGRESS_POLICY={policy}"
        )


def is_remote_endpoint(url: str) -> bool:
    """Treat only syntactically valid non-local HTTP endpoints as remote."""
    try:
        endpoint = validate_remote_endpoint(url, require_https=False)
    except EndpointPolicyError:
        return False
    return endpoint.hostname not in {"localhost", "localhost.localdomain"}
