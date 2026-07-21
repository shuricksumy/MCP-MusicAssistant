import pytest

import music_assistant_mcp.tools.playback as playback_module
from music_assistant_mcp.tools.playback import control, play

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
    assert kwargs["option"] == "play"


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
