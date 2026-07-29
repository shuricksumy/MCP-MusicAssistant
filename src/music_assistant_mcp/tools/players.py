from mcp.server import MCPServer as FastMCP

from .. import players as players_logic
from ..ma_client import get_client


def _player_to_dict(p: players_logic.Player) -> dict:
    return {
        "player_id": p.player_id,
        "name": p.name,
        "powered": p.powered,
        "volume_level": p.volume_level,
    }


async def list_players() -> list[dict]:
    """List every Music Assistant player with id, name, power state and volume.

    Most other tools resolve the player themselves (by name, or the configured
    default) - only call this if the user explicitly asks what players exist, or
    a player name didn't match anything and you need to show what's available.
    """
    client = await get_client()
    players = await players_logic.list_players(client)
    return [_player_to_dict(p) for p in players]


def register(mcp: FastMCP) -> None:
    mcp.tool()(list_players)
