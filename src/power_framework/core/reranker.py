"""Compatibility import for the optional reranker implementation."""

from __future__ import annotations

import importlib
import sys

_implementation = importlib.import_module("power_framework.experimental.reranker")
sys.modules[__name__] = _implementation
