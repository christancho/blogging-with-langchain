import httpx

from api.mcp_server import build_mcp


async def test_mcp_accepts_public_host_header():
    """Behind a proxy/tunnel the Host header is the public hostname, not localhost.

    FastMCP's default DNS-rebinding protection answers 421 for any non-localhost
    Host; build_mcp must not leave it on.
    """
    mcp = build_mcp(session_factory=None)
    app = mcp.streamable_http_app()
    init = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "1"}},
    }
    async with mcp.session_manager.run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://blog.example.com"
        ) as c:
            r = await c.post("/mcp", json=init, headers={"Accept": "application/json, text/event-stream"})
    assert r.status_code == 200
