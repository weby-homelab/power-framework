"""Conflict-safe local MCP client connection plans and transactions."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .utils import atomic_write, create_backup, restore_backup

ConnectClient = Literal["auto", "codex", "opencode", "gemini", "claude"]
ConnectAction = Literal["install", "remove"]
CONNECT_SCHEMA_VERSION = "power.connect-plan.v1"
_JSON_ROOTS = {"opencode": "mcp", "gemini": "mcpServers", "claude": "mcpServers"}


def default_config_path(client: str) -> Path:
    """Return the conventional user config path without creating it."""
    home = Path.home()
    if client == "codex":
        return home / ".codex" / "config.toml"
    if client == "opencode":
        return home / ".config" / "opencode" / "opencode.jsonc"
    if client == "gemini":
        return home / ".gemini" / "settings.json"
    if client == "claude":
        if platform.system() == "Darwin":
            return (
                home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
            )
        return home / ".config" / "Claude" / "claude_desktop_config.json"
    raise ValueError(f"Unsupported POWER client: {client}")


def resolve_client(client: ConnectClient, config_path: Path | None = None) -> str:
    """Resolve ``auto`` to an existing known client config, never by mutation."""
    if client != "auto":
        return client
    if config_path is not None:
        return _client_for_path(config_path)
    for candidate in ("codex", "opencode", "gemini", "claude"):
        if default_config_path(candidate).is_file():
            return candidate
    raise ValueError("client=auto found no existing Codex, OpenCode, Gemini, or Claude config")


def _client_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    name = path.name.lower()
    if suffix == ".toml":
        return "codex"
    if "opencode" in str(path).lower() or name.endswith(".jsonc"):
        return "opencode"
    if "gemini" in str(path).lower():
        return "gemini"
    return "claude"


def _server_entry(client: str, vault_path: Path, executable: str) -> dict[str, Any]:
    """Return the client-specific, content-free local stdio server entry."""
    command = [str(Path(executable)), "-m", "power_framework.mcp"]
    environment = {"POWER_VAULT_DIR": str(vault_path.resolve())}
    if client == "opencode":
        return {"type": "local", "command": command, "environment": environment, "enabled": True}
    return {"command": command[0], "args": command[1:], "env": environment}


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _jsonc_is_supported(content: str) -> bool:
    """Reject comments rather than silently deleting user-authored JSONC text."""
    return not re.search(r"(^|[^:\\])//|/\*|\*/", content, flags=re.MULTILINE)


def _load_json(path: Path, content: str) -> dict[str, Any]:
    if not _jsonc_is_supported(content):
        raise ValueError(
            f"JSONC comments in {path} require manual review; no rewrite was attempted"
        )
    try:
        payload = json.loads(content) if content.strip() else {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"cannot parse JSON client config {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"client config {path} must contain a JSON object")
    return payload


def _render_json(client: str, payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _render_toml(entry: dict[str, Any]) -> str:
    env_path = entry["env"]["POWER_VAULT_DIR"]
    return (
        "# power-connect:v1\n"
        "[mcp_servers.power]\n"
        f"command = {json.dumps(entry['command'])}\n"
        f"args = {json.dumps(entry['args'])}\n"
        f"env = {{ POWER_VAULT_DIR = {json.dumps(env_path)} }}\n"
    )


def _toml_payload(content: str, path: Path) -> dict[str, Any]:
    try:
        payload = tomllib.loads(content) if content.strip() else {}
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"cannot parse TOML client config {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"client config {path} must contain a TOML table")
    return payload


def _recover_preimage(
    client: str,
    config_path: Path,
    current: bytes,
    entry: dict[str, Any],
) -> bytes | None:
    """Recover the exact prior config when the current file is our last install."""
    backup_dir = config_path.parent / ".power-backups"
    if not backup_dir.is_dir():
        return None
    candidates = sorted(
        (
            path
            for path in backup_dir.glob(f"{config_path.stem}.*{config_path.suffix}")
            if path.is_file() and not path.is_symlink()
        ),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for candidate in candidates:
        try:
            preimage = candidate.read_bytes()
            if client == "codex":
                payload = _toml_payload(preimage.decode("utf-8"), candidate)
                servers = payload.get("mcp_servers", {})
                if not isinstance(servers, dict) or "power" in servers:
                    continue
                rendered = (
                    preimage.decode("utf-8").rstrip()
                    + ("\n\n" if preimage.strip() else "")
                    + _render_toml(entry)
                )
            else:
                payload = _load_json(candidate, preimage.decode("utf-8"))
                root = _JSON_ROOTS[client]
                servers = payload.get(root, {})
                if not isinstance(servers, dict) or "power" in servers:
                    continue
                payload[root] = servers
                servers["power"] = entry
                rendered = _render_json(client, payload)
            if rendered.encode("utf-8") == current:
                return preimage
        except (OSError, UnicodeError, ValueError):
            continue
    return None


def _prepare(
    client: str,
    action: ConnectAction,
    config_path: Path,
    vault_path: Path,
    executable: str,
) -> tuple[str, bytes, bytes | None, str | None]:
    """Return status, current bytes, desired bytes, and a conflict reason."""
    if config_path.is_symlink():
        return "manual_review", b"", None, "symlink client configs are never followed"
    current = config_path.read_bytes() if config_path.is_file() else b""
    entry = _server_entry(client, vault_path, executable)
    if client == "codex":
        payload = _toml_payload(current.decode("utf-8"), config_path)
        servers = payload.get("mcp_servers", {})
        if servers is not None and not isinstance(servers, dict):
            return "manual_review", current, None, "mcp_servers must be a TOML table"
        existing = servers.get("power") if isinstance(servers, dict) else None
        expected = {
            "command": entry["command"],
            "args": entry["args"],
            "env": entry["env"],
        }
        if action == "remove":
            if existing is None:
                return "no_change", current, current, None
            if existing != expected:
                return (
                    "manual_review",
                    current,
                    None,
                    "existing Codex power entry is not POWER-owned",
                )
            recovered = _recover_preimage(client, config_path, current, entry)
            if recovered is not None:
                return "ready", current, recovered, None
            rendered = re.sub(
                r"\n?# power-connect:v1\n\[mcp_servers\.power\]\n.*?(?=\n\[|\Z)",
                "",
                current.decode("utf-8"),
                flags=re.DOTALL,
            ).lstrip("\n")
            return "ready", current, rendered.encode("utf-8"), None
        if existing is not None:
            if existing == expected:
                return "no_change", current, current, None
            return "manual_review", current, None, "existing Codex power entry is not POWER-owned"
        rendered = (
            current.decode("utf-8").rstrip()
            + ("\n\n" if current.strip() else "")
            + _render_toml(entry)
        )
        return "ready", current, rendered.encode("utf-8"), None

    payload = _load_json(config_path, current.decode("utf-8"))
    root = _JSON_ROOTS[client]
    servers = payload.get(root, {})
    if not isinstance(servers, dict):
        return "manual_review", current, None, f"{root} must be a JSON object"
    existing = servers.get("power")
    if action == "remove":
        if existing is None:
            return "no_change", current, current, None
        if existing != entry:
            return "manual_review", current, None, "existing JSON power entry is not POWER-owned"
        recovered = _recover_preimage(client, config_path, current, entry)
        if recovered is not None:
            return "ready", current, recovered, None
        del servers["power"]
    else:
        if existing is not None:
            if existing == entry:
                return "no_change", current, current, None
            return "manual_review", current, None, "existing JSON power entry is not POWER-owned"
        payload[root] = servers
        servers["power"] = entry
    return "ready", current, _render_json(client, payload).encode("utf-8"), None


@dataclass(frozen=True)
class ConnectPlan:
    """Content-free, exact-hash-bound client connection plan."""

    client: str
    action: ConnectAction
    config_path: Path
    vault_path: Path
    executable: str
    status: str
    reason: str | None
    preimage_sha256: str
    desired_sha256: str
    changed: bool
    plan_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CONNECT_SCHEMA_VERSION,
            "client": self.client,
            "action": self.action,
            "config_path": str(self.config_path),
            "vault_path": str(self.vault_path),
            "executable": self.executable,
            "status": self.status,
            "reason": self.reason,
            "preimage_sha256": self.preimage_sha256,
            "desired_sha256": self.desired_sha256,
            "changed": self.changed,
            "plan_hash": self.plan_hash,
        }


def build_connect_plan(
    client: ConnectClient,
    vault_path: Path,
    *,
    config_path: Path | None = None,
    executable: str = sys.executable,
    action: ConnectAction = "install",
) -> ConnectPlan:
    """Build a read-only plan for one supported local client."""
    resolved_client = resolve_client(client, config_path)
    target = (config_path or default_config_path(resolved_client)).expanduser().resolve()
    vault = vault_path.expanduser().resolve()
    status, current, desired, reason = _prepare(resolved_client, action, target, vault, executable)
    desired_bytes = desired if desired is not None else current
    preimage_sha256 = _sha256_bytes(current)
    desired_sha256 = _sha256_bytes(desired_bytes)
    fields = {
        "schema_version": CONNECT_SCHEMA_VERSION,
        "client": resolved_client,
        "action": action,
        "config_path": str(target),
        "vault_path": str(vault),
        "executable": executable,
        "status": status,
        "reason": reason,
        "preimage_sha256": preimage_sha256,
        "desired_sha256": desired_sha256,
    }
    plan_hash = _sha256_bytes(json.dumps(fields, sort_keys=True).encode("utf-8"))
    return ConnectPlan(
        client=resolved_client,
        action=action,
        config_path=target,
        vault_path=vault,
        executable=executable,
        status=status,
        reason=reason,
        preimage_sha256=preimage_sha256,
        desired_sha256=desired_sha256,
        changed=desired is not None and desired != current,
        plan_hash=plan_hash,
    )


def apply_connect_plan(plan: dict[str, Any], *, approved: bool) -> dict[str, Any]:
    """Apply one unchanged approved plan and return a content-free receipt."""
    if not approved:
        raise PermissionError("connect apply requires explicit approval")
    if plan.get("schema_version") != CONNECT_SCHEMA_VERSION:
        raise ValueError("unsupported connect plan schema")
    action = plan.get("action")
    if action not in {"install", "remove"}:
        raise ValueError("connect plan action must be install or remove")
    current_plan = build_connect_plan(
        plan["client"],
        Path(plan["vault_path"]),
        config_path=Path(plan["config_path"]),
        executable=plan["executable"],
        action=action,
    )
    if current_plan.as_dict()["plan_hash"] != plan.get("plan_hash"):
        raise RuntimeError("connect plan is stale; regenerate the read-only plan")
    if current_plan.status == "manual_review":
        raise PermissionError(current_plan.reason or "client config requires manual review")
    if not current_plan.changed:
        return {
            "schema_version": CONNECT_SCHEMA_VERSION,
            "status": "no_change",
            "client": current_plan.client,
        }

    target = current_plan.config_path
    desired_status, _current, desired, reason = _prepare(
        current_plan.client,
        current_plan.action,
        target,
        current_plan.vault_path,
        current_plan.executable,
    )
    if desired_status != "ready" or desired is None:
        raise RuntimeError(reason or "connect plan no longer has a writable desired state")
    backup = (
        create_backup(target, backup_dir=target.parent / ".power-backups")
        if target.exists()
        else None
    )
    try:
        atomic_write(target, desired.decode("utf-8"))
        if _sha256_bytes(target.read_bytes()) != current_plan.desired_sha256:
            raise RuntimeError("connect postcondition hash mismatch")
    except Exception:
        if backup is not None:
            restore_backup(backup, target, overwrite=True)
        elif target.exists():
            target.unlink()
        raise
    return {
        "schema_version": CONNECT_SCHEMA_VERSION,
        "status": "applied",
        "client": current_plan.client,
        "action": current_plan.action,
        "config_sha256": current_plan.desired_sha256,
        "backup_created": backup is not None,
    }
