from mcp.server import MCPServer as FastMCP

from ..ma_client import get_client
from ..players import resolve_player

_ADJUST_ALIASES = {
    "louder": "up",
    "increase": "up",
    "raise": "up",
    "higher": "up",
    "quieter": "down",
    "decrease": "down",
    "lower": "down",
}


async def volume(
    player: str | None = None,
    level: int | None = None,
    adjust: str | None = None,
    mute: bool | None = None,
    group: bool = False,
) -> dict:
    """Set volume. Provide one of level (0-100), adjust ("up"/"down"), mute (true/false).

    group: apply to every player in the group (level/adjust only; ignored for mute).
    If none of level/adjust/mute are given, just reports the current level instead of
    erroring - useful if the caller only wanted to check volume.
    """
    client = await get_client()
    resolved_player = await resolve_player(client, player)

    if level is None and adjust is None and mute is None:
        return {"player": resolved_player.name, "level": resolved_player.volume_level}

    if mute is not None:
        if group:
            await client.send(
                "players/cmd/volume_mute", player_id=resolved_player.player_id, muted=mute
            )
            return {
                "player": resolved_player.name,
                "mute": mute,
                "note": "group mute isn't supported - muted this player only",
            }
        await client.send("players/cmd/volume_mute", player_id=resolved_player.player_id, muted=mute)
        return {"player": resolved_player.name, "mute": mute}

    if level is not None:
        command = "group_volume" if group else "volume_set"
        level = max(0, min(100, level))
        await client.send(
            f"players/cmd/{command}", player_id=resolved_player.player_id, volume_level=level
        )
        return {"player": resolved_player.name, "level": level, "group": group}

    requested_adjust = (adjust or "").strip().lower()
    normalized_adjust = _ADJUST_ALIASES.get(requested_adjust, requested_adjust)
    if normalized_adjust not in ("up", "down"):
        raise ValueError("adjust must be 'up' or 'down'")
    command = f"{'group_' if group else ''}volume_{normalized_adjust}"
    await client.send(f"players/cmd/{command}", player_id=resolved_player.player_id)
    return {"player": resolved_player.name, "adjust": normalized_adjust, "group": group}


def register(mcp: FastMCP) -> None:
    mcp.tool()(volume)
