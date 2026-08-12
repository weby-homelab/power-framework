"""Compatibility import for the optional query-expansion implementation."""

from __future__ import annotations

import importlib
import sys

_implementation = importlib.import_module("power_framework.experimental.query_expansion")
sys.modules[__name__] = _implementation
