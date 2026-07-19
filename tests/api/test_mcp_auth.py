import time
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from api.mcp_auth import JwksTokenVerifier


@pytest.fixture
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv_pem, pub_pem


def _make_token(priv_pem, **overrides):
    payload = {
        "iss": "https://issuer.test",
        "aud": "https://mcp.test",
        "sub": "user-1",
        "exp": int(time.time()) + 3600,
        "scope": "blog:generate",
        **overrides,
    }
    return jwt.encode(payload, priv_pem, algorithm="RS256")


class _FakeSigningKey:
    def __init__(self, key_pem):
        self.key = key_pem


@pytest.fixture
def verifier(monkeypatch, rsa_keypair):
    _, pub_pem = rsa_keypair
    from jwt import PyJWKClient
    monkeypatch.setattr(
        PyJWKClient,
        "get_signing_key_from_jwt",
        lambda self, token: _FakeSigningKey(pub_pem),
    )
    return JwksTokenVerifier(
        jwks_url="https://issuer.test/.well-known/jwks.json",
        issuer="https://issuer.test",
        audience="https://mcp.test",
    )


async def test_valid_token_accepted(verifier, rsa_keypair):
    priv_pem, _ = rsa_keypair
    token = _make_token(priv_pem)
    result = await verifier.verify_token(token)
    assert result is not None
    assert result.subject == "user-1"
    assert "blog:generate" in result.scopes


async def test_expired_token_rejected(verifier, rsa_keypair):
    priv_pem, _ = rsa_keypair
    token = _make_token(priv_pem, exp=int(time.time()) - 10)
    assert await verifier.verify_token(token) is None


async def test_wrong_issuer_rejected(verifier, rsa_keypair):
    priv_pem, _ = rsa_keypair
    token = _make_token(priv_pem, iss="https://evil.test")
    assert await verifier.verify_token(token) is None


async def test_wrong_audience_rejected(verifier, rsa_keypair):
    priv_pem, _ = rsa_keypair
    token = _make_token(priv_pem, aud="https://other.test")
    assert await verifier.verify_token(token) is None


async def test_bad_signature_rejected(verifier):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    token = _make_token(other_pem)  # signed by a key the verifier won't accept
    assert await verifier.verify_token(token) is None
