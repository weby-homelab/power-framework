"""Compatibility import for the optional graph extraction implementation."""

from __future__ import annotations

import importlib
import sys

_implementation = importlib.import_module("power_framework.experimental.graph_extraction")
sys.modules[__name__] = _implementation
