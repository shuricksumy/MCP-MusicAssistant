from music_assistant_mcp.search import (
    MediaItem,
    filter_by_providers,
    filter_by_source,
    flatten_results,
    normalize_media_types,
    pick_best,
    search_and_pick,
)

from fakes import FakeMAClient

TIDAL = MediaItem(uri="tidal--abc123://playlist/1", name="Morning Energy (Tidal)", media_type="playlist")
SPOTIFY = MediaItem(uri="spotify--xyz789://playlist/2", name="Morning Energy (Spotify)", media_type="playlist")
APPLE = MediaItem(uri="apple_music://playlist/3", name="Morning Energy (Apple)", media_type="playlist")


def test_flatten_results_combines_media_types():
    raw = {
        "playlists": [{"uri": "tidal--x://playlist/1", "name": "P1"}],
        "tracks": [{"uri": "tidal--x://track/1", "name": "T1"}],
    }
    items = flatten_results(raw, ["playlist", "track"])
    assert [i.media_type for i in items] == ["playlist", "track"]


def test_pick_best_prefers_tidal_over_spotify_and_apple():
    assert pick_best([SPOTIFY, APPLE, TIDAL]) is TIDAL


def test_pick_best_prefers_spotify_over_apple_when_no_tidal():
    assert pick_best([APPLE, SPOTIFY]) is SPOTIFY


def test_pick_best_empty_returns_none():
    assert pick_best([]) is None


def test_pick_best_unranked_provider_ranked_last_but_kept():
    unranked = MediaItem(uri="other://playlist/9", name="Mystery", media_type="playlist", provider="other")
    assert pick_best([unranked, APPLE]) is APPLE


def test_filter_by_source_matches_uri_hint():
    filtered = filter_by_source([TIDAL, SPOTIFY, APPLE], "spotify")
    assert filtered == [SPOTIFY]


def test_filter_by_source_no_source_returns_all():
    items = [TIDAL, SPOTIFY]
    assert filter_by_source(items, None) == items


async def test_search_and_pick_defaults_to_playlist_and_applies_tiebreak():
    client = FakeMAClient(
        {
            "music/search": {
                "playlists": [
                    {"uri": "spotify--x://playlist/1", "name": "Chill (Spotify)"},
                    {"uri": "tidal--x://playlist/2", "name": "Chill (Tidal)"},
                ]
            }
        }
    )
    best, candidates = await search_and_pick(client, "chill")
    assert best.name == "Chill (Tidal)"
    assert len(candidates) == 2
    command, kwargs = client.calls[0]
    assert command == "music/search"
    assert kwargs["media_types"] == ["playlist"]


async def test_search_and_pick_honors_explicit_source():
    client = FakeMAClient(
        {
            "music/search": {
                "playlists": [
                    {"uri": "spotify--x://playlist/1", "name": "Chill (Spotify)"},
                    {"uri": "tidal--x://playlist/2", "name": "Chill (Tidal)"},
                ]
            }
        }
    )
    best, candidates = await search_and_pick(client, "chill", source="spotify")
    assert best.name == "Chill (Spotify)"
    assert len(candidates) == 1


async def test_search_and_pick_passes_providers_through_to_ma_search():
    client = FakeMAClient({"music/search": {"playlists": []}})
    await search_and_pick(client, "chill", providers=["filesystem_smb--ghi"])
    command, kwargs = client.calls[0]
    assert command == "music/search"
    assert kwargs["providers"] == ["filesystem_smb--ghi"]


async def test_search_and_pick_reapplies_providers_client_side_when_server_ignores_it():
    # Regression: a live server sometimes returned results from every provider despite
    # a restrictive `providers=` argument (non-deterministic, confirmed by repeat calls)
    # - filter_by_providers must catch what the server-side restriction missed.
    client = FakeMAClient(
        {
            "music/search": {
                "artists": [
                    {"uri": "webdav--ph58://artist/1", "name": "Coldplay", "provider": "webdav--ph58"},
                    {"uri": "spotify--9hc://artist/2", "name": "Coldplay", "provider": "spotify--9hc"},
                ]
            }
        }
    )
    best, candidates = await search_and_pick(
        client, "Coldplay", media_types=["artist"], providers=["webdav--ph58"]
    )
    assert len(candidates) == 1
    assert best.provider == "webdav--ph58"


def test_filter_by_providers_keeps_library_item_via_provider_mappings():
    library_item = MediaItem(
        uri="library://artist/2",
        name="Coldplay",
        media_type="artist",
        provider="library",
        provider_instances=("tidal--KTohL5uk", "webdav--ph58JcEk"),
    )
    result = filter_by_providers([library_item], ["webdav--ph58JcEk"])
    assert result == [library_item]


def test_filter_by_providers_drops_unmatched_items():
    spotify_item = MediaItem(uri="spotify--x://artist/1", name="Coldplay", media_type="artist", provider="spotify--x")
    assert filter_by_providers([spotify_item], ["webdav--ph58JcEk"]) == []


def test_filter_by_providers_no_restriction_returns_all():
    items = [TIDAL, SPOTIFY]
    assert filter_by_providers(items, None) == items


def test_pick_best_artist_name_match_beats_source_priority():
    # Regression: a live server returned Tidal's top "The Prodigy" hit as the wrong
    # artist ("Fatboy Slim") - name relevance must win over blind source priority for
    # identity lookups (artist/track/album), even though Tidal ranks first.
    wrong_artist_on_top_provider = MediaItem(
        uri="tidal--x://artist/1", name="Fatboy Slim", media_type="artist"
    )
    correct_artist_on_lower_provider = MediaItem(
        uri="apple_music://artist/2", name="The Prodigy", media_type="artist"
    )
    best = pick_best(
        [wrong_artist_on_top_provider, correct_artist_on_lower_provider], query="The Prodigy"
    )
    assert best is correct_artist_on_lower_provider


def test_pick_best_playlist_ignores_name_match_uses_priority_only():
    # Themed/vibe playlist queries legitimately won't literally match every provider's
    # own curated name - playlists stay priority-only, unlike artist/track/album.
    literal_name_match_low_priority = MediaItem(
        uri="apple_music://playlist/1", name="jazz vibes", media_type="playlist"
    )
    themed_but_differently_named_top_priority = MediaItem(
        uri="tidal--x://playlist/2", name="Late Night Jazz", media_type="playlist"
    )
    best = pick_best(
        [literal_name_match_low_priority, themed_but_differently_named_top_priority],
        query="jazz vibes",
    )
    assert best is themed_but_differently_named_top_priority


# --- normalize_media_types ---


def test_normalize_media_types_none_defaults_to_playlist():
    assert normalize_media_types(None) == ["playlist"]


def test_normalize_media_types_empty_list_defaults_to_playlist():
    assert normalize_media_types([]) == ["playlist"]


def test_normalize_media_types_maps_common_aliases():
    assert normalize_media_types(["song", "Albums", " ARTISTS "]) == ["track", "album", "artist"]


def test_normalize_media_types_drops_unrecognized_but_keeps_valid():
    assert normalize_media_types(["track", "nonsense"]) == ["track"]


def test_normalize_media_types_all_unrecognized_defaults_to_playlist():
    assert normalize_media_types(["nonsense", "garbage"]) == ["playlist"]


def test_normalize_media_types_deduplicates():
    assert normalize_media_types(["track", "tracks", "song"]) == ["track"]
