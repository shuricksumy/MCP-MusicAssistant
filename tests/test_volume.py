import pytest

import music_assistant_mcp.tools.volume as volume_module
from music_assistant_mcp.tools.volume import volume

from fakes import FakeMAClient


@pytest.fixture
def patched_client(players_raw, monkeypatch):
    def _install(**extra_responses):
        client = FakeMAClient({"players/all": players_raw, **extra_responses})

        async def _fake_get_client():
            return client

        monkeypatch.setattr(volume_module, "get_client", _fake_get_client)
        return client

    return _install


async def test_volume_no_params_returns_current_level_without_error(patched_client):
    patched_client()
    result = await volume(player="Living Room")
    assert result == {"player": "Living Room", "level": 40}


async def test_volume_level_sets_command(patched_client):
    client = patched_client()
    result = await volume(player="Living Room", level=55)
    assert result == {"player": "Living Room", "level": 55, "group": False}
    command, kwargs = client.calls[-1]
    assert command == "players/cmd/volume_set"
    assert kwargs["volume_level"] == 55


async def test_volume_level_clamped_to_valid_range(patched_client):
    client = patched_client()
    await volume(player="Living Room", level=500)
    _, kwargs = client.calls[-1]
    assert kwargs["volume_level"] == 100

    await volume(player="Living Room", level=-20)
    _, kwargs = client.calls[-1]
    assert kwargs["volume_level"] == 0


async def test_volume_group_level_uses_group_command(patched_client):
    client = patched_client()
    await volume(player="Living Room", level=30, group=True)
    command, _ = client.calls[-1]
    assert command == "players/cmd/group_volume"


async def test_volume_mute_sends_command(patched_client):
    client = patched_client()
    result = await volume(player="Living Room", mute=True)
    assert result == {"player": "Living Room", "mute": True}
    command, kwargs = client.calls[-1]
    assert command == "players/cmd/volume_mute"
    assert kwargs["muted"] is True


async def test_volume_group_mute_falls_back_to_single_player_with_note(patched_client):
    patched_client()
    result = await volume(player="Living Room", mute=True, group=True)
    assert result["mute"] is True
    assert "note" in result


async def test_volume_adjust_up_down(patched_client):
    client = patched_client()
    await volume(player="Living Room", adjust="up")
    command, _ = client.calls[-1]
    assert command == "players/cmd/volume_up"


async def test_volume_adjust_alias_maps_to_up(patched_client):
    client = patched_client()
    result = await volume(player="Living Room", adjust="louder")
    assert result["adjust"] == "up"
    command, _ = client.calls[-1]
    assert command == "players/cmd/volume_up"


async def test_volume_adjust_case_insensitive(patched_client):
    client = patched_client()
    await volume(player="Living Room", adjust="UP")
    command, _ = client.calls[-1]
    assert command == "players/cmd/volume_up"


async def test_volume_adjust_invalid_raises(patched_client):
    patched_client()
    with pytest.raises(ValueError):
        await volume(player="Living Room", adjust="sideways")
