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


@dataclass(frozen=True)
class ProviderInstance:
    instance_id: str
    domain: str
    name: str
    is_streaming: bool | None = None

    @classmethod
    def from_raw(cls, raw: dict) -> "ProviderInstance":
        return cls(
            instance_id=raw.get("instance_id") or raw.get("domain"),
            domain=raw.get("domain"),
            name=raw.get("name") or raw.get("domain"),
            is_streaming=raw.get("is_streaming_provider"),
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

    if scope in (None, "all"):
        return None

    if scope == "online":
        matches = [p for p in providers if p.is_streaming is True]
    elif scope == "local":
        matches = [p for p in providers if p.is_streaming is False]
    else:
        raise ValueError(f"scope must be 'online', 'local', or 'all', got '{scope}'")

    if not matches:
        raise ProviderNotFoundError(scope, providers)
    return [p.instance_id for p in matches]
