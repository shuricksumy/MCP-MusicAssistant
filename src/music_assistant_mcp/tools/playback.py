from mcp.server.fastmcp import FastMCP

from .. import providers as providers_logic
from ..ma_client import get_client
from ..players import resolve_player
from ..search import search_and_pick

_TRANSPORT_COMMANDS = {
    "play": "play",
    "pause": "pause",
    "stop": "stop",
    "toggle": "play_pause",
    "next": "next",
    "previous": "previous",
}


async def play(
    query: str,
    player: str | None = None,
    media_types: list[str] | None = None,
    source: str | None = None,
    scope: str | None = None,
    option: str = "play",
    radio_mode: bool = False,
) -> dict:
    """Search for media and play it on a player - one call, no separate search step.

    player: name/substring (e.g. "kitchen"); omitted -> configured default player.
    media_types: one or more of "playlist", "track", "album", "artist", "radio";
        omitted -> ["playlist"].
    source: name/substring of one specific provider (e.g. "tidal", "spotify",
        "my-nas-share") to force that provider; omitted -> best match is picked
        automatically using the configured provider priority order.
    scope: "online" (streaming providers only, e.g. Spotify/Tidal/Apple - rich
        thematic search), "local" (local/SMB/WebDAV file providers only - literal
        matching), or "all" (default - search everywhere, today's behavior).
        Ignored if `source` is given.
    option: "play" (clear queue and play now, default), "replace", "next", "add".
    radio_mode: start a continuous radio mix seeded from the match (e.g. an artist or
        track) instead of just playing it once.
    """
    client = await get_client()
    resolved_player = await resolve_player(client, player)
    available_providers = await providers_logic.list_providers(client)
    provider_filter = providers_logic.resolve_provider_filter(available_providers, source, scope)

    best, candidates = await search_and_pick(
        client, query, media_types=media_types, source=source, providers=provider_filter
    )
    if best is None:
        raise ValueError(f"No results found for '{query}'" + (f" from {source}" if source else ""))

    await client.send(
        "player_queues/play_media",
        queue_id=resolved_player.player_id,
        media=best.uri,
        option=option,
        radio_mode=radio_mode,
    )
    return {
        "player": resolved_player.name,
        "matched": [c.name for c in candidates[:5]],
        "playing": {"name": best.name, "provider": best.provider, "uri": best.uri},
        "radio_mode": radio_mode,
    }


async def control(
    player: str | None = None,
    command: str = "play",
    seek_seconds: int | None = None,
) -> dict:
    """Playback transport control.

    command: "play" | "pause" | "stop" | "toggle" | "next" | "previous".
    seek_seconds: if given, seeks to that position instead (convert mm:ss to seconds).
    """
    client = await get_client()
    resolved_player = await resolve_player(client, player)

    if seek_seconds is not None:
        await client.send(
            "player_queues/seek", queue_id=resolved_player.player_id, position=seek_seconds
        )
        return {"player": resolved_player.name, "command": "seek", "seek_seconds": seek_seconds}

    ws_command = _TRANSPORT_COMMANDS.get(command)
    if ws_command is None:
        raise ValueError(f"Unknown command '{command}', expected one of {list(_TRANSPORT_COMMANDS)}")

    await client.send(f"player_queues/{ws_command}", queue_id=resolved_player.player_id)
    return {"player": resolved_player.name, "command": command}


def register(mcp: FastMCP) -> None:
    mcp.tool()(play)
    mcp.tool()(control)
