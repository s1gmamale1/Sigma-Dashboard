"""Signed action-approval tokens (X-Sigma-Signoff).

A signoff is a short-lived HS256 JWT bound to a specific action + target
(fingerprint) + single-use nonce. Verification rejects expiry, wrong
action/target (scope binding), bad signature, and replayed nonces.
"""

import pytest

from backend.app.hq.action_auth import (
    ActionAuthError,
    NonceCache,
    mint_signoff,
    target_fingerprint,
    verify_signoff,
)

SECRET = "test-action-secret-please-change-32b"


def test_sign_then_verify_roundtrip() -> None:
    target = {"title": "do a thing"}
    tok = mint_signoff(SECRET, "create_task", target, nonce="n1")
    claims = verify_signoff(SECRET, tok, "create_task", target, nonce_cache=NonceCache())
    assert claims["act"] == "create_task"
    assert claims["nonce"] == "n1"


def test_expired_token_rejected() -> None:
    tok = mint_signoff(SECRET, "create_task", {"x": 1}, ttl_seconds=-1, nonce="n2")
    with pytest.raises(ActionAuthError) as e:
        verify_signoff(SECRET, tok, "create_task", {"x": 1}, nonce_cache=NonceCache())
    assert "expire" in str(e.value).lower()


def test_wrong_action_scope_rejected() -> None:
    tok = mint_signoff(SECRET, "create_task", {"x": 1}, nonce="n3")
    with pytest.raises(ActionAuthError):
        verify_signoff(SECRET, tok, "stop_pane", {"x": 1}, nonce_cache=NonceCache())


def test_wrong_target_rejected() -> None:
    tok = mint_signoff(SECRET, "create_task", {"title": "A"}, nonce="n4")
    with pytest.raises(ActionAuthError):
        verify_signoff(SECRET, tok, "create_task", {"title": "B"}, nonce_cache=NonceCache())


def test_bad_signature_rejected() -> None:
    tok = mint_signoff(SECRET, "create_task", {"x": 1}, nonce="n5")
    with pytest.raises(ActionAuthError):
        verify_signoff("a-different-secret-of-the-right-len!!", tok, "create_task", {"x": 1}, nonce_cache=NonceCache())


def test_replayed_nonce_rejected() -> None:
    cache = NonceCache()
    target = {"x": 1}
    tok = mint_signoff(SECRET, "create_task", target, nonce="n6")
    verify_signoff(SECRET, tok, "create_task", target, nonce_cache=cache)  # first use ok
    tok2 = mint_signoff(SECRET, "create_task", target, nonce="n6")  # same nonce
    with pytest.raises(ActionAuthError) as e:
        verify_signoff(SECRET, tok2, "create_task", target, nonce_cache=cache)
    assert "nonce" in str(e.value).lower()


def test_garbage_token_rejected() -> None:
    with pytest.raises(ActionAuthError):
        verify_signoff(SECRET, "not-a-jwt", "create_task", {}, nonce_cache=NonceCache())


def test_empty_secret_always_rejects() -> None:
    # No action secret configured => signing/verification must be impossible, not open.
    with pytest.raises(ActionAuthError):
        verify_signoff("", "anything", "create_task", {}, nonce_cache=NonceCache())


def test_fingerprint_is_order_independent() -> None:
    assert target_fingerprint({"a": 1, "b": 2}) == target_fingerprint({"b": 2, "a": 1})
    assert target_fingerprint({"a": 1}) != target_fingerprint({"a": 2})
