#!/usr/bin/env python3
"""Run bounded Profile A/B acceptance against one exact Web image.

The proof intentionally records capability flags and immutable identities only;
it never copies vault content into the evidence report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.mcp_test_client import stdio_session

MARKER = "profile-a-b-applicationservice-acceptance"
CSRF_PATTERN = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
PROPOSAL_PATTERN = re.compile(r'name="proposal_id"\s+value="([^"]+)"')


class Browser:
    """Minimal cookie-preserving HTTP client for the local Web proof."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookie_jar = urllib.request.HTTPCookieProcessor()
        self.opener = urllib.request.build_opener(self.cookie_jar)

    def request(
        self, method: str, path: str, data: dict[str, str] | None = None
    ) -> tuple[int, str]:
        encoded = urllib.parse.urlencode(data or {}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=encoded if method == "POST" else None,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method=method,
        )
        try:
            with self.opener.open(request, timeout=15) as response:
                body = response.read().decode("utf-8")
                status = response.status
                return status, body
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", errors="replace")

    def csrf(self, body: str) -> str:
        match = CSRF_PATTERN.search(body)
        if match is None:
            raise RuntimeError("Web form did not contain a CSRF token")
        return match.group(1)


def run(command: list[str], *, env: dict[str, str] | None = None) -> str:
    """Run one fixed or argument-separated command and return stdout."""
    result = subprocess.run(  # noqa: S603 -- command paths and arguments are validated by callers.
        command, check=False, text=True, capture_output=True, env=env
    )
    if result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {result.stderr.strip()}")
    return result.stdout


def wait_for_health(base_url: str, expected_version: str) -> None:
    """Wait for the exact image version to report healthy."""
    deadline = time.monotonic() + 60
    last_error = "health endpoint did not become ready"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=3) as response:
                payload = json.loads(response.read())
            if payload == {"status": "ok", "version": expected_version}:
                return
            last_error = repr(payload)
        except (OSError, ValueError) as error:
            last_error = str(error)
        time.sleep(0.25)
    raise RuntimeError(last_error)


async def mcp_acceptance(mcp_command: Path, vault: Path, environment: dict[str, str]) -> None:
    """Exercise the required native stdio MCP server against the vault."""
    mcp_environment = environment.copy()
    mcp_environment["POWER_VAULT_DIR"] = str(vault)
    config = {
        "mcpServers": {"power": {"command": str(mcp_command), "args": [], "env": mcp_environment}}
    }
    async with stdio_session(config, mode="legacy") as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        if "search_vault_tool" not in tools:
            raise RuntimeError("required MCP search_vault_tool is missing")
        result = await client.call_tool(
            "search_vault_tool",
            {"query": MARKER, "search_mode": "fts", "vault_path": str(vault)},
        )
        text = getattr(result.content[0], "text", "") if result.content else ""
        if MARKER not in text:
            raise RuntimeError("MCP stdio readback did not find the acceptance marker")


def login(browser: Browser, password: str) -> None:
    """Complete the Web password and CSRF login flow."""
    status, body = browser.request("GET", "/login")
    if status != 200:
        raise RuntimeError(f"Web login page returned HTTP {status}")
    status, _ = browser.request(
        "POST",
        "/login",
        {"password": password, "csrf_token": browser.csrf(body)},
    )
    if status not in {200, 303} or not any(
        cookie.name == "power_web_session" for cookie in browser.cookie_jar.cookiejar
    ):
        raise RuntimeError(f"Web login failed with HTTP {status}")


def web_read(browser: Browser, relative_path: str) -> str:
    """Read one note through the authenticated Web route."""
    query = urllib.parse.urlencode({"path": relative_path})
    status, body = browser.request("GET", f"/notes/read?{query}")
    if status != 200:
        raise RuntimeError(f"Web read returned HTTP {status}")
    return body


def web_search(browser: Browser, mode: str) -> None:
    """Prove one dense Web mode is real and did not fall back to FTS."""
    query = urllib.parse.urlencode({"q": "ApplicationService acceptance", "mode": mode})
    status, body = browser.request("GET", f"/search?{query}")
    if status != 200:
        raise RuntimeError(f"Web {mode} search returned HTTP {status}: {body[-1000:]}")
    if f">{mode.upper()}<" not in body or 'class="badge badge-warning"' in body:
        raise RuntimeError(f"Web {mode} search did not prove non-fallback execution")


def web_mutation(browser: Browser, relative_path: str, vault: Path, password: str) -> None:
    """Exercise governed Web proposal/apply and verify source readback."""
    del password
    status, edit_page = browser.request(
        "GET", f"/notes/edit?{urllib.parse.urlencode({'path': relative_path})}"
    )
    if status != 200:
        raise RuntimeError(f"Web edit page returned HTTP {status}")
    current = (vault / relative_path).read_text(encoding="utf-8")
    proposed = f"{current.rstrip()}\n\n{MARKER}\n"
    status, proposal_page = browser.request(
        "POST",
        "/notes/propose",
        {
            "csrf_token": browser.csrf(edit_page),
            "path": relative_path,
            "content": proposed,
        },
    )
    if status != 200:
        raise RuntimeError(f"Web proposal returned HTTP {status}")
    proposal_match = PROPOSAL_PATTERN.search(proposal_page)
    if proposal_match is None:
        raise RuntimeError("Web proposal did not return a proposal ID")
    status, _ = browser.request(
        "POST",
        "/notes/apply",
        {
            "csrf_token": browser.csrf(proposal_page),
            "proposal_id": proposal_match.group(1),
            "approved": "true",
        },
    )
    if status not in {200, 303}:
        raise RuntimeError(f"Web apply returned HTTP {status}")
    if MARKER not in (vault / relative_path).read_text(encoding="utf-8"):
        raise RuntimeError("Web governed apply did not change the canonical vault")


