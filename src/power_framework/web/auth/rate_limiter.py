"""Login rate limiting and lockout mechanism for brute-force protection."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AttemptRecord:
    """Track failed login attempts and lockout timestamps."""

    failure_timestamps: list[float] = field(default_factory=list)
    locked_until: float = 0.0


class LoginRateLimiter:
    """Thread-safe rate limiter and exponential lockout for login attempts."""

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 300,
        base_lockout_seconds: int = 900,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.base_lockout_seconds = base_lockout_seconds
        self._records: dict[str, AttemptRecord] = {}
        self._lock = threading.Lock()

    def _cleanup_old_attempts(self, record: AttemptRecord, now: float) -> None:
        """Remove failure timestamps older than window_seconds."""
        cutoff = now - self.window_seconds
        record.failure_timestamps = [ts for ts in record.failure_timestamps if ts > cutoff]

    def is_locked(self, key: str) -> tuple[bool, int]:
        """
        Check if the key is currently locked out.

        Returns (is_locked, seconds_remaining).
        """
        now = time.time()
        with self._lock:
            record = self._records.get(key)
            if not record:
                return False, 0

            if record.locked_until > now:
                remaining = int(record.locked_until - now) + 1
                return True, remaining

            self._cleanup_old_attempts(record, now)
            return False, 0

    def record_failure(self, key: str) -> tuple[int, bool, int]:
        """
        Record a failed authentication attempt.

        Returns (current_failure_count, is_now_locked, lockout_seconds_remaining).
        """

        now = time.time()
        with self._lock:
            if key not in self._records:
                self._records[key] = AttemptRecord()
            record = self._records[key]

            self._cleanup_old_attempts(record, now)
            record.failure_timestamps.append(now)
            failure_count = len(record.failure_timestamps)

            if failure_count >= self.max_attempts:
                # Exponential backoff based on excess failures
                multiplier = 2 ** max(0, failure_count - self.max_attempts)
                lockout_duration = min(self.base_lockout_seconds * multiplier, 86400)
                record.locked_until = now + lockout_duration
                logger.warning(
                    "Login rate limit exceeded for key=%s: %d failures. Locked for %ds",
                    key,
                    failure_count,
                    lockout_duration,
                )
                return failure_count, True, int(lockout_duration)

            logger.info(
                "Failed login attempt recorded for key=%s (%d/%d)",
                key,
                failure_count,
                self.max_attempts,
            )
            return failure_count, False, 0

    def record_success(self, key: str) -> None:
        """Clear failed attempts upon successful login."""
        with self._lock:
            if key in self._records:
                del self._records[key]

    def reset_all(self) -> None:
        """Clear all records (for testing)."""
        with self._lock:
            self._records.clear()


# Global singleton instance for app-wide login throttling
global_login_rate_limiter = LoginRateLimiter()
