import pytest
from itsdangerous import URLSafeTimedSerializer

from tests.conftest import make_user
from website import db
from website.services import tokens
from website.services.tokens import (
    load_reset_token,
    load_verify_token,
    make_reset_token,
    make_verify_token,
)


def test_reset_token_roundtrip_and_expiry(app, monkeypatch):
    user = make_user("a@example.com")
    token = make_reset_token(user)
    assert load_reset_token(token) == user
    monkeypatch.setitem(tokens.MAX_AGE, "password-reset", -1)
    assert load_reset_token(token) is None


def test_reset_token_invalid_after_password_change(app):
    user = make_user("a@example.com")
    token = make_reset_token(user)
    user.password = "otro-hash-distinto-1234567"
    db.session.commit()
    assert load_reset_token(token) is None


def test_reset_token_rejects_tampered_and_wrong_salt(app):
    user = make_user("a@example.com")
    token = make_reset_token(user)
    assert load_reset_token(token[:-3] + "xxx") is None
    assert load_reset_token(token[:10]) is None
    assert load_reset_token("") is None
    assert load_reset_token(make_verify_token(user, user.email)) is None


def test_reset_token_malformed_payload_and_missing_user(app):
    ser = URLSafeTimedSerializer("test-secret-key", salt="password-reset")
    assert load_reset_token(ser.dumps("nope")) is None
    assert load_reset_token(ser.dumps({"id": 999, "fp": "x"})) is None
    assert load_reset_token(ser.dumps({"id": "abc"})) is None


def test_verify_token_roundtrip_carries_email(app):
    user = make_user("a@example.com")
    token = make_verify_token(user, "nuevo@example.com")
    assert load_verify_token(token) == (user, "nuevo@example.com")
    assert load_verify_token(make_reset_token(user)) is None
    assert load_verify_token("basura") is None


@pytest.mark.parametrize("salt,age", [("password-reset", 3600), ("email-verify", 172800)])
def test_max_ages(salt, age):
    assert tokens.MAX_AGE[salt] == age
