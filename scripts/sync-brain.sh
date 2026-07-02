#!/bin/bash
# P.O.W.E.R. Brain Auto-Sync Script
# Designed to run via cron every 5 minutes to sync vault changes to GitHub.
#
# Cron setup:
#   */5 * * * * /path/to/sync-brain.sh >> /var/log/power-sync.log 2>&1
#
# Environment variables (set in .env or export before running):
#   POWER_VAULT_DIR  - Path to the Obsidian vault (required)
#   POWER_REPO_DIR   - Path to the git repository (defaults to POWER_VAULT_DIR)
#   GIT_USER_NAME    - Git committer name (required for cron)
#   GIT_USER_EMAIL   - Git committer email (required for cron)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_DIR="${POWER_VAULT_DIR:-}"
REPO_DIR="${POWER_REPO_DIR:-$VAULT_DIR}"
DATE_STR=$(date +"%Y-%m-%d %H:%M:%S")

log() {
    echo "[${DATE_STR}] $*"
}

# 1. Validate environment
if [ -z "$VAULT_DIR" ]; then
    log "ERROR: POWER_VAULT_DIR is not set. Exiting."
    exit 1
fi

if [ ! -d "$VAULT_DIR" ]; then
    log "ERROR: Vault directory does not exist: ${VAULT_DIR}"
    exit 1
fi

# 2. Load .env if present
ENV_FILE="${REPO_DIR}/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
    log "Loaded environment from ${ENV_FILE}"
fi

# 3. Configure git identity (required for cron)
if [ -n "${GIT_USER_NAME:-}" ] && [ -n "${GIT_USER_EMAIL:-}" ]; then
    git -C "$REPO_DIR" config user.name "$GIT_USER_NAME"
    git -C "$REPO_DIR" config user.email "$GIT_USER_EMAIL"
fi

# 4. Check for changes
cd "$REPO_DIR"
if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    log "No changes detected. Skipping sync."
    exit 0
fi

# 5. Stage and commit changes
CHANGED_FILES=$(git status --porcelain | wc -l)
log "Detected ${CHANGED_FILES} changed file(s). Staging..."

git add -A

COMMIT_MSG="auto-sync: ${DATE_STR} (${CHANGED_FILES} file(s) changed)"

# 6. Sign commit if GPG key is available
if [ -n "${GPG_SIGNING_KEY:-}" ]; then
    git -C "$REPO_DIR" config user.signingkey "$GPG_SIGNING_KEY"
    git commit -S -m "$COMMIT_MSG"
else
    git commit -m "$COMMIT_MSG"
fi

log "Committed: ${COMMIT_MSG}"

# 7. Push to remote
BRANCH=$(git symbolic-ref --short HEAD)
if git push origin "$BRANCH" 2>/dev/null; then
    log "Pushed to origin/${BRANCH} successfully."
else
    log "WARNING: Push failed. Changes are committed locally but not synced."
    exit 1
fi

log "Sync complete."
