"""Static shared-secret bearer auth for the HTTP-served MCP endpoint.

A single long-lived token (MCP_BEARER_TOKEN) is all n8n's MCP Client HTTP node needs -
no OAuth flow required, so this is a plain ASGI middleware rather than the SDK's
OAuth-oriented auth provider machinery.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from .config import settings


class BearerAuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not settings.mcp_bearer_token:
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        auth_header = headers.get(b"authorization", b"").decode()
        expected = f"Bearer {settings.mcp_bearer_token}"

        if auth_header != expected:
            response_body = b'{"error": "unauthorized"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": response_body})
            return

        await self.app(scope, receive, send)
