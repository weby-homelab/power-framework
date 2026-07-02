#!/bin/bash
# P.O.W.E.R. Skill Installer for AI Agents

set -e

# Target directory is the first argument, defaults to current directory
TARGET_DIR="${1:-$PWD}"
echo "--------------------------------------------------------"
echo "🚀 Installing P.O.W.E.R. Knowledge Management Skill"
echo "📍 Target workspace: $TARGET_DIR"
echo "--------------------------------------------------------"

# 1. Create directories in the target workspace
mkdir -p "$TARGET_DIR/.agents/skills/power/scripts"

# 2. Download/Copy skill files from github (if running via curl) or copy locally (if running from repo)
if [ -f "skills/power/SKILL.md" ]; then
    echo "📦 Copying files locally..."
    cp -r skills/power/* "$TARGET_DIR/.agents/skills/power/"
else
    echo "🌐 Downloading files from GitHub repository..."
    REPO_URL="https://raw.githubusercontent.com/weby-homelab/P.O.W.E.R/main"
    curl -sSL "$REPO_URL/skills/power/SKILL.md" -o "$TARGET_DIR/.agents/skills/power/SKILL.md"
    curl -sSL "$REPO_URL/skills/power/scripts/generate_index.py" -o "$TARGET_DIR/.agents/skills/power/scripts/generate_index.py"
    curl -sSL "$REPO_URL/skills/power/scripts/lint_brain.py" -o "$TARGET_DIR/.agents/skills/power/scripts/lint_brain.py"
fi

# 3. Make scripts executable
chmod +x "$TARGET_DIR/.agents/skills/power/scripts/"*.py

# 4. Try to integrate with OpenCode globally
GLOBAL_SKILLS_DIR="/root/.agents/skills"
if [ -d "$GLOBAL_SKILLS_DIR" ]; then
    echo "🔌 Linking to OpenCode global skills..."
    rm -f "$GLOBAL_SKILLS_DIR/power"
    ln -s "$TARGET_DIR/.agents/skills/power" "$GLOBAL_SKILLS_DIR/power"
    echo "✅ Skill symlinked to OpenCode!"
fi

echo "--------------------------------------------------------"
echo "🎉 P.O.W.E.R. skill successfully installed!"
echo "👉 If using OpenCode, add this path to your opencode.jsonc instructions:"
echo "   \"$TARGET_DIR/.agents/skills/power/SKILL.md\""
echo "--------------------------------------------------------"
