from mcp.server import MCPServer as FastMCP

from . import browse, group, playback, players, providers, queue, search, transfer, volume

_MODULES = (players, providers, playback, volume, queue, transfer, browse, group, search)


def register_all(mcp: FastMCP) -> None:
    for module in _MODULES:
        module.register(mcp)
