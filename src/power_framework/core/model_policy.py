"""Central model acquisition policy for POWER optional neural backends.

The model identifier is configuration input, not an authorization grant.  This
module keeps the egress check, immutable revision check, approval binding, and
runtime-file verification in one small boundary shared by direct Hugging Face
loaders and adapters that delegate loading to another package.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import TYPE_CHECKING

from . import egress

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from .egress import EgressOperation


MODEL_APPROVAL_ENV = "POWER_MODEL_APPROVAL"
ALLOW_CUSTOM_MODELS_ENV = "POWER_ALLOW_CUSTOM_MODELS"
MODEL_OFFLINE_ENV_VARS = (
    "POWER_MODEL_OFFLINE",
    "HF_HUB_OFFLINE",
    "TRANSFORMERS_OFFLINE",
)
DEFAULT_MODEL_ENDPOINT = "https://huggingface.co"

_IMMUTABLE_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_APPROVAL_BYTES = 64 * 1024
_MODEL_ENV_LOCK = RLock()


class ModelPolicyError(RuntimeError):
    """Base class for fail-closed model policy failures."""


class ModelApprovalError(ModelPolicyError):
    """Raised when a model identity is not explicitly approved."""


class ModelOfflineError(ModelPolicyError):
    """Raised when offline mode cannot satisfy a model request from cache."""


class ModelIntegrityError(ModelPolicyError):
    """Raised when a model snapshot is incomplete or its bytes are not pinned."""


@dataclass(frozen=True)
class ApprovedModel:
    """One exact model identity and its complete runtime-file hash manifest."""

    repo: str
    revision: str
    provider: str
    license: str
    files: tuple[tuple[str, str], ...]
    canonical: bool

    @property
    def hashes(self) -> dict[str, str]:
        """Return the expected hash for every approved runtime file."""
        return dict(self.files)


@dataclass
class PreparedModel:
    """Verified local files ready to be handed to an external model loader."""

    spec: ApprovedModel
    files: dict[str, str]
    local_reference: str
    _release_lock: RLock = field(default_factory=RLock, init=False, repr=False, compare=False)
    _released: bool = field(default=False, init=False, repr=False, compare=False)

    def release(self) -> None:
        """Release this model's private staging tree exactly once."""
        with self._release_lock:
            if self._released:
                return
            staging_root = Path(self.local_reference)
            if staging_root.is_symlink():
                raise ModelIntegrityError("model_staging_root_is_symlink")
            if staging_root.exists():
                if not staging_root.is_dir():
                    raise ModelIntegrityError("model_staging_root_is_not_directory")
                shutil.rmtree(staging_root)
            self._released = True

    def close(self) -> None:
        """Compatibility alias for :meth:`release` used by manager shutdown."""
        self.release()


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


def model_offline() -> bool:
    """Return whether any POWER or maintained HF offline flag is authoritative."""
    with _MODEL_ENV_LOCK:
        return any(_env_flag(name) for name in MODEL_OFFLINE_ENV_VARS)


def _validate_repository(repo: str) -> str:
    if not isinstance(repo, str) or not _REPOSITORY_RE.fullmatch(repo):
        raise ModelApprovalError("invalid_model_repository")
    return repo


def _validate_provider(provider: str) -> str:
    if not isinstance(provider, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", provider
    ):
        raise ModelApprovalError("invalid_model_provider")
    return provider


def _validate_license(license_name: str) -> str:
    if not isinstance(license_name, str) or not license_name.strip() or len(license_name) > 128:
        raise ModelApprovalError("model_license_required")
    return license_name.strip()


def _validate_revision(revision: str | None) -> str:
    if not isinstance(revision, str) or not _IMMUTABLE_REVISION_RE.fullmatch(revision):
        raise ModelApprovalError("immutable_model_revision_required")
    return revision


def _validate_file_names(required_files: tuple[str, ...]) -> tuple[str, ...]:
    if not required_files or len(set(required_files)) != len(required_files):
        raise ModelIntegrityError("complete_model_file_manifest_required")
    for filename in required_files:
        if not isinstance(filename, str) or not filename or "\\" in filename:
            raise ModelIntegrityError("invalid_model_runtime_file")
        path = PurePosixPath(filename)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ModelIntegrityError("invalid_model_runtime_file")
    return tuple(required_files)


