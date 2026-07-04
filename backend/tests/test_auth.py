import pytest
from fastapi import HTTPException

from app import auth


def test_require_api_token_is_noop_when_unset(monkeypatch):
    monkeypatch.setattr(auth.settings, "api_auth_token", "")
    auth.require_api_token(authorization=None)  # must not raise


def test_require_api_token_rejects_missing_header(monkeypatch):
    monkeypatch.setattr(auth.settings, "api_auth_token", "secret123")
    with pytest.raises(HTTPException) as exc:
        auth.require_api_token(authorization=None)
    assert exc.value.status_code == 401


def test_require_api_token_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(auth.settings, "api_auth_token", "secret123")
    with pytest.raises(HTTPException):
        auth.require_api_token(authorization="Bearer wrong")


def test_require_api_token_accepts_correct_bearer(monkeypatch):
    monkeypatch.setattr(auth.settings, "api_auth_token", "secret123")
    auth.require_api_token(authorization="Bearer secret123")  # must not raise


def test_check_ws_token_true_when_unset(monkeypatch):
    monkeypatch.setattr(auth.settings, "api_auth_token", "")
    assert auth.check_ws_token(None) is True
    assert auth.check_ws_token("anything") is True


def test_check_ws_token_requires_match_when_set(monkeypatch):
    monkeypatch.setattr(auth.settings, "api_auth_token", "secret123")
    assert auth.check_ws_token(None) is False
    assert auth.check_ws_token("wrong") is False
    assert auth.check_ws_token("secret123") is True
