import os

import jwt
from jwt import PyJWKClient

from mcp.server.auth.provider import TokenVerifier, AccessToken
from mcp.server.auth.settings import AuthSettings


class JwksTokenVerifier(TokenVerifier):
    """Verify a provider-issued JWT against the provider's JWKS.

    Validates signature (RS256), issuer, and audience. Returns an AccessToken
    on success or None on any failure (the MCP SDK turns None into a 401).
    """

    def __init__(self, jwks_url: str, issuer: str, audience: str):
        self.jwks_client = PyJWKClient(jwks_url)
        self.issuer = issuer
        self.audience = audience

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
            )
        except Exception as e:  # noqa: BLE001 — must stay visible per repo rule
            print(f"[mcp-auth] token verification failed: {e}")
            return None

        scope = claims.get("scope", "")
        return AccessToken(
            token=token,
            client_id=claims.get("client_id", claims.get("azp", "unknown")),
            scopes=scope.split() if scope else [],
            expires_at=claims.get("exp"),
            subject=claims.get("sub"),
            claims=claims,
        )


def build_token_verifier() -> JwksTokenVerifier | None:
    """Build the verifier from env, or None if OAuth is not configured."""
    jwks_url = os.environ.get("OAUTH_JWKS_URL")
    issuer = os.environ.get("OAUTH_ISSUER")
    audience = os.environ.get("OAUTH_AUDIENCE")
    if not (jwks_url and issuer and audience):
        print("[mcp-auth] OAuth env not fully set — MCP server will run UNAUTHENTICATED")
        return None
    return JwksTokenVerifier(jwks_url, issuer, audience)


def build_auth_settings() -> AuthSettings | None:
    """Build AuthSettings (advertised discovery metadata) from env, or None."""
    issuer = os.environ.get("OAUTH_ISSUER")
    resource = os.environ.get("MCP_RESOURCE_URL")
    if not (issuer and resource):
        return None
    return AuthSettings(
        issuer_url=issuer,
        resource_server_url=resource,
        required_scopes=[],
    )
