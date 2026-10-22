import asyncio
import json
import logging
import os

import jwt
from jwt import PyJWKClient

_log = logging.getLogger("api.mcp_auth")

# Header Cloudflare Access adds to every request it lets through to the origin.
ACCESS_JWT_HEADER = b"cf-access-jwt-assertion"


class CloudflareAccessVerifier:
    """Verify the Cloudflare Access application token sent to the origin.

    Cloudflare Access (with Managed OAuth) owns login and token issuance for MCP
    clients; on each request it forwards a signed JWT in `Cf-Access-Jwt-Assertion`.
    Validates its signature (RS256, keys from the team's certs endpoint), issuer
    (the team domain), and audience (the Access application's AUD tag).
    """

    def __init__(self, team_domain: str, audience: str):
        team = team_domain.strip().rstrip("/")
        if not team.startswith("https://"):
            team = f"https://{team}"
        self.issuer = team
        self.audience = audience
        self.jwks_client = PyJWKClient(f"{team}/cdn-cgi/access/certs")

    def verify(self, token: str) -> dict | None:
        """Return the token's claims if valid, or None on any failure.

        Args:
            token: Raw value of the Cf-Access-Jwt-Assertion header.

        Returns:
            Decoded claims dict, or None if the token is invalid.
        """
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
            )
        except Exception as e:  # noqa: BLE001 — must stay visible per repo rule
            print(f"[mcp-auth] Cloudflare Access token verification failed: {e}")
            return None


class CloudflareAccessMiddleware:
    """ASGI middleware that rejects HTTP requests lacking a valid Access JWT.

    Cloudflare Access already blocks unauthenticated traffic at the edge; this is
    the origin-side check so a request that reaches the app without passing
    through Access (misrouted tunnel, exposed port) is still refused.
    """

    def __init__(self, app, verifier: CloudflareAccessVerifier):
        self.app = app
        self.verifier = verifier

    async def __call__(self, scope, receive, send):
        """Verify the Access JWT, then delegate to the wrapped app or answer 401."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = next(
            (v.decode("latin-1") for k, v in scope["headers"] if k == ACCESS_JWT_HEADER),
            None,
        )
        if token is None:
            print(f"[mcp-auth] rejected {scope['path']}: missing Cf-Access-Jwt-Assertion header")
        elif await asyncio.to_thread(self.verifier.verify, token) is not None:
            await self.app(scope, receive, send)
            return

        body = json.dumps({"error": "unauthorized"}).encode()
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})


def build_cloudflare_access_verifier() -> CloudflareAccessVerifier | None:
    """Build the verifier from CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD, or None if unset.

    Returns:
        A CloudflareAccessVerifier, or None when either variable is missing.
    """
    team_domain = os.environ.get("CF_ACCESS_TEAM_DOMAIN")
    audience = os.environ.get("CF_ACCESS_AUD")
    if not (team_domain and audience):
        print("[mcp-auth] CF_ACCESS_TEAM_DOMAIN/CF_ACCESS_AUD not set — MCP server will run UNAUTHENTICATED")
        return None
    return CloudflareAccessVerifier(team_domain, audience)


def require_auth_config_or_warn(env, verifier) -> None:
    """Enforce Cloudflare Access config at startup.

    In production ('production'), raise RuntimeError if the verifier is missing,
    so a misconfigured deploy fails closed instead of serving /mcp
    unauthenticated. In any other env, log a loud warning but allow the server
    to run unauthenticated (convenient for local/dev/test).

    Args:
        env: Value of the ENV environment variable.
        verifier: Result of build_cloudflare_access_verifier().
    """
    if verifier is not None:
        return
    if env == "production":
        _log.critical("MCP Cloudflare Access auth is not configured in production — refusing to start.")
        raise RuntimeError(
            "MCP auth env incomplete in production: set CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD."
        )
    _log.warning("MCP server running UNAUTHENTICATED — Cloudflare Access env not set (fine for local/dev).")
