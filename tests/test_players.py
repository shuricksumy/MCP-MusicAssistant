import pytest

from music_assistant_mcp import players as players_logic
from music_assistant_mcp.config import settings


async def test_list_players_parses_raw(fake_client, players_raw):
    result = await players_logic.list_players(fake_client)
    assert [p.player_id for p in result] == [p["player_id"] for p in players_raw]
    assert result[0].name == "Living Room"
    assert result[0].powered is True


def test_find_player_exact_id():
    players = [players_logic.Player("up1", "Living Room"), players_logic.Player("up2", "Kitchen Speaker")]
    assert players_logic.find_player("up2", players).player_id == "up2"


def test_find_player_case_insensitive_exact_name():
    players = [players_logic.Player("up1", "Living Room")]
    assert players_logic.find_player("living room", players).player_id == "up1"


def test_find_player_unique_substring():
    players = [players_logic.Player("up1", "Living Room"), players_logic.Player("up2", "Kitchen Speaker")]
    assert players_logic.find_player("kitchen", players).player_id == "up2"


def test_find_player_ambiguous_substring_returns_none():
    players = [players_logic.Player("up1", "Living Room A"), players_logic.Player("up2", "Living Room B")]
    assert players_logic.find_player("living", players) is None


def test_find_player_no_match_returns_none():
    players = [players_logic.Player("up1", "Living Room")]
    assert players_logic.find_player("nonexistent", players) is None


async def test_resolve_player_uses_default_when_unspecified(fake_client, monkeypatch):
    monkeypatch.setattr(settings, "default_player_name", "Living Room")
    player = await players_logic.resolve_player(fake_client, None)
    assert player.player_id == "up1"


async def test_resolve_player_raises_with_available_list(fake_client):
    with pytest.raises(players_logic.PlayerNotFoundError) as exc_info:
        await players_logic.resolve_player(fake_client, "nonexistent")
    err = exc_info.value
    assert err.requested == "nonexistent"
    assert {p.name for p in err.available} == {"Living Room", "Kitchen Speaker", "LedFX Visualizer"}
