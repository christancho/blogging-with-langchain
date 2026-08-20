import time
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from api.mcp_auth import (
    JwksTokenVerifier,
    StaticTokenVerifier,
    build_auth_settings,
    build_token_verifier,
    require_auth_config_or_warn,
)


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


def test_require_auth_config_production_raises_when_verifier_missing():
    with pytest.raises(RuntimeError):
        require_auth_config_or_warn("production", None, object())


def test_require_auth_config_production_raises_when_settings_missing():
    with pytest.raises(RuntimeError):
        require_auth_config_or_warn("production", object(), None)


def test_require_auth_config_production_ok_when_both_present():
    require_auth_config_or_warn("production", object(), object())  # should not raise


def test_require_auth_config_development_does_not_raise():
    require_auth_config_or_warn("development", None, None)  # warns only


async def test_static_token_verifier_accepts_matching_token():
    verifier = StaticTokenVerifier("secret-token")
    result = await verifier.verify_token("secret-token")
    assert result is not None
    assert result.client_id == "static"


async def test_static_token_verifier_rejects_wrong_token():
    verifier = StaticTokenVerifier("secret-token")
    assert await verifier.verify_token("wrong-token") is None


def test_build_token_verifier_prefers_static_token(monkeypatch):
    monkeypatch.setenv("MCP_STATIC_TOKEN", "secret-token")
    monkeypatch.delenv("OAUTH_JWKS_URL", raising=False)
    monkeypatch.delenv("OAUTH_ISSUER", raising=False)
    monkeypatch.delenv("OAUTH_AUDIENCE", raising=False)
    verifier = build_token_verifier()
    assert isinstance(verifier, StaticTokenVerifier)


def test_build_token_verifier_falls_back_to_jwks(monkeypatch):
    monkeypatch.delenv("MCP_STATIC_TOKEN", raising=False)
    monkeypatch.setenv("OAUTH_JWKS_URL", "https://issuer.test/.well-known/jwks.json")
    monkeypatch.setenv("OAUTH_ISSUER", "https://issuer.test")
    monkeypatch.setenv("OAUTH_AUDIENCE", "https://mcp.test")
    verifier = build_token_verifier()
    assert isinstance(verifier, JwksTokenVerifier)


def test_build_token_verifier_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("MCP_STATIC_TOKEN", raising=False)
    monkeypatch.delenv("OAUTH_JWKS_URL", raising=False)
    monkeypatch.delenv("OAUTH_ISSUER", raising=False)
    monkeypatch.delenv("OAUTH_AUDIENCE", raising=False)
    assert build_token_verifier() is None


def test_build_auth_settings_issuer_falls_back_to_resource_url(monkeypatch):
    monkeypatch.delenv("OAUTH_ISSUER", raising=False)
    monkeypatch.setenv("MCP_RESOURCE_URL", "https://blog.test/mcp")
    settings = build_auth_settings()
    assert str(settings.issuer_url) == "https://blog.test/mcp"
    assert str(settings.resource_server_url) == "https://blog.test/mcp"
