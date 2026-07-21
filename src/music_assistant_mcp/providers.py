"""Provider lookup/classification - lets tools scope search to online streaming
providers (Spotify/Tidal/Apple) vs local/offline file providers (SMB/WebDAV/local dir)."""

from __future__ import annotations

from dataclasses import dataclass

from .ma_client import MAClient


class ProviderNotFoundError(RuntimeError):
    def __init__(self, requested: str, available: list["ProviderInstance"]):
        self.requested = requested
        self.available = available
        names = ", ".join(p.name for p in available) or "(no providers found)"
        super().__init__(f"No provider matches '{requested}'. Available providers: {names}")


_RADIO_FEATURES = {"similar_tracks", "similar_artists"}


@dataclass(frozen=True)
class ProviderInstance:
    instance_id: str
    domain: str
    name: str
    is_streaming: bool | None = None
    supported_features: frozenset[str] = frozenset()

    @classmethod
    def from_raw(cls, raw: dict) -> "ProviderInstance":
        return cls(
            instance_id=raw.get("instance_id") or raw.get("domain"),
            domain=raw.get("domain"),
            name=raw.get("name") or raw.get("domain"),
            is_streaming=raw.get("is_streaming_provider"),
            supported_features=frozenset(raw.get("supported_features") or ()),
        )


async def list_providers(client: MAClient) -> list[ProviderInstance]:
    raw_providers = await client.send("providers")
    return [
        ProviderInstance.from_raw(p) for p in raw_providers or [] if p.get("type") == "music"
    ]


def resolve_provider_filter(
    providers: list[ProviderInstance], source: str | None, scope: str | None
) -> list[str] | None:
    """Returns instance_ids to pass as music/search's `providers=` kwarg, or None for
    no restriction (search everything, today's default behavior)."""
    if source:
        needle = source.strip().lower()
        matches = [
            p
            for p in providers
            if needle in p.domain.lower()
            or needle in p.instance_id.lower()
            or needle in p.name.lower()
        ]
        if not matches:
            raise ProviderNotFoundError(source, providers)
        return [p.instance_id for p in matches]

    normalized_scope = (scope or "all").strip().lower()
    if normalized_scope == "all":
        return None

    if normalized_scope == "online":
        matches = [p for p in providers if p.is_streaming is True]
    elif normalized_scope == "local":
        matches = [p for p in providers if p.is_streaming is False]
    else:
        raise ValueError(f"scope must be 'online', 'local', or 'all', got '{scope}'")

    if not matches:
        raise ProviderNotFoundError(scope, providers)
    return [p.instance_id for p in matches]


def supports_radio(
    providers: list[ProviderInstance],
    media_type: str,
    provider_ids: tuple[str, ...],
    allowed_instance_ids: list[str] | None,
) -> bool:
    """Whether a radio/similar-tracks mix can plausibly be generated for this item.

    Confirmed against a live server: local file providers (e.g. webdav) don't report
    `similar_tracks`/`similar_artists` at all, so requesting radio_mode for an item only
    backed by those never produces an actual dynamic mix - this lets `play()` detect
    that and fall back to a normal (single) play instead of silently no-oping.
    `allowed_instance_ids` restricts the check to the scope/source actually requested
    (e.g. scope="local" shouldn't pass because a cross-provider library item also
    happens to have an unused online backing).
    """
    if media_type not in ("artist", "track"):
        return False

    candidate_ids = set(provider_ids)
    if allowed_instance_ids is not None:
        candidate_ids &= set(allowed_instance_ids)

    by_id = {p.instance_id: p for p in providers}
    return any(
        by_id[pid].supported_features & _RADIO_FEATURES for pid in candidate_ids if pid in by_id
    )
