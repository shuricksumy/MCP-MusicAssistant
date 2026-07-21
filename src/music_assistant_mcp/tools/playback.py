from mcp.server.fastmcp import FastMCP
from music_assistant_models.errors import MediaNotFoundError, UnplayableMediaError

from .. import providers as providers_logic
from ..ma_client import get_client
from ..players import resolve_player
from ..search import normalize_media_types, search_and_pick
from .queue import fetch_queue_status

# A matched search result can still turn out unplayable server-side (e.g. an empty
# user-created playlist, or a moved/deleted local file) - confirmed live with a
# same-named local "Jazz" playlist that had no tracks in it. Retrying the next
# candidate is much smoother than failing the whole call over one bad pick.
_UNPLAYABLE_ERRORS = (MediaNotFoundError, UnplayableMediaError)
_MAX_PLAY_ATTEMPTS = 3

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
# Read-only queries an agent naturally reaches for on "what's playing?"-type asks.
# These must never fall through to the "unrecognized -> play" default below, since that
# would resume/restart playback in response to a question that wasn't asking for that.
_STATUS_COMMANDS = {"get", "status", "now_playing", "nowplaying", "info", "state", "current"}

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
        matching), or "all" (search everywhere). Omitted -> defaults to "online"
        (matches how a human would habitually reach for Spotify/Tidal before their own
        files), automatically broadening to everything if nothing turns up there - so a
        local-only match still gets found without asking for it by name. Ignored if
        `source` is given.
    option: "play" (clear queue and play now, default), "replace", "next", "add".
        Unrecognized values fall back to "play".
    radio_mode: start a continuous radio mix seeded from the match (e.g. an artist or
        track) instead of just playing it once. Only artist/track seeds from a provider
        that actually supports it (checked live) can do this - silently falls back to a
        normal single play otherwise (e.g. local/offline-only items, or playlists/albums/
        radio stations, none of which MA can generate a "similar tracks" mix for).

    If the top match turns out unplayable (e.g. an empty playlist, or a moved/deleted
    local file), automatically tries the next candidate before giving up.
    """
    if not query or not query.strip():
        raise ValueError(
            "query is required and can't be empty - for a query-less 'surprise me'/random "
            "pick, use play_random() instead"
        )

    client = await get_client()
    resolved_player = await resolve_player(client, player)
    available_providers = await providers_logic.list_providers(client)

    used_default_scope = not source and not scope
    try:
        provider_filter = providers_logic.resolve_provider_filter(available_providers, source, scope)
    except providers_logic.ProviderNotFoundError:
        if not used_default_scope:
            raise
        provider_filter = None  # no online providers configured - just search everything

    media_types = normalize_media_types(media_types)
    option = _normalize_option(option)

    best, candidates = await search_and_pick(
        client, query, media_types=media_types, source=source, providers=provider_filter
    )
    if best is None and used_default_scope and provider_filter is not None:
        # nothing found among online providers (the implicit default) - broaden to
        # everything, including local, rather than failing outright.
        provider_filter = None
        best, candidates = await search_and_pick(
            client, query, media_types=media_types, source=source, providers=provider_filter
        )
    if best is None:
        raise ValueError(f"No results found for '{query}'" + (f" from {source}" if source else ""))

    attempts = [best, *(c for c in candidates if c is not best)][:_MAX_PLAY_ATTEMPTS]
    skipped: list[str] = []
    last_error: Exception | None = None
    picked = None
    for candidate in attempts:
        effective_radio_mode = radio_mode and providers_logic.supports_radio(
            available_providers,
            candidate.media_type,
            (*candidate.provider_instances, *([candidate.provider] if candidate.provider else ())),
            provider_filter,
        )
        try:
            await client.send(
                "player_queues/play_media",
                queue_id=resolved_player.player_id,
                media=candidate.uri,
                option=option,
                radio_mode=effective_radio_mode,
            )
            picked = candidate
            break
        except _UNPLAYABLE_ERRORS as err:
            last_error = err
            skipped.append(candidate.name)

    if picked is None:
        raise ValueError(
            f"Found matches for '{query}' but none were playable "
            f"(tried: {', '.join(skipped)}): {last_error}"
        )

    result = {
        "player": resolved_player.name,
        "matched": [c.name for c in candidates[:5]],
        "playing": {"name": picked.name, "provider": picked.provider, "uri": picked.uri},
        "radio_mode": effective_radio_mode,
    }
    if skipped:
        result["note"] = f"skipped unplayable match(es): {', '.join(skipped)}"
    if radio_mode and not effective_radio_mode:
        existing_note = result.get("note")
        radio_note = (
            "radio_mode was requested but isn't supported for this pick (local/offline "
            "provider, or a playlist/album/radio station) - played normally instead"
        )
        result["note"] = f"{existing_note}; {radio_note}" if existing_note else radio_note
    return result


async def play_random(
    player: str | None = None,
    scope: str | None = None,
    source: str | None = None,
    count: int = 20,
    option: str = "play",
) -> dict:
    """Build and play a random mix pulled straight from the library - no search query
    needed. Use for "play something"/"surprise me"/"random mix from my local files"
    type requests, as opposed to `play` which needs something to search for.

    scope: "local" (only your own local/SMB/WebDAV files - e.g. "play something random
        from my local library"), "online" (only synced/favorited tracks from streaming
        providers), or "all" (default - anything in your library, local or online).
    source: name/substring of one specific provider to restrict to instead of scope.
    count: how many random tracks to queue (1-100, default 20).
    option: "play" (clear queue and play now, default), "replace", "next", "add".
    """
    client = await get_client()
    resolved_player = await resolve_player(client, player)
    available_providers = await providers_logic.list_providers(client)
    provider_filter = providers_logic.resolve_provider_filter(available_providers, source, scope or "all")

    count = max(1, min(100, count))
    option = _normalize_option(option)

    tracks = await client.send(
        "music/tracks/library_items", limit=count, order_by="random", provider=provider_filter
    )
    uris = [t["uri"] for t in tracks or [] if t.get("uri")]
    if not uris:
        raise ValueError(
            "No tracks found in your library" + (f" for scope='{scope}'" if scope else "")
        )

    await client.send(
        "player_queues/play_media", queue_id=resolved_player.player_id, media=uris, option=option
    )
    return {
        "player": resolved_player.name,
        "count": len(uris),
        "tracks": [t.get("name") for t in tracks[: len(uris)]],
    }


async def control(
    player: str | None = None,
    command: str = "play",
    seek_seconds: int | None = None,
) -> dict:
    """Playback transport control.

    command: "play" | "pause" | "stop" | "toggle" | "next" | "previous" (a few common
        synonyms like "resume"/"skip"/"prev" are also accepted); unrecognized values
        fall back to "play" rather than failing. For "what's playing?"-style questions,
        use "get" | "status" | "now_playing" | "info" | "state" | "current" - these
        return the current track/queue status and never trigger playback.
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
    if requested in _STATUS_COMMANDS:
        status = await fetch_queue_status(client, resolved_player.player_id)
        return {"player": resolved_player.name, "command": "status", "queue": status}

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
    mcp.tool()(play_random)
    mcp.tool()(control)
