from mcp.server import MCPServer as FastMCP

from ..ma_client import get_client
from ..players import resolve_player


async def transfer(source_player: str, target_player: str) -> dict:
    """Move what's currently playing on `source_player` over to `target_player`."""
    client = await get_client()
    source = await resolve_player(client, source_player)
    target = await resolve_player(client, target_player)
    await client.send(
        "player_queues/transfer", source_queue_id=source.player_id, target_queue_id=target.player_id
    )
    return {"source": source.name, "target": target.name}


def register(mcp: FastMCP) -> None:
    mcp.tool()(transfer)
