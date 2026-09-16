# Contributing to P.O.W.E.R.

Thank you for your interest in contributing to the P.O.W.E.R. Framework!

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/weby-homelab/power-framework.git
   cd power-framework
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install uv==0.11.33
   uv sync --locked --group dev
   ```

3. Run tests to verify setup:
   ```bash
   pytest tests/ -v
   ```

## Architectural Context & North-Star

P.O.W.E.R. is an authoritative local-first control plane for verifiable AI-assisted software
engineering and Linux infrastructure operations. All design decisions and PRs must align with
[ADR-0007: North-Star Control Plane Architecture](docs/adr/0007-power-3.8-north-star-control-plane-architecture.md)
and preserve the two core invariants:
1. `LLM OUTPUT NEVER GRANTS AUTHORITY`
2. `DERIVED STATE MUST NEVER SILENTLY BECOME CANONICAL AUTHORITY`

## Code Standards

- **Python**: 3.13 or 3.14 with explicit type hints
- **Formatting**: Ruff (line-length 100)
- **Types**: MyPy strict mode
- **Style**: Follow PEP 8, preserve contracts, avoid symptom masking
- **Concurrency**: Hard 50% CPU throttling (`os.cpu_count() // 2`) on all indexing/retrieval paths

## Workflow & Gate Discipline

1. Create a focused branch from `main`: `git checkout -b feature/your-feature` (or `docs/*`, `fix/*`).
2. Implement one bounded concern per PR. Never mix architectural gates or refactoring with feature code.
3. Run quality checks locally:
   ```bash
   ruff check src tests scripts
   ruff format --check src tests scripts
   mypy src/power_framework
   pytest tests/ -v
   ```
4. Commit with descriptive messages and mandatory GPG signing (`git commit -S`).
5. Open a Pull Request against `main`.

## Pull Request Process

- All changes land through PRs (no direct pushes to `main`).
- All CI checks must pass (tests, lint, types, doc-drift, packaging, strict docs build).
- At least one review approval required.
- Governance and architectural gates use protected normal merge (`gh pr merge --merge`); squash merge is reserved for atomic single-commit feature branches.

## Maintenance and Backport Policy

- **Main-First Development**: Active development and architectural gates land on `main` first through standard PR and CI validation.
- **Maintenance Lines**: `release/*` branches (e.g. `release/3.7`) contain maintenance backports only; they receive no continued feature development.
- **Provenance-Preserved Backports**: Backports to maintenance lines use `git cherry-pick -x <MAINLINE_COMMIT>` to maintain exact provenance.
- **Mandatory Gates**: PR and automatic CI are mandatory on both `main` and maintenance branches.
- **Architectural Gate Policy**: Detailed gate contracts and governance specifications reside in `docs/plans/POWER_3.8_DEVELOPMENT_PROTOCOL.md`.


## Reporting Issues

- Use GitHub Issues for bugs and feature requests
- Include reproduction steps for bugs
- Specify Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the
GNU General Public License v3.0 (GPLv3), matching `pyproject.toml` and `LICENSE`.
