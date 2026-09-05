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


def test_find_player_prefers_available_on_duplicate_exact_name():
    """Real server has an offline snapcast "LedFX" alongside the live squeezelite
    "LedFx"; list order used to hand back the dead one, so group/ungroup silently
    no-opped."""
    players = [
        players_logic.Player("ma_SnapLedFx", "LedFX", available=False),
        players_logic.Player("72:23:98:63:08:13", "LedFx", available=True),
    ]
    assert players_logic.find_player("ledfx", players).player_id == "72:23:98:63:08:13"
    assert players_logic.find_player("LedFx", players).player_id == "72:23:98:63:08:13"


def test_find_player_ambiguous_substring_resolves_to_only_available_one():
    """"DX3" hits both the live squeezelite player and its offline bluetooth twin;
    only one of them can actually do anything, so it is not really ambiguous."""
    players = [
        players_logic.Player("ma_DX3ProBT3", "DX3 Pro (BT)", available=False),
        players_logic.Player("72:23:90:14:08:63", "DX3 Pro", available=True),
    ]
    assert players_logic.find_player("DX3", players).player_id == "72:23:90:14:08:63"


def test_exact_name_still_beats_substring_even_if_unavailable():
    """Asking for exactly "DX3" must return the player named "DX3", not a longer
    available name that merely contains it."""
    players = [
        players_logic.Player("a", "DX3", available=False),
        players_logic.Player("c", "DX3 Pro", available=True),
    ]
    assert players_logic.find_player("DX3", players).player_id == "a"


def test_find_player_still_ambiguous_when_several_available():
    players = [
        players_logic.Player("a", "snapbox", available=True),
        players_logic.Player("b", "DOCK (snap)", available=True),
    ]
    assert players_logic.find_player("snap", players) is None


def test_find_player_falls_back_to_unavailable_when_none_available():
    players = [players_logic.Player("a", "LedFx", available=False)]
    assert players_logic.find_player("ledfx", players).player_id == "a"


def test_exact_id_wins_over_availability():
    players = [
        players_logic.Player("ma_SnapLedFx", "LedFX", available=False),
        players_logic.Player("72:23:98:63:08:13", "LedFx", available=True),
    ]
    assert players_logic.find_player("ma_SnapLedFx", players).player_id == "ma_SnapLedFx"


def test_from_raw_reads_availability():
    p = players_logic.Player.from_raw(
        {"player_id": "x", "display_name": "X", "available": False, "provider": "snapcast"}
    )
    assert p.available is False
    assert p.provider == "snapcast"
    # payloads without the field stay usable
    assert players_logic.Player.from_raw({"player_id": "y", "name": "Y"}).available is True


def test_player_not_found_error_flags_unavailable_players():
    players = [
        players_logic.Player("a", "Living Room", available=True),
        players_logic.Player("b", "Old Speaker", available=False),
    ]
    err = players_logic.PlayerNotFoundError("nope", players)
    assert "Old Speaker (unavailable)" in str(err)
    assert "Living Room," in str(err) or "Living Room " in str(err)
