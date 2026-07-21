import pytest

import music_assistant_mcp.tools.playback as playback_module
from music_assistant_mcp.tools.playback import control, play, play_random

from fakes import FakeMAClient

STREAMING_PROVIDERS = [
    {
        "instance_id": "spotify--x",
        "domain": "spotify",
        "name": "Spotify",
        "type": "music",
        "is_streaming_provider": True,
        "supported_features": ["search", "similar_tracks"],
    },
]
LOCAL_PROVIDERS = [
    {
        "instance_id": "webdav--y",
        "domain": "webdav",
        "name": "WebDav",
        "type": "music",
        "is_streaming_provider": False,
        "supported_features": ["search"],
    },
]


@pytest.fixture
def patched_client(players_raw, monkeypatch):
    def _install(**extra_responses):
        client = FakeMAClient(
            {
                "players/all": players_raw,
                "providers": STREAMING_PROVIDERS + LOCAL_PROVIDERS,
                **extra_responses,
            }
        )

        async def _fake_get_client():
            return client

        monkeypatch.setattr(playback_module, "get_client", _fake_get_client)
        return client

    return _install


# --- control() ---


async def test_control_defaults_to_play(patched_client):
    client = patched_client()
    result = await control(player="Living Room")
    assert result == {"player": "Living Room", "command": "play"}
    command, _ = client.calls[-1]
    assert command == "player_queues/play"


async def test_control_case_insensitive(patched_client):
    client = patched_client()
    await control(player="Living Room", command="PAUSE")
    command, _ = client.calls[-1]
    assert command == "player_queues/pause"


async def test_control_accepts_synonym(patched_client):
    client = patched_client()
    result = await control(player="Living Room", command="resume")
    assert result["command"] == "play"
    command, _ = client.calls[-1]
    assert command == "player_queues/play"


async def test_control_unrecognized_falls_back_to_play_with_note(patched_client):
    client = patched_client()
    result = await control(player="Living Room", command="frobnicate")
    assert result["command"] == "play"
    assert "note" in result
    command, _ = client.calls[-1]
    assert command == "player_queues/play"


async def test_control_get_returns_status_without_sending_playback_command(patched_client):
    client = patched_client(
        **{
            "player_queues/all": [{"queue_id": "up1", "state": "paused", "shuffle_enabled": False}],
            "player_queues/items": [],
        }
    )
    result = await control(player="Living Room", command="get")
    assert result["command"] == "status"
    assert result["queue"]["state"] == "paused"
    assert all(c[0] != "player_queues/play" for c in client.calls)


async def test_control_status_synonyms_all_return_status(patched_client):
    client = patched_client(
        **{
            "player_queues/all": [{"queue_id": "up1", "state": "playing"}],
            "player_queues/items": [],
        }
    )
    for synonym in ("status", "now_playing", "info", "state", "current"):
        result = await control(player="Living Room", command=synonym)
        assert result["command"] == "status"
    assert all(c[0] != "player_queues/play" for c in client.calls)


async def test_control_seek_clamps_negative_to_zero(patched_client):
    client = patched_client()
    await control(player="Living Room", seek_seconds=-30)
    command, kwargs = client.calls[-1]
    assert command == "player_queues/seek"
    assert kwargs["position"] == 0


# --- play() ---


async def test_play_option_normalizes_invalid_to_play(patched_client):
    client = patched_client(
        **{"music/search": {"playlists": [{"uri": "spotify--x://playlist/1", "name": "Chill"}]}}
    )
    await play(query="chill", player="Living Room", option="bogus")
    command, kwargs = client.calls[-1]
    assert command == "player_queues/play_media"
    # our "play" (clear queue and play now) must be sent as MA's "replace" - MA's own
    # "play" option inserts at the current position without clearing the queue.
    assert kwargs["option"] == "replace"


async def test_play_radio_mode_disabled_for_local_only_pick(patched_client):
    client = patched_client(
        **{
            "music/search": {
                "artists": [{"uri": "webdav--y://artist/1", "name": "Coldplay", "provider": "webdav--y"}]
            }
        }
    )
    result = await play(
        query="Coldplay", player="Living Room", media_types=["artist"], scope="local", radio_mode=True
    )
    assert result["radio_mode"] is False
    assert "note" in result
    command, kwargs = client.calls[-1]
    assert kwargs["radio_mode"] is False


async def test_play_radio_mode_enabled_for_streaming_artist(patched_client):
    client = patched_client(
        **{
            "music/search": {
                "artists": [
                    {"uri": "spotify--x://artist/1", "name": "The Prodigy", "provider": "spotify--x"}
                ]
            }
        }
    )
    result = await play(
        query="The Prodigy", player="Living Room", media_types=["artist"], radio_mode=True
    )
    assert result["radio_mode"] is True
    assert "note" not in result
    command, kwargs = client.calls[-1]
    assert kwargs["radio_mode"] is True


