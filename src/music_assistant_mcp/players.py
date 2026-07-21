"""Player lookup/resolution - the code-side replacement for the prompt's mandatory
"list players first, remember the player_id" step."""

from __future__ import annotations

from dataclasses import dataclass

from .config import settings
from .ma_client import MAClient


class PlayerNotFoundError(RuntimeError):
    def __init__(self, requested: str | None, available: list["Player"]):
        self.requested = requested
        self.available = available
        names = ", ".join(p.name for p in available) or "(no players found)"
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

    @classmethod
    def from_raw(cls, raw: dict) -> "Player":
        return cls(
            player_id=raw.get("player_id") or raw.get("id"),
            name=raw.get("display_name") or raw.get("name") or raw.get("player_id"),
            powered=raw.get("powered"),
            volume_level=raw.get("volume_level"),
        )


async def list_players(client: MAClient) -> list[Player]:
    raw_players = await client.send("players/all")
    return [Player.from_raw(p) for p in raw_players or []]


def find_player(name_or_id: str | None, players: list[Player]) -> Player | None:
    """Exact id match, then case-insensitive exact name, then substring match."""
    if not name_or_id:
        return None
    needle = name_or_id.strip().lower()
    for p in players:
        if p.player_id == name_or_id:
            return p
    for p in players:
        if p.name.lower() == needle:
            return p
    matches = [p for p in players if needle in p.name.lower()]
    if len(matches) == 1:
        return matches[0]
    return None


async def resolve_player(client: MAClient, name_or_id: str | None) -> Player:
    """Resolve a player by name/id, falling back to the configured default.

    Raises PlayerNotFoundError (listing what's actually available) instead of guessing,
    so the calling agent can relay a clear message instead of needing a prompt rule for it.
    """
    players = await list_players(client)

    target = name_or_id or settings.default_player_name
    player = find_player(target, players)
    if player is not None:
        return player
    raise PlayerNotFoundError(name_or_id, players)
