# Contributing

## Setup

```bash
git clone https://github.com/weby-homelab/P.O.W.E.R.git
cd P.O.W.E.R
pip install -e ".[dev]"
```

## Running tests

```bash
pytest tests/ -v --tb=short
```

Coverage threshold: **70%**.

## Linting

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/power_framework/
```

## Pre-commit

Install hooks:

```bash
pre-commit install
```

## Making changes

1. Create an issue describing the change
2. Create a branch (`feature/*` or `fix/*`)
3. Make changes with tests
4. GPG-sign your commits
5. Open a pull request

## License

GPLv3 — Built in Ukraine ⚡
