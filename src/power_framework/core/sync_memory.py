"""Memory pre-flight estimation, adaptive pressure sizing, and vmem caps for dense sync."""

from __future__ import annotations

import inspect
import logging
import os
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

try:  # resource is POSIX-only; Windows uses the no-limit path.
    import resource
except ImportError:  # pragma: no cover - exercised on Windows
    resource = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from collections.abc import Iterator

logger = logging.getLogger(__name__)

_MIB = 1024 * 1024
DEFAULT_PRESSURE_FLOOR_BYTES = 512 * _MIB
DEFAULT_EMBED_BATCH_SIZE = 8
MAX_EMBED_BATCH_SIZE = 128
DEFAULT_EMBED_COMMIT_EVERY = 50
MAX_EMBED_COMMIT_EVERY = 4096
_ALLOW_LOW_MEMORY: ContextVar[bool] = ContextVar("power_sync_allow_low_memory", default=False)


@dataclass(frozen=True)
class SyncMemoryEstimate:
    """Memory footprint estimate for one dense embedding sync pass."""

    provider: str
    model: str
    item_count: int
    embedding_dimension: int
    batch_size: int
    model_arena_bytes: int
    working_set_bytes: int
    total_estimated_bytes: int
    available_bytes: int | None
    recommended_batch_size: int


