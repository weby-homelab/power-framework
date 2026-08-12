"""Compatibility import for the optional relation-suggestion implementation."""

from __future__ import annotations

import importlib
import sys

_implementation = importlib.import_module("power_framework.experimental.relations")
sys.modules[__name__] = _implementation
