import pytest
from datetime import timedelta
from jose import JWTError


def test_hash_and_verify_password():
    from api.auth import hash_password, verify_password
    hashed = hash_password("mypassword")
    assert hashed != "mypassword"
    assert verify_password("mypassword", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_create_and_decode_token():
    from api.auth import create_token, decode_token
    token = create_token()
    payload = decode_token(token)
    assert payload["sub"] == "user"


def test_expired_token_raises():
    from api.auth import create_token, decode_token
    token = create_token(expires_delta=timedelta(seconds=-1))
    with pytest.raises(JWTError):
        decode_token(token)


def test_invalid_token_raises():
    from api.auth import decode_token
    with pytest.raises(JWTError):
        decode_token("not.a.valid.token")
