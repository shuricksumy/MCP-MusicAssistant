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
    scope: "online" (streaming providers only), "local" (file providers only), or "all"
        (search everywhere). Omitted -> defaults to "online", automatically broadening
        to everything if nothing turns up there. Ignored if `source` is given.
    """
    if not query or not query.strip():
        raise ValueError("query is required and can't be empty")

    client = await get_client()
    available_providers = await providers_logic.list_providers(client)

    used_default_scope = not source and not scope
    try:
        provider_filter = providers_logic.resolve_provider_filter(available_providers, source, scope)
    except providers_logic.ProviderNotFoundError:
        if not used_default_scope:
            raise
        provider_filter = None

    _, candidates = await search_and_pick(
        client, query, media_types=media_types, limit=limit, source=source, providers=provider_filter
    )
    if not candidates and used_default_scope and provider_filter is not None:
        _, candidates = await search_and_pick(
            client, query, media_types=media_types, limit=limit, source=source, providers=None
        )
    return [
        {"name": c.name, "media_type": c.media_type, "provider": c.provider, "uri": c.uri}
        for c in candidates
    ]


def register(mcp: FastMCP) -> None:
    mcp.tool()(search)