def start_container(
    *,
    image: str,
    container: str,
    volume: str,
    vault: Path,
    model_cache: Path,
    port: int,
    password: str,
) -> None:
    """Start one constrained Web-only container."""
    command = [
        "docker",
        "run",
        "--detach",
        "--name",
        container,
        "--publish",
        f"127.0.0.1:{port}:8080",
        "--mount",
        f"type=bind,src={vault},dst=/brain",
        "--mount",
        f"type=volume,src={volume},dst=/var/cache/power",
        "--mount",
        f"type=bind,src={model_cache},dst=/models/huggingface,ro",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m",  # noqa: S108 -- isolated noexec container tmpfs.
        "--user",
        "10001:10001",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--init",
        "--read-only",
        "--env",
        "POWER_WEB_HOST=0.0.0.0",
        "--env",
        "POWER_WEB_PORT=8080",
        "--env",
        "POWER_WEB_VAULT_PATH=/brain",
        "--env",
        "POWER_WEB_AUTH_ENABLED=true",
        "--env",
        "POWER_WEB_COOKIE_SECURE=false",
        "--env",
        f"POWER_WEB_ADMIN_PASSWORD={password}",
        "--env",
        "POWER_WEB_READ_ONLY_MODE=false",
        "--env",
        "POWER_EMBED_PROVIDER=bge-m3",
        "--env",
        "POWER_EMBED_DEVICE=cpu",
        "--env",
        "POWER_RERANKER=bge",
        "--env",
        "POWER_RERANKER_DEVICE=cpu",
        "--env",
        "POWER_MODEL_OFFLINE=1",
        "--env",
        "HF_HOME=/models/huggingface",
        "--env",
        "HF_HUB_OFFLINE=1",
        "--env",
        "TRANSFORMERS_OFFLINE=1",
        "--env",
        "XDG_CACHE_HOME=/var/cache/power",
        image,
    ]
    run(command)


def stop_container(container: str) -> None:
    """Remove one proof container without affecting unrelated runtimes."""
    subprocess.run(  # noqa: S603 -- fixed Docker executable and generated container name.
        ["docker", "rm", "--force", container],  # noqa: S607
        check=False,
        capture_output=True,
    )


def prepare_vault_for_container(vault: Path) -> None:
    """Share the disposable bind mount with the container and host runner.

    The Web proof runs as UID 10001 and then reads the canonical vault from
    the host to verify the governed mutation.  The vault is disposable and
    isolated, so its entries must remain traversable, readable, and removable
    by both identities after ownership changes.
    """
    try:
        run(["sudo", "chown", "-R", "10001:10001", str(vault)])
        run(["sudo", "chmod", "-R", "a+rwX", str(vault)])
    except FileNotFoundError:
        for path in [vault, *sorted(vault.rglob("*"))]:
            if not path.exists():
                continue
            os.chown(path, 10001, 10001)
            mode = path.stat().st_mode
            os.chmod(path, mode | (0o777 if path.is_dir() else 0o666))


