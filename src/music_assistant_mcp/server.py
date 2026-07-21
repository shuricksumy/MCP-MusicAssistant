"""Entrypoint: builds the FastMCP app, registers tools, wraps it with bearer auth,
and serves it over Streamable HTTP."""

from __future__ import annotations

import logging

import uvicorn
from mcp.server.fastmcp import FastMCP

from .auth import BearerAuthMiddleware
from .config import settings
from .tools import register_all

logging.basicConfig(level=logging.INFO)

mcp = FastMCP("music-assistant")
register_all(mcp)

app = BearerAuthMiddleware(mcp.streamable_http_app())


def main() -> None:
    if not settings.mcp_bearer_token:
        logging.warning("MCP_BEARER_TOKEN is not set - the /mcp endpoint will be unauthenticated")
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
