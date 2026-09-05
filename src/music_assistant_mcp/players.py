"""Player lookup/resolution - the code-side replacement for the prompt's mandatory
"list players first, remember the player_id" step."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .config import settings
from .ma_client import MAClient


class PlayerNotFoundError(RuntimeError):
    def __init__(self, requested: str | None, available: list["Player"]):
        self.requested = requested
        self.available = available
        names = (
            ", ".join(f"{p.name} (unavailable)" if not p.available else p.name for p in available)
            or "(no players found)"
        )
        super().__init__(
            f"No player matches '{requested}'. Available players: {names}"
            if requested
            else f"No default player configured and none could be resolved. Available players: {names}"
        )


@dataclass(frozen=True)
class Player:
    player_id: str
    name: str
    powered: bool | None = None
    volume_level: int | None = None
    # MA reports offline/stale players as available=False. Default True so a payload
    # that omits the field (older servers, test fixtures) still behaves as before.
    available: bool = True
    provider: str | None = None
    # MA's own answer to "what can this player sync with", which is what its UI offers.
    # Empty for a player that is currently a group *child* - it can't host a group while
    # synced - so provider is still needed as a fallback.
    can_group_with: tuple[str, ...] = ()
    synced_to: str | None = None
    active_group: str | None = None

    @property
    def is_grouped(self) -> bool:
        return bool(self.synced_to or self.active_group)

    @classmethod
    def from_raw(cls, raw: dict) -> "Player":
        return cls(
            player_id=raw.get("player_id") or raw.get("id"),
            name=raw.get("display_name") or raw.get("name") or raw.get("player_id"),
            powered=raw.get("powered"),
            volume_level=raw.get("volume_level"),
            available=raw.get("available", True),
            provider=raw.get("provider"),
            can_group_with=tuple(raw.get("can_group_with") or ()),
            synced_to=raw.get("synced_to"),
            active_group=raw.get("active_group"),
        )


async def list_players(client: MAClient) -> list[Player]:
    raw_players = await client.send("players/all")
    return [Player.from_raw(p) for p in raw_players or []]


def _narrow(matches: list[Player], prefer: "Callable[[Player], bool] | None") -> Player | None:
    """Reduce same-tier matches to a single player, or None if still ambiguous.

    Tiers are tried narrowest-first: satisfies `prefer` and online, then satisfies
    `prefer`, then merely online. A tier with two survivors is genuinely ambiguous and
    no broader tier can fix that, so it stops rather than guessing.
    """
    tiers = []
    if prefer is not None:
        tiers.append([p for p in matches if prefer(p) and p.available])
        tiers.append([p for p in matches if prefer(p)])
    tiers.append([p for p in matches if p.available])
    for tier in tiers:
        if len(tier) == 1:
            return tier[0]
        if len(tier) > 1:
            return None
    return None


def find_player(
    name_or_id: str | None,
    players: list[Player],
    prefer: "Callable[[Player], bool] | None" = None,
) -> Player | None:
    """Exact id match, then case-insensitive exact name, then substring match.

    Within a tier, ties break towards `prefer` (if given) and then towards a player MA
    currently reports as available. Music Assistant keeps stale players around under the
    same (or a prefix-sharing) name as the live one - e.g. an offline snapcast "LedFX"
    next to the squeezelite "LedFx" that is actually wired up. Commands addressed to the
    offline twin are accepted and then silently do nothing, so picking it looks exactly
    like a broken tool.

    `prefer` is how the group tool keeps a request on one protocol: asking to sync
    "LedFx" into the squeezelite "DX3 Pro" has to resolve the squeezelite LedFx, never
    the identically-named snapcast one, since MA can only group players that share a
    protocol.
    """
    if not name_or_id:
        return None
    needle = name_or_id.strip().lower()
    for p in players:
        if p.player_id == name_or_id:
            return p

    exact = [p for p in players if p.name.lower() == needle]
    if exact:
        return _narrow(exact, prefer) or exact[0]

    matches = [p for p in players if needle in p.name.lower()]
    if len(matches) == 1:
        return matches[0]
    # An otherwise-ambiguous substring is unambiguous in practice once the wrong
    # protocol and the offline twins are ruled out (e.g. "DX3" across "DX3 Pro (BT)"
    # and "DX3 Pro").
    return _narrow(matches, prefer)


async def resolve_player(
    client: MAClient,
    name_or_id: str | None,
    players: list[Player] | None = None,
    prefer: "Callable[[Player], bool] | None" = None,
) -> Player:
    """Resolve a player by name/id, falling back to the configured default.

    Raises PlayerNotFoundError (listing what's actually available) instead of guessing,
    so the calling agent can relay a clear message instead of needing a prompt rule for it.

    `players` lets a caller resolving several names reuse one `players/all` fetch;
    `prefer` is passed through to find_player() to break ties (see there).
    """
    if players is None:
        players = await list_players(client)

    target = name_or_id or settings.default_player_name
    player = find_player(target, players, prefer=prefer)
    if player is not None:
        return player
    raise PlayerNotFoundError(name_or_id, players)
