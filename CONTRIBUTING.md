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

## Code Standards

- **Python**: 3.13 or 3.14 with type hints
- **Formatting**: Ruff (line-length 100)
- **Types**: MyPy strict mode
- **Style**: Follow PEP 8, use existing patterns

## Workflow

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make changes with tests
3. Run quality checks:
   ```bash
   ruff check src tests scripts
   ruff format --check src tests scripts
   mypy src/power_framework
   pytest tests/ -v
   ```
4. Commit with a descriptive message (GPG-signed preferred)
5. Open a Pull Request

## Pull Request Process

- All changes go through PRs (no direct pushes to `main`)
- CI must pass (tests, lint, types)
- At least one review approval required
- Squash merge preferred

## Reporting Issues

- Use GitHub Issues for bugs and feature requests
- Include reproduction steps for bugs
- Specify Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the
GNU General Public License v3.0 (GPLv3), matching `pyproject.toml` and `LICENSE`.
