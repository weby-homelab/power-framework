# Weby Homelab Agent Instructions

## Startup
- Read `brain/index.md` → `read_sub_index(category)` → specific notes. NEVER glob `**/*.md`
- Follow PAV: Plan (~3 lines) → Act (full code, no placeholders) → Validate (logs/tests)

## Second Brain
- OKF frontmatter required: `type`, `title`, `description`, `timestamp`
- After changes: call `generate_index`, append to `log.md`
- Session logs → `06_Daily_Logs/YYYY-MM-DD_topic.md`

## Safety & Security
- No hardcoded secrets. GPG-sign commits (key 2D49E810C7F2527E, user=weby-homelab)
- Branch → PR → Merge. No direct pushes to main. Cleanup merged branches.
- Fail-closed on missing credentials. Pydantic for API validation.

## Infrastructure
- HTZNR (46.224.186.236) = PROD, PRXMX-01 = Home Core, PRXMX-02 = STAGING
- Tailscale, Docker, NFTables. Use ThreadPoolExecutor, not raw threads.
