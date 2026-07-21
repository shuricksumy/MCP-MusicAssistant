"""Search + source-tiebreak - the code-side replacement for STEP 2/2.1 of the old prompt
(manually filtering results by URI prefix and applying a Tidal > Spotify > Apple rule)."""

from __future__ import annotations

from dataclasses import dataclass

from .config import settings
from .ma_client import MAClient

DEFAULT_MEDIA_TYPES = ["playlist"]

# music/search's response groups results under plural (mostly) keys that don't match
# the singular MediaType values used as request params - confirmed against a live server.
_RESULT_KEYS = {
    "playlist": "playlists",
    "track": "tracks",
    "album": "albums",
    "artist": "artists",
    "radio": "radio",
}

_MEDIA_TYPE_ALIASES = {
    "song": "track",
    "songs": "track",
    "tracks": "track",
    "playlists": "playlist",
    "albums": "album",
    "artists": "artist",
    "radios": "radio",
    "station": "radio",
    "stations": "radio",
}


def normalize_media_types(media_types: list[str] | None) -> list[str]:
    """Map common mistakes (plurals, "song") to valid values and drop anything still
    unrecognized, rather than sending it through and letting the server reject it -
    an agent passing a slightly-off value shouldn't hard-fail the whole call."""
    if not media_types:
        return list(DEFAULT_MEDIA_TYPES)
    normalized: list[str] = []
    for mt in media_types:
        candidate = _MEDIA_TYPE_ALIASES.get(mt.strip().lower(), mt.strip().lower())
        if candidate in _RESULT_KEYS and candidate not in normalized:
            normalized.append(candidate)
    return normalized or list(DEFAULT_MEDIA_TYPES)


def _domain_of(provider_id: str | None) -> str | None:
    """Provider fields/URIs use an instance id like "spotify--9hcJiXgW" or
    "apple_music--4KbYhDtU" (confirmed against a live server) - this is the plain
    domain ("spotify", "apple_music") for tiebreak/filter matching."""
    if not provider_id:
        return None
    return provider_id.split("--", 1)[0]


@dataclass(frozen=True)
class MediaItem:
    uri: str
    name: str
    media_type: str
    provider: str | None = None
    # A "library" item (synced/favorited locally) reports provider="library" at the top
    # level but is actually backed by one or more real provider instances - these let us
    # tell whether it's genuinely available via an allowed provider (see filter_by_providers).
    provider_instances: tuple[str, ...] = ()

    @classmethod
    def from_raw(cls, raw: dict, media_type: str) -> "MediaItem":
        return cls(
            uri=raw.get("uri"),
            name=raw.get("name") or raw.get("title") or raw.get("uri"),
            media_type=media_type,
            provider=raw.get("provider") or raw.get("provider_domain"),
            provider_instances=tuple(
                m["provider_instance"]
                for m in raw.get("provider_mappings") or []
                if m.get("provider_instance")
            ),
        )


def _provider_of(item: MediaItem) -> str | None:
    if item.provider:
        return _domain_of(item.provider)
    return _domain_of((item.uri or "").split("://", 1)[0]) if item.uri else None


def flatten_results(raw_results: dict, media_types: list[str]) -> list[MediaItem]:
    items: list[MediaItem] = []
    for media_type in media_types:
        result_key = _RESULT_KEYS.get(media_type, media_type)
        for raw in raw_results.get(result_key) or []:
            items.append(MediaItem.from_raw(raw, media_type))
    return items


def filter_by_source(items: list[MediaItem], source: str | None) -> list[MediaItem]:
    if not source:
        return items
    source = source.lower()
    return [item for item in items if _provider_of(item) == source]


def filter_by_providers(items: list[MediaItem], providers: list[str] | None) -> list[MediaItem]:
    """Client-side safety net for the `providers=` restriction sent to music/search:
    confirmed against a live server that the server-side filter is unreliable (repeat
    identical requests sometimes returned unfiltered results across all providers, not
    just the ones requested) - so re-check here rather than trust it blindly. A "library"
    item (provider="library") is kept if any of its real backing provider_instances match.
    """
    if not providers:
        return items
    allowed = set(providers)
    return [
        item
        for item in items
        if item.provider in allowed or allowed.intersection(item.provider_instances)
    ]


# Identity lookups (is this literally the artist/track/album asked for?) need every
# query word present in the name - confirmed against a live server that a provider can
# return an irrelevant top "match" (e.g. Tidal returning "Fatboy Slim" for a search for
# "The Prodigy"), and blindly source-prioritizing that irrelevant hit plays the wrong
# thing. Playlists/radio stay priority-only: a themed/vibe query (e.g. "jazz vibes")
# legitimately won't literally appear in every provider's own curated playlist name.
_IDENTITY_MEDIA_TYPES = {"artist", "track", "album"}


def _name_matches_query(name: str, query: str) -> bool:
    name = name.lower()
    return all(word in name for word in query.lower().split())


def pick_best(
    items: list[MediaItem],
    query: str | None = None,
    priority: tuple[str, ...] = settings.source_priority,
) -> MediaItem | None:
    """Pick the best item: for artist/track/album, a name match to `query` always wins
    over source priority; for playlist/radio, source priority alone decides. Ties within
    a group keep provider priority order, then original (relevance) order.

    Returns None (no genuine match) rather than the top-ranked item when doing an
    artist/track/album lookup and *nothing* actually matched the query by name -
    confirmed live that a nonsense query can otherwise still "confidently" return some
    unrelated artist, since a source-priority tiebreak among equally-unmatched
    candidates always picks something. Playlists/radio are unaffected (no name-match
    requirement to begin with).
    """
    if not items:
        return None

    def rank(item: MediaItem) -> tuple[int, int]:
        provider = _provider_of(item)
        try:
            source_rank = priority.index(provider) if provider else len(priority)
        except ValueError:
            source_rank = len(priority)

        if query and item.media_type in _IDENTITY_MEDIA_TYPES:
            match_rank = 0 if _name_matches_query(item.name, query) else 1
        else:
            match_rank = 0
        return (match_rank, source_rank)

    best = min(items, key=rank)
    match_rank, _ = rank(best)
    if query and best.media_type in _IDENTITY_MEDIA_TYPES and match_rank == 1:
        return None
    return best


async def search_and_pick(
    client: MAClient,
    query: str,
    media_types: list[str] | None = None,
    source: str | None = None,
    providers: list[str] | None = None,
    limit: int = 15,
) -> tuple[MediaItem | None, list[MediaItem]]:
    """Returns (best_match, all_candidates). `media_types` defaults to ["playlist"].

    `providers` (instance ids) restricts the search to just online streaming providers or
    just local file providers - requested server-side, then re-checked client-side via
    filter_by_providers() since the server-side restriction was found to be unreliable.
    `source` still applies an additional client-side tiebreak/filter on top.
    """
    media_types = normalize_media_types(media_types)
    limit = max(1, min(50, limit or 15))
    raw = await client.send(
        "music/search",
        search_query=query,
        media_types=media_types,
        limit=limit,
        providers=providers,
    )
    items = flatten_results(raw or {}, media_types)
    candidates = filter_by_providers(items, providers)
    candidates = filter_by_source(candidates, source)
    return pick_best(candidates, query=query), candidates