async def test_play_radio_mode_disabled_for_playlist_even_on_streaming_provider(patched_client):
    client = patched_client(
        **{"music/search": {"playlists": [{"uri": "spotify--x://playlist/1", "name": "Chill"}]}}
    )
    result = await play(query="chill", player="Living Room", radio_mode=True)
    assert result["radio_mode"] is False
    assert "note" in result


# --- default scope (omitted) prefers online, falls back to everything ---


async def test_play_default_scope_finds_online_item_without_fallback(patched_client):
    client = patched_client(
        **{
            "music/search": {
                "artists": [{"uri": "spotify--x://artist/1", "name": "Coldplay", "provider": "spotify--x"}]
            }
        }
    )
    result = await play(query="Coldplay", player="Living Room", media_types=["artist"])
    assert result["playing"]["provider"] == "spotify--x"
    search_calls = [c for c in client.calls if c[0] == "music/search"]
    assert len(search_calls) == 1
    assert search_calls[0][1]["providers"] == ["spotify--x"]


async def test_play_default_scope_falls_back_to_local_when_nothing_online(patched_client):
    client = patched_client(
        **{
            "music/search": {
                "artists": [{"uri": "webdav--y://artist/1", "name": "Coldplay", "provider": "webdav--y"}]
            }
        }
    )
    result = await play(query="Coldplay", player="Living Room", media_types=["artist"])
    assert result["playing"]["provider"] == "webdav--y"
    search_calls = [c for c in client.calls if c[0] == "music/search"]
    assert len(search_calls) == 2
    assert search_calls[0][1]["providers"] == ["spotify--x"]
    assert search_calls[1][1]["providers"] is None


async def test_play_falls_back_when_no_online_providers_configured(monkeypatch, players_raw):
    client = FakeMAClient(
        {
            "players/all": players_raw,
            "providers": LOCAL_PROVIDERS,
            "music/search": {
                "artists": [{"uri": "webdav--y://artist/1", "name": "Coldplay", "provider": "webdav--y"}]
            },
        }
    )

    async def _fake_get_client():
        return client

    monkeypatch.setattr(playback_module, "get_client", _fake_get_client)

    result = await play(query="Coldplay", player="Living Room", media_types=["artist"])
    assert result["playing"]["provider"] == "webdav--y"


async def test_play_explicit_scope_online_does_not_fall_back(patched_client):
    client = patched_client(**{"music/search": {"artists": []}})
    with pytest.raises(ValueError):
        await play(query="Coldplay", player="Living Room", media_types=["artist"], scope="online")
    search_calls = [c for c in client.calls if c[0] == "music/search"]
    assert len(search_calls) == 1


# --- play_random() ---

RANDOM_TRACKS = [
    {"uri": "webdav--y://track/1", "name": "Track A"},
    {"uri": "webdav--y://track/2", "name": "Track B"},
    {"uri": "spotify--x://track/3", "name": "Track C"},
]


async def test_play_random_defaults_to_all_scope(patched_client):
    client = patched_client(**{"music/tracks/library_items": RANDOM_TRACKS})
    result = await play_random(player="Living Room")
    assert result["count"] == 3
    assert result["tracks"] == ["Track A", "Track B", "Track C"]
    command, kwargs = client.calls[-1]
    assert command == "player_queues/play_media"
    assert kwargs["media"] == [t["uri"] for t in RANDOM_TRACKS]

    library_call = next(c for c in client.calls if c[0] == "music/tracks/library_items")
    assert library_call[1]["order_by"] == "random"
    assert library_call[1]["provider"] is None


async def test_play_random_scope_local_restricts_provider(patched_client):
    client = patched_client(**{"music/tracks/library_items": RANDOM_TRACKS[:2]})
    await play_random(player="Living Room", scope="local")
    library_call = next(c for c in client.calls if c[0] == "music/tracks/library_items")
    assert library_call[1]["provider"] == ["webdav--y"]


async def test_play_random_count_clamped_to_valid_range(patched_client):
    client = patched_client(**{"music/tracks/library_items": RANDOM_TRACKS})
    await play_random(player="Living Room", count=1000)
    library_call = next(c for c in client.calls if c[0] == "music/tracks/library_items")
    assert library_call[1]["limit"] == 100

    await play_random(player="Living Room", count=-5)
    library_call = next(c for c in reversed(client.calls) if c[0] == "music/tracks/library_items")
    assert library_call[1]["limit"] == 1


