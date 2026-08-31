# Informational: install P.O.W.E.R. 3.7.10 on Windows 11 25H2

> **Not a supported `v3.7.10` platform.** Windows support is deferred
> indefinitely and has no scheduled release target. The commands below are
> informational and must not be presented as Windows compatibility or release
> certification for the 3.7.10 Linux release boundary.

This guide installs P.O.W.E.R. `v3.7.10` in an isolated virtual environment,
creates a clean vault, verifies the CLI, and configures an MCP client. It uses
PowerShell syntax throughout.

> **Release artifact:** after publication, use only the signed `v3.7.10` tag and
> immutable wheel from the [GitHub release page](https://github.com/weby-homelab/power-framework/releases/tag/v3.7.10).
> Physical Windows evidence remains a separate target-host gate; see the
> [platform support matrix](support-matrix.md).

## Support and evidence boundary

- P.O.W.E.R. requires Python 3.13 or 3.14.
- Windows 11 25H2 is an official Windows 11 release (OS build family `26200`).
- ONNX Runtime supports Windows 11, and its Windows builds require the current
  Microsoft Visual C++ runtime.
- P.O.W.E.R. `v3.7.10` includes an automated cross-platform regression for the
  Windows rename-overwrite behavior.
- Physical Windows 11 25H2 validation was completed on 2026-08-08 for follow-up
  revision `4e5b2b9`; see the [validation report](tests/windows-11-25h2-validation.md).
  This validates the follow-up source/build and does not move or reissue any
  immutable historical release artifacts.

Official prerequisites:

- [Windows 11 release information](https://learn.microsoft.com/windows/release-health/windows11-release-information)
- [Python for Windows](https://www.python.org/downloads/windows/)
- [Python virtual-environment guidance](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/)
- [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist)
- [ONNX Runtime installation requirements](https://onnxruntime.ai/docs/install/)

## 1. Confirm Windows and architecture

Open Windows Terminal with a PowerShell tab. Administrator privileges are not
required for the per-user installation in this guide.

```powershell
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber, OsArchitecture
[System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
```

For Windows 11 25H2, `OsBuildNumber` should begin with `26200`. P.O.W.E.R. uses
CPU ONNX Runtime; no CUDA toolkit is required.

## 2. Install prerequisites

Install a 64-bit CPython release from python.org. During setup, enable the
Python launcher and `PATH` options offered by the installer. Python 3.13 is a
conservative recommended choice; Python 3.13 or 3.14 satisfy the current package
contract.

Install the current Microsoft Visual C++ 2015–2022 Redistributable matching the
host architecture. Git is optional for the release-wheel path below, but is
required for a source or editable installation:

```powershell
winget install --id Git.Git -e --source winget
```

Close and reopen Windows Terminal after installing prerequisites, then verify:

```powershell
py --version
py -m pip --version
git --version
```

If `git` is not installed because you will use only the release wheel, the
`git --version` check may be skipped.

## 3. Create the isolated runtime

Use explicit paths so P.O.W.E.R. works without activating a PowerShell script
or changing the execution policy:

```powershell
$PowerHome = Join-Path $env:LOCALAPPDATA "POWER"
$VenvDir = Join-Path $PowerHome ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$PowerExe = Join-Path $VenvDir "Scripts\power.exe"
$McpExe = Join-Path $VenvDir "Scripts\power-mcp.exe"

New-Item -ItemType Directory -Force -Path $PowerHome | Out-Null
py -m venv $VenvDir
& $VenvPython -m pip install --upgrade pip
```

Verify that the virtual environment, not the global interpreter, is selected:

```powershell
& $VenvPython -c "import sys; print(sys.version); print(sys.executable); print(sys.prefix != sys.base_prefix)"
```

The last line must be `True`, and the executable path must end in
`POWER\.venv\Scripts\python.exe`.

## 4. Install the immutable release

The release wheel avoids Git and pins the P.O.W.E.R. source version. Its Python
dependencies are still resolved from the configured Python package index.

```powershell
$ReleaseWheel = "https://github.com/weby-homelab/power-framework/releases/download/v3.7.10/power_framework-3.7.10-py3-none-any.whl"
& $VenvPython -m pip install $ReleaseWheel
if ($LASTEXITCODE -ne 0) { throw "P.O.W.E.R. installation failed" }
```

Verify the executable, distribution metadata, and lean FTS import:

```powershell
& $PowerExe --version
& $VenvPython -c "from importlib.metadata import version; print(version('power-framework'))"
& $VenvPython -c "import power_framework; print('lean FTS import: OK')"
if ($LASTEXITCODE -ne 0) { throw "P.O.W.E.R. import verification failed" }
```

Both version checks must report `3.7.10`, and the import check must print
`lean FTS import: OK`. The official agent-server contract installs the explicit
`[mcp]` extra before configuring MCP, and `[semantic]` only when dense search is
intentionally enabled:

```powershell
$McpRequirement = "power-framework[mcp] @ $ReleaseWheel"
& $VenvPython -m pip install $McpRequirement
```

### Alternative: install from the pinned tag

Use this only when Git is installed:

```powershell
& $VenvPython -m pip install "git+https://github.com/weby-homelab/power-framework.git@v3.7.10"
```

Do not install unpinned `main` when reproducibility matters.

## 5. Create and verify a clean knowledge vault

Choose a new or empty directory. `power init` intentionally refuses a non-empty
directory; use the migration guide for existing knowledge bases.

```powershell
$Vault = Join-Path $env:USERPROFILE "Documents\POWER-Vault"
& $PowerExe init $Vault
if ($LASTEXITCODE -ne 0) { throw "Vault initialization failed" }

& $PowerExe ingest $Vault --type Resource --title "First note" --description "Clean-install acceptance note"
if ($LASTEXITCODE -ne 0) { throw "First note ingestion failed" }

& $PowerExe index $Vault --strict
if ($LASTEXITCODE -ne 0) { throw "Strict index generation failed" }

& $PowerExe lint $Vault
if ($LASTEXITCODE -ne 0) { throw "Vault lint failed" }

& $PowerExe markdown-check $Vault
if ($LASTEXITCODE -ne 0) { throw "Markdown check failed" }
```

An orphan warning for the first unlinked note is informational. The acceptance
gate is exit code `0`, no invalid OKF metadata, and no broken internal links.

Build the lightweight FTS index and prove retrieval without downloading model
assets:

```powershell
& $PowerExe sync $Vault --fts-only
if ($LASTEXITCODE -ne 0) { throw "FTS synchronization failed" }

& $PowerExe search $Vault "acceptance" --mode fts
if ($LASTEXITCODE -ne 0) { throw "FTS search failed" }
```

The result must include `First note`.

## 6. Optional dense and reranked search

Semantic and reranked search require pinned BGE-M3 and reranker model assets.
The first full synchronization can take significant time, network bandwidth,
disk space, and memory:

```powershell
& $PowerExe sync $Vault
if ($LASTEXITCODE -ne 0) { throw "Dense synchronization failed" }

& $PowerExe search $Vault "clean installation" --mode semantic
if ($LASTEXITCODE -ne 0) { throw "Semantic search failed" }
```

Model files are managed by the Hugging Face cache, not by the virtual
environment directory. P.O.W.E.R. validates its pinned model contract and
fails closed when required assets are absent or corrupt. Do not disable
Microsoft Defender or SmartScreen to make a failed download pass; inspect the
error, proxy, available disk space, and security event first.

## 7. Configure an MCP client

Always point the client at the virtual environment's exact `power-mcp.exe`
launcher. The global `py` launcher may select a different interpreter where
P.O.W.E.R. is not installed.

For Claude Desktop, edit
`$env:APPDATA\Claude\claude_desktop_config.json`. Replace `YOUR-NAME` with the
actual Windows user directory, or obtain the exact values with the PowerShell
commands below:

```powershell
$VenvPython
$Vault
```

Example JSON (backslashes must be doubled):

```json
{
  "mcpServers": {
    "power": {
      "command": "C:\\Users\\YOUR-NAME\\AppData\\Local\\POWER\\.venv\\Scripts\\power-mcp.exe",
      "args": [],
      "env": {
        "POWER_VAULT_DIR": "C:\\Users\\YOUR-NAME\\Documents\\POWER-Vault"
      }
    }
  }
}
```

Before restarting the MCP client, validate the configured interpreter and vault:

```powershell
$env:POWER_VAULT_DIR = $Vault
& $McpExe preflight
```

Restart the MCP client after saving its configuration. A long-lived client
does not automatically reload an updated Python environment or JSON file.

## 8. Upgrade, rollback, and uninstall

Upgrade to a specific release by replacing the version in the wheel URL and
running the same install command with `--upgrade`. Verify `power --version`
afterward.

Rollback to the previous stable release, `v3.4.5`:

```powershell
$RollbackWheel = "https://github.com/weby-homelab/power-framework/releases/download/v3.4.5/power_framework-3.4.5-py3-none-any.whl"
& $VenvPython -m pip install --force-reinstall $RollbackWheel
& $PowerExe --version
```

Uninstall the application without touching the vault:

```powershell
& $VenvPython -m pip uninstall power-framework
```

The knowledge vault is ordinary Markdown and remains separate from the Python
runtime. Back it up before deleting either directory.

## Troubleshooting

| Symptom | Resolution |
| --- | --- |
| `py` is not recognized | Re-run the python.org installer with the launcher enabled, reopen Terminal, and verify the Windows App Execution Aliases/PATH configuration. |
| `power` is not recognized | Use the explicit `$PowerExe` path from this guide; no global `PATH` edit is required. |
| `Activate.ps1` is blocked | Activation is optional. Continue using `$VenvPython` and `$PowerExe`. If you choose to change execution policy, review Microsoft's execution-policy guidance and organizational Group Policy first. |
| `DLL load failed` while importing `onnxruntime` | Install or repair the current Visual C++ 2015–2022 Redistributable matching the host architecture, then reopen Terminal. |
| `pip install git+...` fails | Install Git for Windows, or use the release-wheel path, which does not require Git. |
| MCP client reports module not found | Its `command` points to the wrong Python. Use the full `.venv\Scripts\python.exe` path and restart the client. |
| Explicit `POWER_EMBED_DEVICE=cuda` fails with `requested_onnx_provider_not_bound` | This is the fail-closed GPU contract: the session did not bind CUDA. Keep the error, verify the pip `nvidia-*` runtime and `onnxruntime-gpu`, or set `POWER_EMBED_DEVICE=auto` only when CPU fallback is intended. |
| `power init` refuses the directory | The target is not empty. Do not bypass the guard; use a new path or follow the migration guide. |
| Dense sync fails | Keep the failure closed. Check disk space, network/proxy access, the exact model error, and retry; FTS remains available through `sync --fts-only` and `search --mode fts`. |

## Acceptance checklist

- Windows reports version 25H2 / build family `26200`.
- The selected Python is 3.13 or 3.14 and the venv check prints `True`.
- `power --version` and distribution metadata both report `3.7.10`.
- `power_framework` imports successfully and the official agent-server install
  includes the `[mcp]` extra.
- MCP preflight runs with the same interpreter.
- `init`, `ingest`, `index --strict`, `lint`, and `markdown-check` exit `0`.
- FTS sync exits `0` and search returns the acceptance note.
- MCP preflight prints `MCP preflight: OK` using the exact configured Python.
- Dense/reranked capability is claimed only if the optional full sync and
  corresponding search pass on the target Windows host.
