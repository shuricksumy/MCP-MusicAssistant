"""Grouping has to stay on one protocol: Music Assistant only syncs players that share
a provider, and this server really does have a squeezelite "LedFx" next to an offline
snapcast "LedFX"."""

import pytest

import music_assistant_mcp.tools.group as group_module
from music_assistant_mcp.tools.group import group

from fakes import FakeMAClient

DX3 = "72:23:90:14:08:63"
LEDFX_SQ = "72:23:98:63:08:13"
LEDFX_SNAP = "ma_SnapLedFx"
DOCK_SNAP = "ma_DOCKsnap"

# Trimmed from the live server (MA 2.10.2, schema 65).
REAL_PLAYERS = [
    {
        "player_id": DX3,
        "display_name": "DX3 Pro",
        "provider": "squeezelite",
        "available": True,
        "can_group_with": ["ee:d7:55:0e:23:ee", LEDFX_SQ],
    },
    {
        "player_id": LEDFX_SQ,
        "display_name": "LedFx",
        "provider": "squeezelite",
        "available": True,
        "can_group_with": ["ee:d7:55:0e:23:ee", DX3],
    },
    {
        "player_id": LEDFX_SNAP,
        "display_name": "LedFX",
        "provider": "snapcast",
        "available": False,
        "can_group_with": [DOCK_SNAP],
    },
    {
        "player_id": DOCK_SNAP,
        "display_name": "DOCK (snap)",
        "provider": "snapcast",
        "available": True,
        "can_group_with": [],
    },
    {
        "player_id": "ma_DX3ProBT3",
        "display_name": "DX3 Pro (BT)",
        "provider": "snapcast",
        "available": False,
        "can_group_with": [DOCK_SNAP],
    },
]


@pytest.fixture
def patched_client(monkeypatch):
    def _install(players=None):
        client = FakeMAClient({"players/all": players if players is not None else REAL_PLAYERS})

        async def _fake_get_client():
            return client

        monkeypatch.setattr(group_module, "get_client", _fake_get_client)
        return client

    return _install


def _sent(client, command):
    return next(kwargs for cmd, kwargs in client.calls if cmd == command)


async def test_join_resolves_members_on_the_targets_protocol(patched_client):
    """"DX3" is squeezelite, so "LedFx" must resolve to the squeezelite one."""
    client = patched_client()
    result = await group(action="join", players=["LedFx"], target_player="DX3")
    assert _sent(client, "players/cmd/group_many") == {
        "child_player_ids": [LEDFX_SQ],
        "target_player": DX3,
    }
    assert "warning" not in result


async def test_join_on_snapcast_target_picks_the_snapcast_twin(patched_client):
    """Same name, other protocol: a snapcast target must pull the snapcast LedFX even
    though it is the offline one - and say so."""
    client = patched_client()
    result = await group(action="join", players=["LedFx"], target_player="DOCK (snap)")
    assert _sent(client, "players/cmd/group_many")["child_player_ids"] == [LEDFX_SNAP]
    assert "not available" in result["warning"]


async def test_join_prefers_protocol_over_availability(patched_client):
    """Availability breaks ties, but never at the cost of crossing protocols: the
    snapcast LedFX here is the online one and still must not join a squeezelite group."""
    players = [dict(p) for p in REAL_PLAYERS]
    for p in players:
        if p["player_id"] == LEDFX_SNAP:
            p["available"] = True
    client = patched_client(players)
    await group(action="join", players=["LedFx"], target_player="DX3")
    assert _sent(client, "players/cmd/group_many")["child_player_ids"] == [LEDFX_SQ]


async def test_join_warns_when_member_cannot_share_a_group(patched_client):
    """An unambiguous name on the wrong protocol still resolves, but MA would silently
    do nothing, so the mismatch has to be reported."""
    client = patched_client()
    result = await group(action="join", players=["DOCK (snap)"], target_player="DX3")
    assert _sent(client, "players/cmd/group_many")["child_player_ids"] == [DOCK_SNAP]
    assert "only groups players that share a protocol" in result["warning"]


async def test_join_falls_back_to_provider_when_can_group_with_is_empty(patched_client):
    """A player that is currently a group child reports can_group_with=[]; provider is
    then the only signal left."""
    players = [dict(p) for p in REAL_PLAYERS]
    for p in players:
        if p["player_id"] == DX3:
            p["can_group_with"] = []
    client = patched_client(players)
    result = await group(action="join", players=["LedFx"], target_player="DX3")
    assert _sent(client, "players/cmd/group_many")["child_player_ids"] == [LEDFX_SQ]
    assert "warning" not in result


async def test_leave_prefers_the_player_actually_in_a_group(patched_client):
    players = [dict(p) for p in REAL_PLAYERS]
    for p in players:
        if p["player_id"] == LEDFX_SQ:
            p["synced_to"] = DX3
    client = patched_client(players)
    result = await group(action="leave", players=["LedFx"])
    assert _sent(client, "players/cmd/ungroup_many") == {"player_ids": [LEDFX_SQ]}
    assert "warning" not in result


async def test_join_resolves_target_by_substring_and_reports_real_names(patched_client):
    patched_client()
    result = await group(action="join", players=["ledfx"], target_player="DX3")
    assert result["target"] == "DX3 Pro"
    assert result["players"] == ["LedFx"]


async def test_players_are_resolved_from_a_single_players_all_fetch(patched_client):
    client = patched_client()
    await group(action="join", players=["LedFx", "DOCK (snap)"], target_player="DX3")
    assert [cmd for cmd, _ in client.calls].count("players/all") == 1


async def test_invalid_action_rejected_before_any_command(patched_client):
    client = patched_client()
    with pytest.raises(ValueError, match="join.*leave"):
        await group(action="sync", players=["LedFx"], target_player="DX3")
    assert not [cmd for cmd, _ in client.calls if cmd.startswith("players/cmd")]
