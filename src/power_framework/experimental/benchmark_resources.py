"""Content-free process and device resource snapshots for diagnostics."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import os
import shutil
import subprocess
import sys
from typing import Any


def _peak_rss_bytes() -> int | None:
    """Return the process peak resident set size when the host exposes it."""
    if os.name == "nt":
        try:

            class _ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("page_fault_count", wintypes.DWORD),
                    ("peak_working_set_size", ctypes.c_size_t),
                    ("working_set_size", ctypes.c_size_t),
                    ("quota_peak_paged_pool_usage", ctypes.c_size_t),
                    ("quota_paged_pool_usage", ctypes.c_size_t),
                    ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
                    ("quota_non_paged_pool_usage", ctypes.c_size_t),
                    ("pagefile_usage", ctypes.c_size_t),
                    ("peak_pagefile_usage", ctypes.c_size_t),
                ]

            counters = _ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            windll = ctypes.windll  # type: ignore[attr-defined]
            process = windll.kernel32.GetCurrentProcess()
            get_info = windll.psapi.GetProcessMemoryInfo
            get_info.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(_ProcessMemoryCounters),
                wintypes.DWORD,
            ]
            get_info.restype = wintypes.BOOL
            if get_info(process, ctypes.byref(counters), counters.cb):
                return int(counters.peak_working_set_size)
        except (AttributeError, OSError, TypeError, ValueError):
            return None
        return None

    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (ImportError, OSError, ValueError):
        return None
    if value <= 0:
        return None
    # Linux and the BSDs report KiB; macOS reports bytes.
    return value if sys.platform == "darwin" else value * 1024


def _nvidia_memory_used_bytes() -> int | None:
    """Return aggregate visible-device memory from optional ``nvidia-smi``."""
    executable = shutil.which("nvidia-smi")
    if executable is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603 - fixed executable and arguments
            [executable, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    values: list[int] = []
    for line in completed.stdout.splitlines():
        try:
            value = int(line.strip())
        except ValueError:
            continue
        if value >= 0:
            values.append(value)
    return sum(values) * 1024 * 1024 if values else None


def resource_snapshot(*, include_gpu: bool = True) -> dict[str, Any]:
    """Return a path-free resource snapshot suitable for a benchmark receipt."""
    gpu_memory = _nvidia_memory_used_bytes() if include_gpu else None
    return {
        "peak_rss_bytes": _peak_rss_bytes(),
        "gpu_memory_used_bytes": gpu_memory,
        "gpu_memory_scope": "all_visible_devices"
        if include_gpu and gpu_memory is not None
        else None,
        "gpu_memory_source": "nvidia-smi" if include_gpu and gpu_memory is not None else None,
    }
