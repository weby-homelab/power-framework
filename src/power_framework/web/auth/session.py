"""Session and token management for the POWER Web UI."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)


class SessionManager:
    """Safe, signed session token manager with time-to-live."""

    def __init__(self, secret_key: str, salt: str = "power_web_session_salt") -> None:
        self.serializer = URLSafeTimedSerializer(secret_key, salt=salt)

    def create_session(self, user_id: str) -> str:
        """Create signed session token."""
        return self.serializer.dumps({"sub": user_id})

    def verify_session(self, token: str, max_age_seconds: int = 86400) -> str | None:
        """Verify signed session token and return user ID if valid and not expired."""
        verified = self.verify_session_details(token, max_age_seconds=max_age_seconds)
        return verified[0] if verified is not None else None

    def verify_session_details(
        self,
        token: str,
        max_age_seconds: int = 86400,
    ) -> tuple[str, datetime] | None:
        """Verify a session and return its subject plus the token's actual expiry."""
        if not isinstance(token, str) or not token or max_age_seconds <= 0:
            return None
        try:
            loaded = self.serializer.loads(
                token,
                max_age=max_age_seconds,
                return_timestamp=True,
            )
            if not isinstance(loaded, tuple) or len(loaded) != 2:
                return None
            data, issued_at = loaded
            subject = data.get("sub") if isinstance(data, dict) else None
            if (
                not isinstance(subject, str)
                or not subject.strip()
                or len(subject) > 256
                or not isinstance(issued_at, datetime)
            ):
                return None
            return subject, issued_at.astimezone(UTC) + timedelta(seconds=max_age_seconds)
        except SignatureExpired:
            logger.debug("Session expired")
            return None
        except BadSignature:
            logger.warning("Invalid session signature")
            return None