def _validate_hash_manifest(
    files: Mapping[str, object], required_files: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    expected_names = set(required_files)
    if set(files) != expected_names:
        raise ModelIntegrityError("complete_model_file_manifest_required")
    normalized: list[tuple[str, str]] = []
    for filename in required_files:
        digest = files.get(filename)
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest.lower()):
            raise ModelIntegrityError(f"invalid_model_sha256:{filename}")
        normalized.append((filename, digest.lower()))
    return tuple(normalized)


def _load_custom_approval(
    *,
    operation: EgressOperation,
    repo: str,
    revision: str,
    provider: str,
    expected_license: str | None,
    required_files: tuple[str, ...],
) -> ApprovedModel:
    if not _env_flag(ALLOW_CUSTOM_MODELS_ENV):
        raise ModelApprovalError("custom_model_requires_approval")
    raw = os.getenv(MODEL_APPROVAL_ENV, "").strip()
    if not raw or len(raw.encode("utf-8")) > _MAX_APPROVAL_BYTES:
        raise ModelApprovalError("custom_model_requires_approval")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ModelApprovalError("custom_model_approval_is_invalid") from exc
    if not isinstance(payload, dict):
        raise ModelApprovalError("custom_model_approval_is_invalid")
    if payload.get("repo") != repo or payload.get("revision") != revision:
        raise ModelApprovalError("custom_model_identity_not_approved")
    if payload.get("operation") != operation.value:
        raise ModelApprovalError("custom_model_operation_not_approved")
    if payload.get("provider") != provider:
        raise ModelApprovalError("custom_model_provider_not_approved")
    license_name = _validate_license(payload.get("license", ""))
    if expected_license is not None and license_name != _validate_license(expected_license):
        raise ModelApprovalError("custom_model_license_not_approved")
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ModelIntegrityError("complete_model_file_manifest_required")
    hashes = _validate_hash_manifest(files, required_files)
    return ApprovedModel(
        repo=repo,
        revision=revision,
        provider=provider,
        license=license_name,
        files=hashes,
        canonical=False,
    )


def resolve_model(
    *,
    operation: EgressOperation,
    repo: str,
    revision: str | None,
    provider: str,
    required_files: tuple[str, ...],
    canonical_repo: str,
    canonical_revision: str,
    canonical_provider: str,
    canonical_license: str,
    canonical_hashes: Mapping[str, str],
    custom_license: str | None = None,
) -> ApprovedModel:
    """Resolve a canonical or explicitly approved custom model identity."""
    validated_repo = _validate_repository(repo)
    validated_revision = _validate_revision(revision)
    validated_provider = _validate_provider(provider)
    filenames = _validate_file_names(required_files)
    if (
        validated_repo == canonical_repo
        and validated_revision == canonical_revision
        and validated_provider == canonical_provider
    ):
        hashes = _validate_hash_manifest(canonical_hashes, filenames)
        return ApprovedModel(
            repo=validated_repo,
            revision=validated_revision,
            provider=validated_provider,
            license=_validate_license(canonical_license),
            files=hashes,
            canonical=True,
        )
    expected_custom_license = (
        custom_license
        if custom_license is not None
        else (canonical_license if validated_provider == canonical_provider else None)
    )
    return _load_custom_approval(
        operation=operation,
        repo=validated_repo,
        revision=validated_revision,
        provider=validated_provider,
        expected_license=expected_custom_license,
        required_files=filenames,
    )


def _cached_model_files(spec: ApprovedModel) -> dict[str, str]:
    """Return complete local HF cache hits without performing network I/O."""
    cache_override = os.getenv("HF_HUB_CACHE")
    if cache_override:
        cache_root = Path(cache_override).expanduser()
    else:
        hf_home = os.getenv("HF_HOME")
        if hf_home:
            cache_root = Path(hf_home).expanduser() / "hub"
        else:
            xdg_cache = os.getenv("XDG_CACHE_HOME")
            cache_root = (
                Path(xdg_cache).expanduser() / "huggingface" / "hub"
                if xdg_cache
                else Path.home() / ".cache" / "huggingface" / "hub"
            )
    snapshot_root = (
        cache_root / f"models--{spec.repo.replace('/', '--')}" / "snapshots" / spec.revision
    )
    cached: dict[str, str] = {}
    for filename, _expected in spec.files:
        candidate = snapshot_root / filename
        if candidate.is_file():
            cached[filename] = str(candidate)
    return cached


