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
                {"queue_id": "up1", "shuffle_enabled": False},
                {"queue_id": "up2", "shuffle_enabled": True},
            ],
            "player_queues/items": [{"name": "Track 1"}],
        }
    )
    result = await queue(player="Living Room", action="get")
    assert result["queue"] == {"queue_id": "up1", "shuffle_enabled": False}
    assert result["items"] == [{"name": "Track 1"}]


async def test_queue_shuffle_requires_bool(patched_client):
    patched_client()
    with pytest.raises(ValueError):
        await queue(player="Living Room", action="shuffle")


async def test_queue_shuffle_sends_command(patched_client):
    patched_client()
    result = await queue(player="Living Room", action="shuffle", shuffle=True)
    assert result == {"player": "Living Room", "shuffle": True}


async def test_queue_repeat_validates_mode(patched_client):
    patched_client()
    with pytest.raises(ValueError):
        await queue(player="Living Room", action="repeat", repeat="loop-forever")


async def test_queue_move_requires_item_id(patched_client):
    patched_client()
    with pytest.raises(ValueError):
        await queue(player="Living Room", action="move_up")


async def test_queue_move_up_sends_negative_shift(patched_client):
    patched_client()
    result = await queue(player="Living Room", action="move_up", item_id="item-5")
    assert result == {"player": "Living Room", "action": "move_up", "item_id": "item-5"}


async def test_queue_unknown_action_raises(patched_client):
    patched_client()
    with pytest.raises(ValueError):
        await queue(player="Living Room", action="teleport")


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
