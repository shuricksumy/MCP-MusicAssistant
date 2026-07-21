"""Entrypoint: builds the FastMCP app, registers tools, and serves it either over
Streamable HTTP with bearer auth (default - for n8n and other remote/HTTP MCP clients)
or over stdio (MCP_TRANSPORT=stdio - for hosts that spawn the server as a local
subprocess, e.g. `uvx --from git+... music-assistant-mcp`, no auth needed since the
host owns the process's stdio pipes directly)."""

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
    if settings.mcp_transport == "stdio":
        mcp.run(transport="stdio")
        return

    if not settings.mcp_bearer_token:
        logging.warning("MCP_BEARER_TOKEN is not set - the /mcp endpoint will be unauthenticated")
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
