"""Entrypoint: builds the FastMCP app, registers tools, and serves it either over
Streamable HTTP with bearer auth (default - for n8n and other remote/HTTP MCP clients)
or over stdio (MCP_TRANSPORT=stdio - for hosts that spawn the server as a local
subprocess, e.g. `uvx --from git+... music-assistant-mcp`, no auth needed since the
host owns the process's stdio pipes directly)."""

from __future__ import annotations

import logging

import uvicorn
from mcp.server import MCPServer as FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .auth import BearerAuthMiddleware
from .config import settings
from .tools import register_all

logging.basicConfig(level=logging.INFO)

# Sent as part of the MCP `initialize` response and surfaced by most clients regardless
# of whatever system prompt the host does or doesn't configure - matters most for a
# small/local model that needs to be told directly to just call the tool, not asked to
# reason its way there (confirmed: a local 9B model didn't reliably call `play` without
# this).
INSTRUCTIONS = """\
Music Assistant MCP - controls a home audio system. Act immediately, don't ask permission.

- User wants music played, with something specific in mind (song/artist/album/playlist/mood) \
-> call `play` right away with that as the query. Never just describe what you'd play - \
call the tool.
- User wants music but nothing specific ("play something", "surprise me", "random") -> call \
`play_random`, no query needed.
- Never ask which player, source, or provider to use before playing - the tools resolve a \
default player and search online providers automatically. Only mention players/providers if \
a name you were given doesn't match anything (the tool's error tells you what's available).
- Pause/resume/stop/skip/seek -> `control`. Volume -> `volume`. Shuffle/repeat/clear/reorder \
the queue -> `queue`. Move playback to another player -> `transfer`. Group/ungroup players \
(e.g. syncing a visualizer) -> `group`.
- "Enable"/"disable"/"turn on"/"turn off" a visualizer or LED strip (e.g. LedFx) means \
syncing it to whatever is playing, NOT powering it or changing its volume: enable -> `group` \
with action="join", disable -> `group` with action="leave". Pass the name as the user said it; \
`group` picks the right player when several share that name. Only pass `target_player` if the \
music is on a player other than the default.
- After a tool call succeeds, briefly confirm what's actually playing using its response - \
don't just say "done".
"""

mcp = FastMCP("music-assistant", instructions=INSTRUCTIONS)
register_all(mcp)

# The SDK auto-enables its own DNS-rebinding Host-header check whenever the server is
# constructed/served without an explicit host= override, allow-listing only
# 127.0.0.1/localhost/::1 - confirmed live (against both mcp 1.29.0 and 2.0.0) that this
# silently 421s every request from a real client reaching this server over its LAN IP,
# which is the whole point of running it (n8n etc. on the same network, not localhost).
# Bearer-token auth (BearerAuthMiddleware, below) is this server's actual security
# boundary, so the redundant Host-header check is disabled explicitly rather than left
# to trigger by accident.
app = BearerAuthMiddleware(
    mcp.streamable_http_app(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
    )
)


def main() -> None:
    if settings.mcp_transport == "stdio":
        mcp.run(transport="stdio")
        return

    if not settings.mcp_bearer_token:
        logging.warning("MCP_BEARER_TOKEN is not set - the /mcp endpoint will be unauthenticated")
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
