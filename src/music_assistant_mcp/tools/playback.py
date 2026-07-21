from mcp.server.fastmcp import FastMCP

from .. import providers as providers_logic
from ..ma_client import get_client
from ..players import resolve_player
from ..search import normalize_media_types, search_and_pick

_TRANSPORT_COMMANDS = {
    "play": "play",
    "pause": "pause",
    "stop": "stop",
    "toggle": "play_pause",
    "next": "next",
    "previous": "previous",
}
# Lenient synonyms so a slightly-off agent guess still does the right thing instead of
# hard-failing (see module note in tools/queue.py for the same philosophy elsewhere).
_COMMAND_ALIASES = {
    "resume": "play",
    "unpause": "play",
    "start": "play",
    "halt": "stop",
    "skip": "next",
    "back": "previous",
    "prev": "previous",
    "pause_play": "toggle",
    "play_pause": "toggle",
}

_VALID_OPTIONS = {"play", "replace", "next", "add"}


def _normalize_option(option: str) -> str:
    candidate = (option or "play").strip().lower()
    return candidate if candidate in _VALID_OPTIONS else "play"


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
        omitted (or unrecognized) -> ["playlist"].
    source: name/substring of one specific provider (e.g. "tidal", "spotify",
        "my-nas-share") to force that provider; omitted -> best match is picked
        automatically using the configured provider priority order.
    scope: "online" (streaming providers only, e.g. Spotify/Tidal/Apple - rich
        thematic search), "local" (local/SMB/WebDAV file providers only - literal
        matching), or "all" (default - search everywhere, today's behavior).
        Ignored if `source` is given.
    option: "play" (clear queue and play now, default), "replace", "next", "add".
        Unrecognized values fall back to "play".
    radio_mode: start a continuous radio mix seeded from the match (e.g. an artist or
        track) instead of just playing it once. Only artist/track seeds from a provider
        that actually supports it (checked live) can do this - silently falls back to a
        normal single play otherwise (e.g. local/offline-only items, or playlists/albums/
        radio stations, none of which MA can generate a "similar tracks" mix for).
    """
    client = await get_client()
    resolved_player = await resolve_player(client, player)
    available_providers = await providers_logic.list_providers(client)
    provider_filter = providers_logic.resolve_provider_filter(available_providers, source, scope)

    media_types = normalize_media_types(media_types)
    option = _normalize_option(option)

    best, candidates = await search_and_pick(
        client, query, media_types=media_types, source=source, providers=provider_filter
    )
    if best is None:
        raise ValueError(f"No results found for '{query}'" + (f" from {source}" if source else ""))

    effective_radio_mode = radio_mode and providers_logic.supports_radio(
        available_providers,
        best.media_type,
        (*best.provider_instances, *([best.provider] if best.provider else ())),
        provider_filter,
    )

    await client.send(
        "player_queues/play_media",
        queue_id=resolved_player.player_id,
        media=best.uri,
        option=option,
        radio_mode=effective_radio_mode,
    )
    result = {
        "player": resolved_player.name,
        "matched": [c.name for c in candidates[:5]],
        "playing": {"name": best.name, "provider": best.provider, "uri": best.uri},
        "radio_mode": effective_radio_mode,
    }
    if radio_mode and not effective_radio_mode:
        result["note"] = (
            "radio_mode was requested but isn't supported for this pick (local/offline "
            "provider, or a playlist/album/radio station) - played normally instead"
        )
    return result


async def control(
    player: str | None = None,
    command: str = "play",
    seek_seconds: int | None = None,
) -> dict:
    """Playback transport control.

    command: "play" | "pause" | "stop" | "toggle" | "next" | "previous" (a few common
        synonyms like "resume"/"skip"/"prev" are also accepted); unrecognized values
        fall back to "play" rather than failing.
    seek_seconds: if given, seeks to that position instead (convert mm:ss to seconds).
    """
    client = await get_client()
    resolved_player = await resolve_player(client, player)

    if seek_seconds is not None:
        await client.send(
            "player_queues/seek", queue_id=resolved_player.player_id, position=max(0, seek_seconds)
        )
        return {"player": resolved_player.name, "command": "seek", "seek_seconds": seek_seconds}

    requested = (command or "play").strip().lower()
    normalized = _COMMAND_ALIASES.get(requested, requested)
    ws_command = _TRANSPORT_COMMANDS.get(normalized)

    result = {"player": resolved_player.name, "command": normalized}
    if ws_command is None:
        ws_command = "play"
        normalized = "play"
        result["command"] = "play"
        result["note"] = f"unrecognized command '{command}', defaulted to play"

    await client.send(f"player_queues/{ws_command}", queue_id=resolved_player.player_id)
    return result


def register(mcp: FastMCP) -> None:
    mcp.tool()(play)
    mcp.tool()(control)
