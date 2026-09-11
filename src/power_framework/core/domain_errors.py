"""Shared domain-policy exception type."""

from __future__ import annotations


class DomainConfigError(ValueError):
    """Raised when a domain registry or policy cannot be trusted."""
