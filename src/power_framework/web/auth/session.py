"""Session and token management for the POWER Web UI."""

from __future__ import annotations

import logging

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
        try:
            data = self.serializer.loads(token, max_age=max_age_seconds)
            return str(data.get("sub"))
        except SignatureExpired:
            logger.debug("Session expired")
            return None
        except BadSignature:
            logger.warning("Invalid session signature")
            return None