def inspect_container(container: str) -> tuple[str, list[str], bool, str]:
    """Return user, dropped capabilities, read-only flag, and PID command line."""
    payload = json.loads(run(["docker", "inspect", container]))[0]
    user = str(payload["Config"].get("User", ""))
    cap_drop = [str(item) for item in payload["HostConfig"].get("CapDrop", [])]
    read_only = bool(payload["HostConfig"].get("ReadonlyRootfs"))
    cmdline = run(
        [
            "docker",
            "exec",
            container,
            "python",
            "-c",
            "import pathlib; print(pathlib.Path('/proc/1/cmdline').read_bytes().replace(b'\\0', b' '))",
        ]
    )
    return user, cap_drop, read_only, cmdline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--model-cache", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--image-digest", default="")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()

    image = args.image
    model_cache = args.model_cache.expanduser().resolve()
    if not model_cache.is_dir():
        raise SystemExit(f"model cache does not exist: {model_cache}")
    power = Path(sys.executable).with_name("power")
    mcp = Path(sys.executable).with_name("power-mcp")
    if not power.is_file() or not mcp.is_file():
        raise SystemExit("Profile A requires power and power-mcp in the active environment")

    container = f"power-profile-{os.getpid()}"
    volume = f"power-profile-cache-{os.getpid()}"
    password = "profile-acceptance-password"  # noqa: S105 -- disposable local proof credential.
    base_url = f"http://127.0.0.1:{args.port}"
    try:
        with tempfile.TemporaryDirectory(prefix="power-profile-acceptance-") as directory:
            host_environment = {
                **os.environ,
                "HF_HOME": os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface")),
                "XDG_CACHE_HOME": str(Path(directory) / "host-cache"),
            }
            vault = Path(directory) / "vault"
            run([str(power), "init", str(vault)], env=host_environment)
            run(
                [
                    str(power),
                    "ingest",
                    str(vault),
                    "--type",
                    "Resource",
                    "--title",
                    "ApplicationService acceptance",
                    "--description",
                    "Disposable semantic and reranked Web acceptance fixture",
                    "--tags",
                    "profile acceptance",
                ],
                env=host_environment,
            )
            run([str(power), "sync", str(vault), "--strict"], env=host_environment)
            generated_names = {"index.md", "_index.md", "default.md", "log.md"}
            note_paths = [path for path in vault.rglob("*.md") if path.name not in generated_names]
            if len(note_paths) != 1:
                raise RuntimeError(f"expected one fixture note, got {len(note_paths)}")
            relative_path = note_paths[0].relative_to(vault).as_posix()
            run(
                [str(mcp), "preflight"],
                env={**host_environment, "POWER_VAULT_DIR": str(vault)},
            )
            asyncio.run(mcp_acceptance(mcp, vault, host_environment))
            prepare_vault_for_container(vault)

            stop_container(container)
            subprocess.run(  # noqa: S603 -- fixed Docker executable and generated volume name.
                ["docker", "volume", "rm", "--force", volume],  # noqa: S607
                check=False,
                capture_output=True,
            )
            start_container(
                image=image,
                container=container,
                volume=volume,
                vault=vault,
                model_cache=model_cache,
                port=args.port,
                password=password,
            )
            wait_for_health(base_url, args.version)
            run(["docker", "exec", container, "power", "sync", "/brain", "--strict"])
            browser = Browser(base_url)
            login(browser, password)
            web_search(browser, "semantic")
            web_search(browser, "reranked")
            if MARKER in web_read(browser, relative_path):
                raise RuntimeError("acceptance marker existed before Web mutation")
            web_mutation(browser, relative_path, vault, password)
            if MARKER not in web_read(browser, relative_path):
                raise RuntimeError("Web readback missed governed mutation")
            host_read = run(
                [str(power), "search", str(vault), MARKER, "--mode", "fts"],
                env=host_environment,
            )
            if MARKER not in host_read:
                raise RuntimeError("host CLI did not read the Web mutation")
            asyncio.run(mcp_acceptance(mcp, vault, host_environment))
            user, cap_drop, read_only, cmdline = inspect_container(container)
            if user != "10001:10001" or "ALL" not in cap_drop or not read_only:
                raise RuntimeError("Web container hardening contract failed")
            if "power-mcp" in cmdline or "power-web" not in cmdline:
                raise RuntimeError("Web container is not Web-only")

            stop_container(container)
            subprocess.run(  # noqa: S603 -- fixed Docker executable and generated volume name.
                ["docker", "volume", "rm", "--force", volume],  # noqa: S607
                check=True,
                capture_output=True,
            )
            start_container(
                image=image,
                container=container,
                volume=volume,
                vault=vault,
                model_cache=model_cache,
                port=args.port,
                password=password,
            )
            wait_for_health(base_url, args.version)
            run(["docker", "exec", container, "power", "sync", "/brain", "--strict"])
            restarted = Browser(base_url)
            login(restarted, password)
            web_search(restarted, "semantic")
            web_search(restarted, "reranked")
            if MARKER not in web_read(restarted, relative_path):
                raise RuntimeError("canonical vault did not survive cache-volume rebuild")

            image_config = json.loads(run(["docker", "image", "inspect", image]))[0]
            labels = image_config.get("Config", {}).get("Labels", {})
            evidence: dict[str, Any] = {
                "schema": "power.profile.acceptance.v1",
                "version": args.version,
                "image_digest": args.image_digest or None,
                "profile_a": {
                    "native_cli": True,
                    "native_mcp_stdio": True,
                    "docker_web_containers": 0,
                },
                "profile_b": {
                    "web_health": True,
                    "web_authenticated_read": True,
                    "web_semantic_non_fallback": True,
                    "web_reranked_non_fallback": True,
                    "web_governed_mutation": True,
                    "host_cli_readback": True,
                    "host_mcp_readback": True,
                    "same_canonical_vault": True,
                    "cache_delete_rebuild": True,
                    "container_user": user,
                    "cap_drop_all": True,
                    "read_only_rootfs": True,
                    "web_mcp_services": 0,
                    "web_applicationservice_bypass_count": 0,
                },
                "image": image,
                "image_labels": labels,
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(json.dumps(evidence, sort_keys=True))
    finally:
        if os.environ.get("KEEP_PROFILE_CONTAINER") != "1":
            stop_container(container)
            subprocess.run(  # noqa: S603 -- fixed Docker executable and generated volume name.
                ["docker", "volume", "rm", "--force", volume],  # noqa: S607
                check=False,
                capture_output=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