class MemoryPreflightError(RuntimeError):
    """Raised before model loading when available RAM is below estimated dense-sync demand."""

    def __init__(self, estimate: SyncMemoryEstimate) -> None:
        self.estimate = estimate
        est_mib = max(1, estimate.total_estimated_bytes // _MIB)
        avail_mib = (
            "unknown"
            if estimate.available_bytes is None
            else str(max(0, estimate.available_bytes // _MIB))
        )
        super().__init__(
            f"Dense sync preflight refused: estimated RAM ~{est_mib} MiB exceeds available "
            f"~{avail_mib} MiB (provider={estimate.provider}, model={estimate.model}, "
            f"items={estimate.item_count}, dim={estimate.embedding_dimension}). "
            "Pass --allow-low-memory (or POWER_SYNC_ALLOW_LOW_MEMORY=1) to force with "
            "batch_size=1, or run with --fts-only."
        )


@contextmanager
def low_memory_override(allow: bool) -> Iterator[None]:
    """Scope an explicit low-memory preflight bypass cleanly across a sync call."""
    token = _ALLOW_LOW_MEMORY.set(bool(allow))
    try:
        yield
    finally:
        _ALLOW_LOW_MEMORY.reset(token)


def is_low_memory_allowed(explicit: bool | None = None) -> bool:
    """Return whether an explicit low-memory override is active."""
    if isinstance(explicit, bool):
        return explicit
    if _ALLOW_LOW_MEMORY.get():
        return True
    env_flag = os.getenv("POWER_SYNC_ALLOW_LOW_MEMORY", "").strip().lower()
    return env_flag in {"1", "true", "yes"}


def parse_int_env(name: str, default: int, *, minimum: int = 0) -> int:
    """Parse an integer environment override without crashing on empty or malformed text."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return max(minimum, default)
    try:
        return max(minimum, int(raw))
    except ValueError:
        logger.warning("Ignoring invalid integer %s=%r; using %d", name, raw, default)
        return max(minimum, default)


def validate_positive_embedding_limit(name: str, value: int, maximum: int) -> int:
    """Validate that an embedding/commit limit is a bounded positive integer."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"invalid_{name.lower()}:expected_integer")
    if value < 1:
        raise ValueError(f"invalid_{name.lower()}:must_be_positive")
    if value > maximum:
        raise ValueError(f"invalid_{name.lower()}:maximum_is_{maximum}")
    return value


def read_positive_embedding_limit(name: str, default: int, maximum: int) -> int:
    """Read and validate a fail-closed positive integer limit from an environment variable."""
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"invalid_{name.lower()}:expected_integer") from None
    return validate_positive_embedding_limit(name, value, maximum)


def validated_embedding_limits() -> tuple[int, int]:
    """Validate bounded embedding batch and commit intervals before sync mutation."""
    return (
        read_positive_embedding_limit(
            "POWER_EMBED_BATCH_SIZE", DEFAULT_EMBED_BATCH_SIZE, MAX_EMBED_BATCH_SIZE
        ),
        read_positive_embedding_limit(
            "POWER_EMBED_COMMIT_EVERY", DEFAULT_EMBED_COMMIT_EVERY, MAX_EMBED_COMMIT_EVERY
        ),
    )


def apply_sync_vmem_cap(sync_embeddings: bool) -> int | None:
    """Apply optional POSIX ``RLIMIT_AS`` backstop from ``POWER_SYNC_VMEM_LIMIT_MB``.

    This remains an opt-in safeguard (``0`` = disabled) because dense ONNX
    backends such as BGE-M3 can reserve multi-GB virtual address spaces.
    """
    vmem_limit_mb = parse_int_env("POWER_SYNC_VMEM_LIMIT_MB", 0, minimum=0)
    if (
        vmem_limit_mb <= 0
        or not sync_embeddings
        or resource is None
        or not hasattr(resource, "RLIMIT_AS")
    ):
        return None
    try:
        getrlimit = getattr(resource, "getrlimit")  # noqa: B009 - optional POSIX module.
        setrlimit = getattr(resource, "setrlimit")  # noqa: B009 - optional POSIX module.
        _, hard = getrlimit(resource.RLIMIT_AS)
        requested = vmem_limit_mb * _MIB
        new_soft = min(requested, hard) if hard > 0 else requested
        applied_mb = new_soft // _MIB
        setrlimit(resource.RLIMIT_AS, (new_soft, hard))
        logger.info("Applied virtual-memory cap: %d MB", applied_mb)
        return applied_mb
    except (ValueError, OSError) as exc:  # pragma: no cover
        logger.warning("Could not apply vmem cap: %s", exc)
        return None


def available_memory_bytes() -> int | None:
    """Best-effort available physical RAM in bytes without inducing swapping."""
    meminfo_path = "/proc/meminfo"
    with suppress(OSError, ValueError), open(meminfo_path, encoding="utf-8") as fh:
        values: dict[str, int] = {}
        for line in fh:
            parts = line.split()
            if len(parts) >= 2 and parts[0].endswith(":"):
                key = parts[0][:-1]
                if key in {"MemAvailable", "MemFree", "Buffers", "Cached"}:
                    values[key] = int(parts[1]) * 1024
        if "MemAvailable" in values:
            return values["MemAvailable"]
        fallback = values.get("MemFree", 0) + values.get("Buffers", 0) + values.get("Cached", 0)
        if fallback > 0:
            return fallback

    if hasattr(os, "sysconf"):
        with suppress(ValueError, OSError):
            pages = int(os.sysconf("SC_AVPHYS_PAGES"))
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            if pages > 0 and page_size > 0:
                return pages * page_size
    return None


def infer_embedder_dimension(embedder: object | None, provider: str, model: str) -> int:
    """Determine vector width without triggering remote calls, lazy init, or @property getters."""
    if embedder is not None:
        # Use inspect.getattr_static so descriptor properties (OllamaEmbeddingManager.dimension,
        # FastEmbedManager.dimension) never execute HTTP calls or model loading before preflight.
        static_dim = inspect.getattr_static(embedder, "dimension", None)
        if isinstance(static_dim, int) and not isinstance(static_dim, bool) and static_dim > 0:
            return static_dim
        cached_dim = inspect.getattr_static(embedder, "_dim", None)
        if isinstance(cached_dim, int) and not isinstance(cached_dim, bool) and cached_dim > 0:
            return cached_dim
        if (
            not isinstance(static_dim, property)
            and callable(static_dim)
            and "ollama" not in provider.casefold()
            and "fastembed" not in provider.casefold()
        ):
            try:
                bound = (
                    static_dim.__get__(embedder, type(embedder))
                    if hasattr(static_dim, "__get__")
                    else static_dim
                )
                computed = int(bound())
                if computed > 0:
                    return computed
            except Exception:  # noqa: S110 - fall back cleanly before preflight
                pass
    lowered = f"{provider} {model}".casefold()
    if any(
        token in lowered
        for token in ("bge-m3", "bgem3", "bge_m3", "qwen3", "qwen", "large", "embeddinggemma")
    ):
        return 1024
    if "base" in lowered and "minilm" not in lowered and "small" not in lowered:
        return 768
    return 384


def estimate_model_arena_bytes(provider: str, model: str, embedding_dimension: int) -> int:
    """Estimate active model weights + inference arena RAM for the configured backend."""
    lowered = f"{provider} {model}".casefold()
    if "ollama" in lowered:
        return 256 * _MIB
    if (
        "bge-m3" in lowered
        or "bgem3" in lowered
        or "bge_m3" in lowered
        or ("bge" in lowered and embedding_dimension >= 1024)
    ):
        return 2200 * _MIB
    if "embeddinggemma" in lowered or "gemma" in lowered:
        return 1400 * _MIB
    if "qwen3" in lowered:
        return 1800 * _MIB
    if any(token in lowered for token in ("minilm", "small")) or (0 < embedding_dimension <= 384):
        return 512 * _MIB
    return (1536 if embedding_dimension >= 1024 else 512) * _MIB


def select_adaptive_batch_size(
    requested: int,
    available_bytes: int | None,
    model_arena_bytes: int,
) -> int:
    """Scale initial batch size down cleanly when free headroom above model arena is tight."""
    base = max(1, requested)
    if available_bytes is None:
        return base
    headroom = available_bytes - model_arena_bytes
    if headroom < 512 * _MIB:
        return 1
    if headroom < 1024 * _MIB:
        return min(base, 2)
    if headroom < 2048 * _MIB:
        return min(base, 4)
    return base


def should_shrink_batch_under_pressure(
    available_bytes: int | None,
    *,
    pressure_floor_bytes: int = DEFAULT_PRESSURE_FLOOR_BYTES,
) -> bool:
    """Return whether available RAM crossed below the safety floor mid-sync."""
    return available_bytes is not None and available_bytes < pressure_floor_bytes


def preflight_dense_sync_memory(
    *,
    provider: str,
    model: str,
    item_count: int,
    embedding_dimension: int,
    requested_batch_size: int,
    allow_low_memory: bool | None = None,
    available_bytes: int | None = None,
) -> SyncMemoryEstimate:
    """Estimate dense sync RAM before loading model weights and refuse on shortfall."""
    req_bs = max(1, requested_batch_size)
    avail = available_memory_bytes() if available_bytes is None else available_bytes
    if item_count <= 0:
        return SyncMemoryEstimate(
            provider=provider,
            model=model,
            item_count=0,
            embedding_dimension=embedding_dimension,
            batch_size=req_bs,
            model_arena_bytes=0,
            working_set_bytes=0,
            total_estimated_bytes=0,
            available_bytes=avail,
            recommended_batch_size=req_bs,
        )

    arena = estimate_model_arena_bytes(provider, model, embedding_dimension)
    rec_bs = select_adaptive_batch_size(req_bs, avail, arena)
    dim = max(embedding_dimension, 256)
    working_set = max(64 * _MIB, item_count * dim * 4 + rec_bs * dim * 256)
    total = arena + working_set
    estimate = SyncMemoryEstimate(
        provider=provider,
        model=model,
        item_count=item_count,
        embedding_dimension=embedding_dimension,
        batch_size=req_bs,
        model_arena_bytes=arena,
        working_set_bytes=working_set,
        total_estimated_bytes=total,
        available_bytes=avail,
        recommended_batch_size=rec_bs,
    )
    if avail is not None and total > avail:
        if is_low_memory_allowed(allow_low_memory):
            logger.warning(
                "Proceeding under explicit low-memory override: estimated RAM ~%d MiB "
                "exceeds available ~%d MiB (provider=%s, model=%s, items=%d, batch_size=1)",
                max(1, total // _MIB),
                max(0, avail // _MIB),
                provider,
                model,
                item_count,
            )
            return SyncMemoryEstimate(
                provider=provider,
                model=model,
                item_count=item_count,
                embedding_dimension=embedding_dimension,
                batch_size=req_bs,
                model_arena_bytes=arena,
                working_set_bytes=working_set,
                total_estimated_bytes=total,
                available_bytes=avail,
                recommended_batch_size=1,
            )
        raise MemoryPreflightError(estimate)
    return estimate
