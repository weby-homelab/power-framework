# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.4.x   | :white_check_mark: |
| < 1.4   | :x:                |

## Reporting a Vulnerability

**Please DO NOT create a public issue for security vulnerabilities.**

Instead, report vulnerabilities via email:

📧 **rekvizitor.ua@gmail.com**

Include as much detail as possible:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Response Timeline

| Stage          | Timeframe |
| -------------- | --------- |
| Acknowledgment | 48 hours  |
| Assessment     | 7 days    |

## Security Measures

The P.O.W.E.R. framework implements the following security measures:

- **Path traversal protection** — all vault paths are validated through `validate_vault_path` to prevent directory traversal attacks
- **Safe YAML parsing** — `yaml.safe_load` is used exclusively to prevent arbitrary code execution via YAML deserialization
- **Strict input validation** — Pydantic v2 models with strict validation ensure all inputs conform to expected schemas
- **Dependency auditing** — `pip-audit` runs in CI to detect known vulnerabilities in project dependencies
