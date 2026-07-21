from mcp.server.fastmcp import FastMCP

from ..ma_client import get_client
from ..players import resolve_player


async def volume(
    player: str | None = None,
    level: int | None = None,
    adjust: str | None = None,
    mute: bool | None = None,
    group: bool = False,
) -> dict:
    """Set volume. Provide exactly one of level (0-100), adjust ("up"/"down"), mute (true/false).

    group: apply to every player in the group (only valid with level/adjust, not mute).
    """
    client = await get_client()
    resolved_player = await resolve_player(client, player)

    provided = [v for v in (level, adjust, mute) if v is not None]
    if len(provided) != 1:
        raise ValueError("Provide exactly one of: level, adjust, mute")

    if mute is not None:
        if group:
            raise ValueError("group=true is not supported with mute")
        await client.send("players/cmd/volume_mute", player_id=resolved_player.player_id, muted=mute)
        return {"player": resolved_player.name, "mute": mute}

    if level is not None:
        command = "group_volume" if group else "volume_set"
        await client.send(
            f"players/cmd/{command}", player_id=resolved_player.player_id, volume_level=level
        )
        return {"player": resolved_player.name, "level": level, "group": group}

    if adjust not in ("up", "down"):
        raise ValueError("adjust must be 'up' or 'down'")
    command = f"{'group_' if group else ''}volume_{adjust}"
    await client.send(f"players/cmd/{command}", player_id=resolved_player.player_id)
    return {"player": resolved_player.name, "adjust": adjust, "group": group}


def register(mcp: FastMCP) -> None:
    mcp.tool()(volume)
