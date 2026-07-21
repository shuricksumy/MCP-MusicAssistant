from mcp.server.fastmcp import FastMCP

from .. import providers as providers_logic
from ..ma_client import get_client
from ..search import search_and_pick


async def search(
    query: str,
    media_types: list[str] | None = None,
    limit: int = 15,
    source: str | None = None,
    scope: str | None = None,
) -> list[dict]:
    """Raw search, returned without playing anything - use `play` instead unless the
    user just wants to know what's available. media_types defaults to ["playlist"].

    source: name/substring of one specific provider (e.g. "tidal", "my-nas-share").
    scope: "online" (streaming providers only), "local" (file providers only), or
        "all" (default). Ignored if `source` is given.
    """
    client = await get_client()
    available_providers = await providers_logic.list_providers(client)
    provider_filter = providers_logic.resolve_provider_filter(available_providers, source, scope)

    _, candidates = await search_and_pick(
        client, query, media_types=media_types, limit=limit, source=source, providers=provider_filter
    )
    return [
        {"name": c.name, "media_type": c.media_type, "provider": c.provider, "uri": c.uri}
        for c in candidates
    ]


def register(mcp: FastMCP) -> None:
    mcp.tool()(search)
