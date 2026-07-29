from mcp.server import MCPServer as FastMCP

from ..ma_client import get_client


async def browse(path: str | None = None) -> object:
    """Browse the provider library hierarchically. Omit `path` to list root providers,
    e.g. path=None -> "spotify://library" -> "spotify://library/playlists".

    No pagination - confirmed against the music-assistant-client source that
    music/browse only takes `path`, unlike the old community server's browse tool.
    """
    client = await get_client()
    return await client.send("music/browse", path=path)


def register(mcp: FastMCP) -> None:
    mcp.tool()(browse)
