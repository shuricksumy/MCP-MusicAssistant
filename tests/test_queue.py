import pytest

import music_assistant_mcp.tools.queue as queue_module
from music_assistant_mcp.tools.queue import queue

from fakes import FakeMAClient


@pytest.fixture
def patched_client(players_raw, monkeypatch):
    def _install(**extra_responses):
        client = FakeMAClient({"players/all": players_raw, **extra_responses})

        async def _fake_get_client():
            return client

        monkeypatch.setattr(queue_module, "get_client", _fake_get_client)
        return client

    return _install


async def test_queue_get_fetches_state_and_items(patched_client):
    patched_client(
        **{
            "player_queues/all": [
                {"queue_id": "up1", "shuffle_enabled": False, "state": "playing"},
                {"queue_id": "up2", "shuffle_enabled": True},
            ],
            "player_queues/items": [{"name": "Track 1", "media_item": {"name": "Track 1"}}],
        }
    )
    result = await queue(player="Living Room", action="get")
    assert result["queue"]["state"] == "playing"
    assert result["queue"]["shuffle"] is False
    assert result["queue"]["upcoming"] == [{"name": "Track 1", "artist": None, "album": None, "duration": None}]


async def test_queue_get_summarizes_current_and_next_track(patched_client):
    patched_client(
        **{
            "player_queues/all": [
                {
                    "queue_id": "up1",
                    "state": "playing",
                    "current_item": {
                        "name": "Sirens",
                        "duration": 161,
                        "media_item": {
                            "name": "Sirens",
                            "artists": [{"name": "Skepta"}, {"name": "Finessekid"}],
                            "album": {"name": "Sirens (From Ireland)"},
                            "images": [{"path": "https://example.com/big-image.jpg"}],
                        },
                    },
                    "next_item": {"name": "Take U A Army", "media_item": {"name": "Take U A Army"}},
                }
            ],
            "player_queues/items": [],
        }
    )
    result = await queue(player="Living Room", action="get")
    assert result["queue"]["current"] == {
        "name": "Sirens",
        "artist": "Skepta, Finessekid",
        "album": "Sirens (From Ireland)",
        "duration": 161,
    }
    assert result["queue"]["next"]["name"] == "Take U A Army"
    assert "images" not in str(result)


async def test_queue_shuffle_defaults_to_true_when_omitted(patched_client):
    patched_client()
    result = await queue(player="Living Room", action="shuffle")
    assert result == {"player": "Living Room", "shuffle": True}


async def test_queue_shuffle_sends_command(patched_client):
    patched_client()
    result = await queue(player="Living Room", action="shuffle", shuffle=True)
    assert result == {"player": "Living Room", "shuffle": True}


async def test_queue_shuffle_false_is_respected(patched_client):
    patched_client()
    result = await queue(player="Living Room", action="shuffle", shuffle=False)
    assert result == {"player": "Living Room", "shuffle": False}


async def test_queue_repeat_defaults_to_all_when_invalid(patched_client):
    patched_client()
    result = await queue(player="Living Room", action="repeat", repeat="loop-forever")
    assert result == {"player": "Living Room", "repeat": "all"}


async def test_queue_repeat_defaults_to_all_when_omitted(patched_client):
    patched_client()
    result = await queue(player="Living Room", action="repeat")
    assert result == {"player": "Living Room", "repeat": "all"}


async def test_queue_move_requires_item_id(patched_client):
    patched_client()
    with pytest.raises(ValueError):
        await queue(player="Living Room", action="move_up")


async def test_queue_move_up_sends_negative_shift(patched_client):
    patched_client()
    result = await queue(player="Living Room", action="move_up", item_id="item-5")
    assert result == {"player": "Living Room", "action": "move_up", "item_id": "item-5"}


async def test_queue_unknown_action_falls_back_to_get(patched_client):
    patched_client(
        **{
            "player_queues/all": [{"queue_id": "up1", "shuffle_enabled": False}],
            "player_queues/items": [],
        }
    )
    result = await queue(player="Living Room", action="teleport")
    assert result["queue"]["shuffle"] is False
    assert "note" in result


async def test_queue_move_next_sends_zero_shift(patched_client):
    client = patched_client()
    await queue(player="Living Room", action="move_next", item_id="item-5")
    command, kwargs = client.calls[-1]
    assert command == "player_queues/move_item"
    assert kwargs["pos_shift"] == 0


async def test_queue_remove_uses_item_id_or_index_kwarg(patched_client):
    client = patched_client()
    await queue(player="Living Room", action="remove", item_id="item-5")
    command, kwargs = client.calls[-1]
    assert command == "player_queues/delete_item"
    assert kwargs["item_id_or_index"] == "item-5"
    assert "queue_item_id" not in kwargs


async def test_queue_action_is_case_insensitive(patched_client):
    client = patched_client()
    await queue(player="Living Room", action="SHUFFLE", shuffle=True)
    command, kwargs = client.calls[-1]
    assert command == "player_queues/shuffle"
    assert kwargs["shuffle_enabled"] is True
