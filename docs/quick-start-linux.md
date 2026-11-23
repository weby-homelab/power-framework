# Quick Start (Linux)

Install POWER from a published release in a private virtual environment and check a new Markdown vault. No root access or Docker is required for the CLI. For the browser interface, complete the native install and follow the [Web container guide for the example release](https://github.com/weby-homelab/power-framework/blob/v3.7.13/deploy/web/README.md).

Use Bash, `gh`, and Python 3.13 or 3.14 with `venv`. The example uses the [published `v3.7.13` assets](https://github.com/weby-homelab/power-framework/releases/tag/v3.7.13). For another release, use its wheel, lock and checksums together.

## Install and verify

```bash
set -euo pipefail
POWER_VERSION=3.7.13
POWER_RELEASE_DIR="$HOME/.cache/power-release-$POWER_VERSION"
mkdir -p "$POWER_RELEASE_DIR"
gh release download "v$POWER_VERSION" --repo weby-homelab/power-framework \
  --pattern "power_framework-${POWER_VERSION}-py3-none-any.whl" \
  --pattern 'power-native-requirements.txt' \
  --pattern 'SHA256SUMS' \
  --dir "$POWER_RELEASE_DIR"
(
  cd "$POWER_RELEASE_DIR"
  for asset in "power_framework-${POWER_VERSION}-py3-none-any.whl" power-native-requirements.txt; do
    awk -v name="$asset" '$2 == name { print; found++ } END { exit (found != 1) }' SHA256SUMS |
      sha256sum --check --strict -
  done
)
python3 -m venv "$POWER_RELEASE_DIR/venv"
POWER_PYTHON="$POWER_RELEASE_DIR/venv/bin/python"
"$POWER_PYTHON" -m pip install --require-hashes \
  -r "$POWER_RELEASE_DIR/power-native-requirements.txt"
"$POWER_PYTHON" -m pip install --no-deps \
  "$POWER_RELEASE_DIR/power_framework-${POWER_VERSION}-py3-none-any.whl"
export PATH="$POWER_RELEASE_DIR/venv/bin:$PATH"
power --version
```

`power --version` should report `3.7.13` for this example.

## Check a new vault

Use a new directory. For an existing collection of notes, use the [migration guide](migration-guide.md) instead.

```bash
power init ~/my-vault
power lint ~/my-vault
power index ~/my-vault
power heal ~/my-vault            # Preview only; does not apply repairs
power markdown-check ~/my-vault
```

Next: [connect an MCP client](mcp-client-onboarding.md) or see the [full installation guide](getting-started.md).
