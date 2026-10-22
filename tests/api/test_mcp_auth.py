import time
import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from api.mcp_auth import (
    CloudflareAccessMiddleware,
    CloudflareAccessVerifier,
    build_cloudflare_access_verifier,
    require_auth_config_or_warn,
)

TEAM = "https://myteam.cloudflareaccess.com"
AUD = "aud-tag-123"


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
    # Shape of a Cloudflare Access application token: aud is a list of AUD tags.
    payload = {
        "iss": TEAM,
        "aud": [AUD],
        "sub": "user-1",
        "email": "me@example.com",
        "exp": int(time.time()) + 3600,
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
    return CloudflareAccessVerifier(team_domain=TEAM, audience=AUD)


def test_valid_token_accepted(verifier, rsa_keypair):
    priv_pem, _ = rsa_keypair
    claims = verifier.verify(_make_token(priv_pem))
    assert claims is not None
    assert claims["email"] == "me@example.com"


def test_expired_token_rejected(verifier, rsa_keypair):
    priv_pem, _ = rsa_keypair
    assert verifier.verify(_make_token(priv_pem, exp=int(time.time()) - 10)) is None


def test_wrong_issuer_rejected(verifier, rsa_keypair):
    priv_pem, _ = rsa_keypair
    assert verifier.verify(_make_token(priv_pem, iss="https://evil.cloudflareaccess.com")) is None


def test_wrong_audience_rejected(verifier, rsa_keypair):
    priv_pem, _ = rsa_keypair
    assert verifier.verify(_make_token(priv_pem, aud=["some-other-app"])) is None


def test_bad_signature_rejected(verifier):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    assert verifier.verify(_make_token(other_pem)) is None


def test_team_domain_without_scheme_is_normalized():
    v = CloudflareAccessVerifier(team_domain="myteam.cloudflareaccess.com/", audience=AUD)
    assert v.issuer == TEAM
    assert v.jwks_client.uri == f"{TEAM}/cdn-cgi/access/certs"


def test_build_verifier_from_env(monkeypatch):
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", TEAM)
    monkeypatch.setenv("CF_ACCESS_AUD", AUD)
    v = build_cloudflare_access_verifier()
    assert isinstance(v, CloudflareAccessVerifier)
    assert v.audience == AUD


@pytest.mark.parametrize("missing", ["CF_ACCESS_TEAM_DOMAIN", "CF_ACCESS_AUD"])
def test_build_verifier_none_when_unconfigured(monkeypatch, missing):
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", TEAM)
    monkeypatch.setenv("CF_ACCESS_AUD", AUD)
    monkeypatch.delenv(missing)
    assert build_cloudflare_access_verifier() is None


def test_require_auth_config_production_raises_when_verifier_missing():
    with pytest.raises(RuntimeError):
        require_auth_config_or_warn("production", None)


def test_require_auth_config_production_ok_when_present():
    require_auth_config_or_warn("production", object())  # should not raise


def test_require_auth_config_development_does_not_raise():
    require_auth_config_or_warn("development", None)  # warns only


def _protected_client(verifier):
    async def ok(request):
        return PlainTextResponse("ok")

    inner = Starlette(routes=[Route("/mcp", ok, methods=["GET", "POST"])])
    app = CloudflareAccessMiddleware(inner, verifier)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://blog.example.com")


async def test_middleware_rejects_missing_assertion(verifier):
    async with _protected_client(verifier) as c:
        r = await c.post("/mcp")
    assert r.status_code == 401


async def test_middleware_rejects_invalid_assertion(verifier, rsa_keypair):
    priv_pem, _ = rsa_keypair
    bad = _make_token(priv_pem, aud=["some-other-app"])
    async with _protected_client(verifier) as c:
        r = await c.post("/mcp", headers={"Cf-Access-Jwt-Assertion": bad})
    assert r.status_code == 401


async def test_middleware_passes_valid_assertion(verifier, rsa_keypair):
    priv_pem, _ = rsa_keypair
    async with _protected_client(verifier) as c:
        r = await c.post("/mcp", headers={"Cf-Access-Jwt-Assertion": _make_token(priv_pem)})
    assert r.status_code == 200
    assert r.text == "ok"
