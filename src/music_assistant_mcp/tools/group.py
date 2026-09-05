from mcp.server import MCPServer as FastMCP

from ..ma_client import get_client
from ..players import Player, list_players, resolve_player


def _groupable_with(target: Player):
    """Predicate for "this player can actually be synced into `target`".

    Grouping is a protocol-level feature - squeezelite syncs with squeezelite, snapcast
    with snapcast - and Music Assistant already publishes the answer per player as
    `can_group_with`, which is what its own UI offers. That list is empty for a player
    that is currently a group child (it can't host a group while synced), so fall back
    to matching the provider, which is the rule `can_group_with` encodes anyway.
    """
    if target.can_group_with:
        return lambda p: p.player_id in target.can_group_with
    return lambda p: p.provider is not None and p.provider == target.provider


def _incompatible(resolved: list[Player], target: Player) -> list[Player]:
    if target.can_group_with:
        return [p for p in resolved if p.player_id not in target.can_group_with]
    return [
        p
        for p in resolved
        if p.provider and target.provider and p.provider != target.provider
    ]


def _warnings(resolved: list[Player], target: Player | None) -> list[str]:
    """MA accepts group/ungroup commands it cannot carry out and then does nothing at
    all - no error, no state change. Without these the tool reports a confident success
    for a command that never happened."""
    notes = []
    offline = [p.name for p in [*resolved, *( [target] if target else [] )] if not p.available]
    if offline:
        notes.append(
            f"{', '.join(offline)} is not available in Music Assistant right now - the "
            "command was accepted but will not take effect until the player comes back online."
        )
    if target is not None and (bad := _incompatible(resolved, target)):
        notes.append(
            f"{', '.join(f'{p.name} ({p.provider})' for p in bad)} cannot be synced with "
            f"{target.name} ({target.provider}) - Music Assistant only groups players that "
            "share a protocol."
        )
    return notes


async def group(action: str, players: list[str], target_player: str | None = None) -> dict:
    """Group or ungroup players (e.g. syncing a LedFX visualizer player, or any speaker group).

    action: "join" - add `players` into `target_player`'s group (target defaults to the
            configured default player).
            "leave" - remove `players` from whatever group they're in.
    players: names/substrings of the player(s) to add or remove. Names are matched
        against players on the same protocol as `target_player`, so a name that exists
        on two providers (a squeezelite "LedFx" and a snapcast "LedFX") resolves to the
        one that can actually join the target.
    """
    client = await get_client()
    normalized_action = (action or "").strip().lower()
    if normalized_action not in ("join", "leave"):
        raise ValueError("action must be 'join' or 'leave'")

    # One fetch shared by every name below, so members are resolved against exactly the
    # same snapshot the target was picked from.
    all_players = await list_players(client)

    if normalized_action == "join":
        # The target is resolved first because it decides which protocol - and so which
        # of several same-named players - the members have to be.
        target = await resolve_player(client, target_player, players=all_players)
        prefer = _groupable_with(target)
        resolved = [
            await resolve_player(client, name, players=all_players, prefer=prefer)
            for name in players
        ]
        await client.send(
            "players/cmd/group_many",
            child_player_ids=[p.player_id for p in resolved],
            target_player=target.player_id,
        )
        result = {"action": "join", "players": [p.name for p in resolved], "target": target.name}
        notes = _warnings(resolved, target)
    else:
        # No target to key off, so prefer a player that is actually in a group - that's
        # the one a "leave" can possibly be about.
        resolved = [
            await resolve_player(
                client, name, players=all_players, prefer=lambda p: p.is_grouped
            )
            for name in players
        ]
        await client.send(
            "players/cmd/ungroup_many", player_ids=[p.player_id for p in resolved]
        )
        result = {"action": "leave", "players": [p.name for p in resolved]}
        notes = _warnings(resolved, None)

    if notes:
        result["warning"] = " ".join(notes)
    return result


def register(mcp: FastMCP) -> None:
    mcp.tool()(group)
