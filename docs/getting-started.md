# Getting Started

## Installation

```bash
pip install power-framework
```

Verify the installation:

```bash
power --version
```

## Create a vault

```bash
power init my-vault
cd my-vault
```

This creates the P.A.R.A. directory structure:

```
vault/
├── 00_Inbox/
├── 01_Projects/
├── 02_Areas/
├── 03_Resources/
├── 04_Archive/
├── 05_Templates/
└── 06_Daily_Logs/
```

## Add notes

```bash
power ingest --title "My Note" --type Resource --description "A useful resource"
```

## Run health checks

```bash
power lint .
```

## Auto-heal frontmatter

```bash
power heal .                  # Preview changes (dry run)
power heal . --no-dry-run     # Apply fixes
```

## Check markdown quality

```bash
power markdown-check .
```

## Generate index

```bash
power index .
```

## Search

```bash
power search . "my query"
```

## Run ROT audit with extended scoring

```bash
power rot . --extended
```
