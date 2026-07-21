from mcp.server.fastmcp import FastMCP

from ..ma_client import get_client
from ..players import resolve_player


async def group(action: str, players: list[str], target_player: str | None = None) -> dict:
    """Group or ungroup players (e.g. syncing a LedFX visualizer player, or any speaker group).

    action: "join" - add `players` into `target_player`'s group (target defaults to the
            configured default player).
            "leave" - remove `players` from whatever group they're in.
    players: names/substrings of the player(s) to add or remove.
    """
    client = await get_client()
    resolved = [await resolve_player(client, p) for p in players]
    player_ids = [p.player_id for p in resolved]

    if action == "join":
        target = await resolve_player(client, target_player)
        await client.send(
            "players/cmd/group_many", child_player_ids=player_ids, target_player=target.player_id
        )
        return {"action": "join", "players": [p.name for p in resolved], "target": target.name}

    if action == "leave":
        await client.send("players/cmd/ungroup_many", player_ids=player_ids)
        return {"action": "leave", "players": [p.name for p in resolved]}

    raise ValueError("action must be 'join' or 'leave'")


def register(mcp: FastMCP) -> None:
    mcp.tool()(group)
