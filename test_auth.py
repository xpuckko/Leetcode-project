from datetime import datetime, timedelta, timezone

import jwt
import pytest

import auth
from auth import create_access_token, decode_access_token


def test_token_roundtrip() -> None:
    token = create_access_token(5)
    assert decode_access_token(token) == 5


def test_token_has_three_parts() -> None:
    token = create_access_token(5)
    assert len(token.split(".")) == 3


def test_payload_contains_sub_and_exp() -> None:
    token = create_access_token(5)
    payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
    assert payload["sub"] == "5"
    assert "exp" in payload


def test_tampered_token_is_rejected() -> None:
    token = create_access_token(5)
    bad = token[:-2] + "xx"
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(bad)


def test_token_signed_with_wrong_key_is_rejected() -> None:
    payload = {
        "sub": "5",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    forged = jwt.encode(payload, "x" *32, algorithm=auth.ALGORITHM)
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged)


def test_expired_token_is_rejected() -> None:
    payload = {
        "sub": "5",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    expired = jwt.encode(payload, auth.SECRET_KEY, algorithm=auth.ALGORITHM)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired)


def test_garbage_string_is_rejected() -> None:
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("not-a-token")