def _verify_model_files(spec: ApprovedModel, paths: Mapping[str, str]) -> dict[str, str]:
    """Verify every approved runtime file before returning paths to a loader."""
    expected = spec.hashes
    if set(paths) != set(expected):
        missing = ",".join(sorted(set(expected) - set(paths)))
        raise ModelIntegrityError(f"incomplete_model_snapshot:{missing}")
    verified: dict[str, str] = {}
    for filename, expected_digest in spec.files:
        path = Path(paths[filename])
        if not path.is_file():
            raise ModelIntegrityError(f"missing_model_runtime_file:{filename}")
        checksum = hashlib.sha256()
        with path.open("rb") as model_file:
            for chunk in iter(lambda: model_file.read(8 * 1024 * 1024), b""):
                checksum.update(chunk)
        actual_hash = checksum.hexdigest()
        if actual_hash != expected_digest:
            raise ModelIntegrityError(f"model_sha256_mismatch:{filename}")
        verified[filename] = str(path)
    return verified


def verify_model_files(spec: ApprovedModel, paths: Mapping[str, str]) -> dict[str, str]:
    """Verify a model file mapping without acquiring or loading any model."""
    return _verify_model_files(spec, paths)


def _acquire_resolved_model(spec: ApprovedModel, operation: EgressOperation) -> dict[str, str]:
    """Acquire one approved model while serializing constructor environment windows."""
    with _MODEL_ENV_LOCK:
        return _acquire_resolved_model_locked(spec, operation)


def _acquire_resolved_model_locked(
    spec: ApprovedModel, operation: EgressOperation
) -> dict[str, str]:
    """Use cache when complete; otherwise authorize and fetch exactly pinned files."""
    cached = _cached_model_files(spec)
    if len(cached) == len(spec.files):
        return verify_model_files(spec, cached)
    if model_offline():
        raise ModelOfflineError("model_offline_cache_missing")

    # This is intentionally before importing/calling any HF network-capable API.
    egress.require_remote_egress(operation, "public")
    configured_endpoint = os.getenv("HF_ENDPOINT", DEFAULT_MODEL_ENDPOINT).strip().rstrip("/")
    try:
        endpoint = egress.validate_remote_endpoint(
            configured_endpoint,
            require_https=True,
            allowed_origins=frozenset({DEFAULT_MODEL_ENDPOINT}),
            allow_query=False,
        )
    except egress.EgressDeniedError as exc:
        raise ModelApprovalError("model_endpoint_not_approved") from exc
    if endpoint.path not in {"", "/"}:
        raise ModelApprovalError("model_endpoint_not_approved")
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise ModelPolicyError("huggingface_hub_required_for_model_acquisition") from exc

    downloaded: dict[str, str] = {}
    for filename, _expected in spec.files:
        downloaded[filename] = str(
            hf_hub_download(
                spec.repo,
                filename,
                revision=spec.revision,
                local_files_only=False,
                endpoint=endpoint.origin,
            )
        )
    return verify_model_files(spec, downloaded)


def acquire_model_files(
    *,
    operation: EgressOperation,
    repo: str,
    revision: str | None,
    provider: str,
    required_files: tuple[str, ...],
    canonical_repo: str,
    canonical_revision: str,
    canonical_provider: str,
    canonical_license: str,
    canonical_hashes: Mapping[str, str],
    custom_license: str | None = None,
) -> dict[str, str]:
    """Authorize, acquire, and verify a direct HF model snapshot."""
    spec = resolve_model(
        operation=operation,
        repo=repo,
        revision=revision,
        provider=provider,
        required_files=required_files,
        canonical_repo=canonical_repo,
        canonical_revision=canonical_revision,
        canonical_provider=canonical_provider,
        canonical_license=canonical_license,
        canonical_hashes=canonical_hashes,
        custom_license=custom_license,
    )
    return _acquire_resolved_model(spec, operation)


