#!/bin/bash
# P.O.W.E.R. Skill & MCP Server Installer for AI Agents
# Usage:
#   curl -sSL https://raw.githubusercontent.com/weby-homelab/power-framework/main/install.sh | bash
#   curl -sSL https://raw.githubusercontent.com/weby-homelab/power-framework/main/install.sh | bash -s -- /path/to/workspace

set -euo pipefail

# Read version from source if available locally, otherwise use fallback
if [ -f "src/power_framework/core/utils.py" ]; then
    VERSION=$(python3 -c "exec(open('src/power_framework/core/utils.py').read()); print(__version__)" 2>/dev/null || echo "1.5.1")
else
    VERSION="1.5.1"
fi
TARGET_DIR="${1:-$PWD}"
REPO_URL="https://raw.githubusercontent.com/weby-homelab/power-framework/main"

echo "--------------------------------------------------------"
echo "P.O.W.E.R. Framework Installer v${VERSION}"
echo "Target workspace: ${TARGET_DIR}"
echo "--------------------------------------------------------"

# 1. Check prerequisites
check_prerequisites() {
    local missing=0

    if ! command -v python3 &>/dev/null; then
        echo "ERROR: python3 is not installed. Please install Python 3.10+ first."
        missing=1
    else
        local py_version
        py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        local py_major
        py_major=$(echo "$py_version" | cut -d. -f1)
        local py_minor
        py_minor=$(echo "$py_version" | cut -d. -f2)
        if [ "$py_major" -lt 3 ] || ([ "$py_major" -eq 3 ] && [ "$py_minor" -lt 10 ]); then
            echo "ERROR: Python 3.10+ required (found ${py_version})."
            missing=1
        else
            echo "OK: Python ${py_version} found."
        fi
    fi

    if ! command -v curl &>/dev/null && [ ! -f "skills/power/SKILL.md" ]; then
        echo "ERROR: curl is not installed. Required for downloading files."
        missing=1
    else
        echo "OK: curl found."
    fi

    if [ "$missing" -eq 1 ]; then
        echo ""
        echo "Installation aborted. Please install missing prerequisites."
        exit 1
    fi
}

check_prerequisites

# 2. Create directory structure
echo ""
echo "Creating directory structure..."
mkdir -p "${TARGET_DIR}/.agents/skills/power/scripts"
mkdir -p "${TARGET_DIR}/.agents/mcp_servers"
mkdir -p "${TARGET_DIR}/power_core"

# 3. Download or copy files
if [ -f "skills/power/SKILL.md" ]; then
    echo "Copying files locally..."
    # Exclude __pycache__ when copying (use rsync or fallback to find+cp)
    if command -v rsync &>/dev/null; then
        rsync -a --exclude='__pycache__' skills/power/ "${TARGET_DIR}/.agents/skills/power/"
        cp mcp_servers/power_server.py "${TARGET_DIR}/.agents/mcp_servers/"
        rsync -a --exclude='__pycache__' power_core/ "${TARGET_DIR}/power_core/"
    else
        find skills/power/ -not -path '*/__pycache__/*' -type f -exec cp --parents {} "${TARGET_DIR}/.agents/" \;
        cp mcp_servers/power_server.py "${TARGET_DIR}/.agents/mcp_servers/"
        find power_core/ -not -path '*/__pycache__/*' -type f -exec cp --parents {} "${TARGET_DIR}/" \;
    fi
else
    echo "Downloading files from GitHub..."

    local_files=(
        "skills/power/SKILL.md"
        "skills/power/scripts/generate_index.py"
        "skills/power/scripts/lint_brain.py"
        "mcp_servers/power_server.py"
        "power_core/__init__.py"
        "power_core/models.py"
        "power_core/parser.py"
        "power_core/utils.py"
        "power_core/indexer.py"
        "power_core/linter.py"
        "power_core/searcher.py"
    )

    for file in "${local_files[@]}"; do
        echo "  Downloading ${file}..."
        local dest="${TARGET_DIR}/${file}"
        mkdir -p "$(dirname "$dest")"
        if ! curl -sSL "${REPO_URL}/${file}" -o "$dest"; then
            echo "  WARNING: Failed to download ${file}"
        fi
    done
fi

# 4. Make scripts executable
chmod +x "${TARGET_DIR}/.agents/skills/power/scripts/"*.py 2>/dev/null || true
chmod +x "${TARGET_DIR}/.agents/mcp_servers/power_server.py" 2>/dev/null || true

# 5. Install Python dependencies
echo ""
echo "Installing Python dependencies..."
if python3 -m pip install --quiet mcp pydantic pyyaml 2>/dev/null; then
    echo "OK: Dependencies installed."
else
    echo "WARNING: Could not install dependencies automatically."
    echo "Please run: pip install mcp pydantic pyyaml"
fi

# 6. Link to global directories (if they exist)
echo ""
echo "Checking for global integration points..."

HOME_DIR="${HOME:-/root}"

GLOBAL_SKILLS_DIR="${HOME_DIR}/.agents/skills"
if [ -d "$GLOBAL_SKILLS_DIR" ]; then
    echo "Linking to global skills directory..."
    rm -f "${GLOBAL_SKILLS_DIR}/power"
    ln -sf "${TARGET_DIR}/.agents/skills/power" "${GLOBAL_SKILLS_DIR}/power"
    echo "OK: Skill symlinked."
fi

GLOBAL_MCP_DIR="${HOME_DIR}/.config/opencode/mcp_servers"
if [ -d "$GLOBAL_MCP_DIR" ]; then
    echo "Linking to global MCP servers..."
    rm -f "${GLOBAL_MCP_DIR}/power_server.py"
    ln -sf "${TARGET_DIR}/.agents/mcp_servers/power_server.py" "${GLOBAL_MCP_DIR}/power_server.py"
    echo "OK: MCP server symlinked."
fi

# 7. Print configuration instructions
echo ""
echo "--------------------------------------------------------"
echo "P.O.W.E.R. v${VERSION} installed successfully!"
echo "--------------------------------------------------------"
echo ""
echo "To configure your AI agent, add the following:"
echo ""
echo "OpenCode (opencode.jsonc):"
echo "  instructions: [\"${TARGET_DIR}/.agents/skills/power/SKILL.md\"]"
echo ""
echo "  mcp: {"
echo "    \"power\": {"
echo "      \"type\": \"local\","
echo "      \"command\": [\"python3\", \"${TARGET_DIR}/.agents/mcp_servers/power_server.py\"],"
echo "      \"enabled\": true"
echo "    }"
echo "  }"
echo ""
echo "Claude Desktop (claude_desktop_config.json):"
echo "  \"mcpServers\": {"
echo "    \"power\": {"
echo "      \"command\": \"python3\","
echo "      \"args\": [\"${TARGET_DIR}/.agents/mcp_servers/power_server.py\"],"
echo "      \"env\": {"
echo "        \"POWER_VAULT_DIR\": \"/path/to/your/my-vault\""
echo "      }"
echo "    }"
echo "  }"
echo "--------------------------------------------------------"
