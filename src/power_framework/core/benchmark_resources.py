"""Compatibility import for optional benchmark resource probes."""

from __future__ import annotations

import importlib
import sys

_implementation = importlib.import_module("power_framework.experimental.benchmark_resources")
sys.modules[__name__] = _implementation