def _split_model_reference(model_reference: str) -> tuple[str, str]:
    """Split ``org/model@40-hex-commit`` references used by delegated loaders."""
    if not isinstance(model_reference, str) or "@" not in model_reference:
        raise ModelApprovalError("immutable_model_revision_required")
    repo, revision = model_reference.rsplit("@", 1)
    return _validate_repository(repo), _validate_revision(revision)


def prepare_external_model(
    *,
    operation: EgressOperation,
    provider: str,
    model_reference: str,
    expected_license: str | None = None,
) -> PreparedModel:
    """Prepare a custom delegated-loader model and return a local verified snapshot.

    Delegated loaders do not expose a stable revision/hash API.  They therefore
    accept only the exact ``repo@revision`` reference from an approval manifest,
    acquire every manifest file through this boundary, and receive a local path
    while all maintained offline flags are forced during construction.
    """
    repo, revision = _split_model_reference(model_reference)
    if not _env_flag(ALLOW_CUSTOM_MODELS_ENV):
        raise ModelApprovalError("custom_model_requires_approval")
    raw = os.getenv(MODEL_APPROVAL_ENV, "").strip()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ModelApprovalError("custom_model_approval_is_invalid") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), dict):
        raise ModelIntegrityError("complete_model_file_manifest_required")
    required_files = tuple(str(filename) for filename in payload["files"])
    spec = resolve_model(
        operation=operation,
        repo=repo,
        revision=revision,
        provider=provider,
        required_files=required_files,
        canonical_repo="__no_delegated_canonical_model__",
        canonical_revision="0" * 40,
        canonical_provider="__no_delegated_provider__",
        canonical_license="custom",
        canonical_hashes={},
        custom_license=expected_license,
    )
    files = _acquire_resolved_model(spec, operation)
    # Never expose the shared HF snapshot to a delegated loader: it may contain
    # unapproved config, code, tokenizer, or checkpoint files. Hardlinks avoid
    # copying multi-gigabyte model sidecars; the fallback copy keeps the same
    # isolated file set on filesystems that do not support hardlinks.
    staging_root = Path(tempfile.mkdtemp(prefix="power-model-"))
    prepared = PreparedModel(spec=spec, files={}, local_reference=str(staging_root))
    try:
        for filename, _digest in spec.files:
            source = Path(files[filename]).resolve(strict=True)
            destination = staging_root / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, destination)
            except OSError:
                shutil.copyfile(source, destination)
            prepared.files[filename] = str(destination)
        prepared.files = verify_model_files(spec, prepared.files)
    except BaseException as exc:
        try:
            prepared.release()
        except Exception as release_exc:
            raise release_exc from exc
        if isinstance(exc, Exception):
            raise ModelIntegrityError("isolated_model_snapshot_failed") from exc
        raise
    return prepared


@contextmanager
def force_model_offline(*, extra_environment: Mapping[str, str] | None = None) -> Iterator[None]:
    """Protect one delegated import/constructor window from remote acquisition.

    The lock is shared with :func:`model_offline`, so another POWER acquisition
    waits for the temporary constructor state and then reads the real user/CI
    policy after the environment is restored. Callers must not hold this context
    around normal model inference.
    """
    with _MODEL_ENV_LOCK:
        temporary = dict(extra_environment or {})
        for name in MODEL_OFFLINE_ENV_VARS:
            temporary[name] = "1"
        previous: dict[str, str | None] = {name: os.environ.get(name) for name in temporary}
        for name, temporary_value in temporary.items():
            os.environ[name] = temporary_value
        try:
            yield
        finally:
            for name, previous_value in previous.items():
                if previous_value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = previous_value


__all__ = [
    "ALLOW_CUSTOM_MODELS_ENV",
    "DEFAULT_MODEL_ENDPOINT",
    "MODEL_APPROVAL_ENV",
    "MODEL_OFFLINE_ENV_VARS",
    "ApprovedModel",
    "ModelApprovalError",
    "ModelIntegrityError",
    "ModelOfflineError",
    "ModelPolicyError",
    "PreparedModel",
    "acquire_model_files",
    "force_model_offline",
    "model_offline",
    "prepare_external_model",
    "resolve_model",
    "verify_model_files",
]
