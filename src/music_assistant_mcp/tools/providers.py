from mcp.server import MCPServer as FastMCP

from .. import providers as providers_logic
from ..ma_client import get_client


def _provider_to_dict(p: providers_logic.ProviderInstance) -> dict:
    return {
        "instance_id": p.instance_id,
        "domain": p.domain,
        "name": p.name,
        "is_streaming": p.is_streaming,
    }


async def list_providers() -> list[dict]:
    """List configured music providers (Spotify, Tidal, local/SMB/WebDAV shares, ...)
    with whether each is a streaming ("online") or local file ("offline") provider.

    Only call this if the user asks what sources/providers are configured, or a
    `source`/`scope` value passed to `play`/`search` didn't match anything.
    """
    client = await get_client()
    provider_list = await providers_logic.list_providers(client)
    return [_provider_to_dict(p) for p in provider_list]


def register(mcp: FastMCP) -> None:
    mcp.tool()(list_providers)