async def test_play_random_no_tracks_raises(patched_client):
    patched_client(**{"music/tracks/library_items": []})
    with pytest.raises(ValueError):
        await play_random(player="Living Room", scope="local")


async def test_play_random_option_normalized(patched_client):
    client = patched_client(**{"music/tracks/library_items": RANDOM_TRACKS})
    await play_random(player="Living Room", option="bogus")
    command, kwargs = client.calls[-1]
    assert command == "player_queues/play_media"
    assert kwargs["option"] == "replace"


async def test_play_default_option_clears_queue_via_replace_not_ma_play(patched_client):
    # Regression test: MA's own "play" queue-option inserts at the current position
    # and does NOT clear the queue - only "replace" does. Sending our default option
    # as literal "play" caused the queue to grow unbounded across requests instead of
    # starting fresh each time.
    client = patched_client(
        **{"music/search": {"playlists": [{"uri": "spotify--x://playlist/1", "name": "Chill"}]}}
    )
    await play(query="chill", player="Living Room")
    command, kwargs = client.calls[-1]
    assert command == "player_queues/play_media"
    assert kwargs["option"] == "replace"


async def test_play_shuffle_sends_shuffle_command_when_given(patched_client):
    client = patched_client(
        **{"music/search": {"playlists": [{"uri": "spotify--x://playlist/1", "name": "Chill"}]}}
    )
    result = await play(query="chill", player="Living Room", shuffle=True)
    assert result["shuffle"] is True
    shuffle_calls = [c for c in client.calls if c[0] == "player_queues/shuffle"]
    assert len(shuffle_calls) == 1
    assert shuffle_calls[0][1]["shuffle_enabled"] is True


async def test_play_omitted_shuffle_sends_no_shuffle_command(patched_client):
    client = patched_client(
        **{"music/search": {"playlists": [{"uri": "spotify--x://playlist/1", "name": "Chill"}]}}
    )
    result = await play(query="chill", player="Living Room")
    assert "shuffle" not in result
    assert all(c[0] != "player_queues/shuffle" for c in client.calls)


async def test_play_random_shuffle_sends_shuffle_command_when_given(patched_client):
    client = patched_client(**{"music/tracks/library_items": RANDOM_TRACKS})
    result = await play_random(player="Living Room", shuffle=False)
    assert result["shuffle"] is False
    shuffle_calls = [c for c in client.calls if c[0] == "player_queues/shuffle"]
    assert len(shuffle_calls) == 1
    assert shuffle_calls[0][1]["shuffle_enabled"] is False


async def test_play_explicit_next_and_add_pass_through_unchanged(patched_client):
    client = patched_client(
        **{"music/search": {"playlists": [{"uri": "spotify--x://playlist/1", "name": "Chill"}]}}
    )
    await play(query="chill", player="Living Room", option="next")
    assert client.calls[-1][1]["option"] == "next"

    await play(query="chill", player="Living Room", option="add")
    assert client.calls[-1][1]["option"] == "add"


# --- play() retries the next candidate if the top match is unplayable ---


async def test_play_retries_next_candidate_when_top_match_unplayable(patched_client):
    from music_assistant_models.errors import MediaNotFoundError

    def flaky_play_media(call_number, kwargs):
        if call_number == 1:
            raise MediaNotFoundError("empty playlist")
        return None

    client = patched_client(
        **{
            "music/search": {
                "playlists": [
                    {"uri": "spotify--x://playlist/1", "name": "Empty Jazz"},
                    {"uri": "spotify--x://playlist/2", "name": "Real Jazz"},
                ]
            },
            "player_queues/play_media": flaky_play_media,
        }
    )
    result = await play(query="jazz", player="Living Room")
    assert result["playing"]["name"] == "Real Jazz"
    assert "Empty Jazz" in result["note"]
    play_media_calls = [c for c in client.calls if c[0] == "player_queues/play_media"]
    assert len(play_media_calls) == 2


async def test_play_raises_clear_error_when_all_candidates_unplayable(patched_client):
    from music_assistant_models.errors import MediaNotFoundError

    def always_fails(call_number, kwargs):
        raise MediaNotFoundError("gone")

    client = patched_client(
        **{
            "music/search": {"playlists": [{"uri": "spotify--x://playlist/1", "name": "Gone"}]},
            "player_queues/play_media": always_fails,
        }
    )
    with pytest.raises(ValueError, match="none were playable"):
        await play(query="jazz", player="Living Room")


async def test_play_empty_query_raises_with_helpful_message(patched_client):
    patched_client()
    with pytest.raises(ValueError, match="play_random"):
        await play(query="", player="Living Room")


async def test_play_whitespace_only_query_raises(patched_client):
    patched_client()
    with pytest.raises(ValueError, match="play_random"):
        await play(query="   ", player="Living Room")
