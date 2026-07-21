import pytest

import music_assistant_mcp.tools.search as search_tool_module
from music_assistant_mcp.tools.search import search

from fakes import FakeMAClient

STREAMING_PROVIDERS = [
    {
        "instance_id": "spotify--x",
        "domain": "spotify",
        "name": "Spotify",
        "type": "music",
        "is_streaming_provider": True,
        "supported_features": ["search"],
    },
]


@pytest.fixture
def patched_client(monkeypatch):
    def _install(**extra_responses):
        client = FakeMAClient({"providers": STREAMING_PROVIDERS, **extra_responses})

        async def _fake_get_client():
            return client

        monkeypatch.setattr(search_tool_module, "get_client", _fake_get_client)
        return client

    return _install


async def test_search_empty_query_raises(patched_client):
    patched_client()
    with pytest.raises(ValueError):
        await search(query="")


async def test_search_defaults_to_online_scope(patched_client):
    client = patched_client(
        **{
            "music/search": {
                "playlists": [
                    {"uri": "spotify--x://playlist/1", "name": "Chill", "provider": "spotify--x"}
                ]
            }
        }
    )
    result = await search(query="chill")
    assert result == [
        {"name": "Chill", "media_type": "playlist", "provider": "spotify--x", "uri": "spotify--x://playlist/1"}
    ]
    search_calls = [c for c in client.calls if c[0] == "music/search"]
    assert len(search_calls) == 1
    assert search_calls[0][1]["providers"] == ["spotify--x"]
