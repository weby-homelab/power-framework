"""Unit tests for SessionManager and CSRF token generation/verification."""

from __future__ import annotations

from power_framework.web.auth.csrf import generate_csrf_token, verify_csrf_token
from power_framework.web.auth.session import SessionManager


def test_session_manager_lifecycle() -> None:
    """Test session token creation and verification."""
    mgr = SessionManager(secret_key="test_signing_key_12345")
    raw_session = mgr.create_session("user_admin")
    assert raw_session is not None

    user = mgr.verify_session(raw_session, max_age_seconds=60)
    assert user == "user_admin"


def test_session_manager_tamper_and_expiry() -> None:
    """Ensure tampered or expired tokens fail to verify."""
    mgr = SessionManager(secret_key="test_signing_key_12345")
    raw_session = mgr.create_session("user_admin")

    # Tampered token
    tampered = raw_session + "xyz"
    assert mgr.verify_session(tampered) is None

    # Expired token with negative max age
    assert mgr.verify_session(raw_session, max_age_seconds=-1) is None


def test_csrf_token_verification() -> None:
    """Test CSRF token generation and validation."""
    csrf_key = "csrf_sign_key_123"
    session_id = "sess_987"

    csrf_val = generate_csrf_token(csrf_key, session_id)
    assert csrf_val is not None
    assert verify_csrf_token(csrf_key, session_id, csrf_val) is True

    # Tampered token or wrong session
    assert verify_csrf_token(csrf_key, "wrong_session", csrf_val) is False
    assert verify_csrf_token(csrf_key, session_id, csrf_val + "bad") is False
