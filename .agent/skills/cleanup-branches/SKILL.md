---
name: cleanup-branches
description: Cleans up obsolete, merged git branches in the local repository and deletes them from GitHub.
---

# 🗑️ Git Branch Cleanup Skill

This skill is designed for automatically cleaning up obsolete and already merged branches from the local environment and remote repository on GitHub.

## 🚀 How to Use

The skill automatically activates when:
1. Work on a Pull Request (PR) or merging changes is complete.
2. A deployment process has been initiated.
3. The user requests deleting extra branches or tidying up the repository.

You can run the cleanup script directly from the terminal:
```bash
/root/geminicli/.agents/skills/cleanup-branches/scripts/cleanup_branches.py
```

The script on its own:
- Checks whether you are in a Git repository.
- Retrieves the `GITHUB_RELEASE_TOKEN` token from the `.env` file.
- Retrieves the repository name and its owner.
- Determines the list of branches that have already been merged into `main` or `master`.
- Deletes these branches on GitHub via the API.
- Runs the `git fetch origin --prune` command to clean up local references.