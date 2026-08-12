"""Compatibility import for the optional ROT scoring implementation."""

from __future__ import annotations

import importlib
import sys

_implementation = importlib.import_module("power_framework.experimental.rot_scoring")
sys.modules[__name__] = _implementation
