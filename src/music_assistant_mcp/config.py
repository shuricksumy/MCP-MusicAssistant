"""Environment-based settings, loaded once at import time."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class Settings:
    ma_server_url: str = field(default_factory=lambda: os.environ.get("MA_SERVER_URL", ""))
    ma_token: str | None = field(default_factory=lambda: os.environ.get("MA_TOKEN") or None)

    mcp_transport: str = field(
        default_factory=lambda: os.environ.get("MCP_TRANSPORT", "streamable-http")
    )
    mcp_host: str = field(default_factory=lambda: os.environ.get("MCP_HOST", "0.0.0.0"))
    mcp_port: int = field(default_factory=lambda: int(os.environ.get("MCP_PORT", "8005")))
    mcp_bearer_token: str | None = field(
        default_factory=lambda: os.environ.get("MCP_BEARER_TOKEN") or None
    )

    default_player_name: str | None = field(
        default_factory=lambda: os.environ.get("DEFAULT_PLAYER_NAME") or None
    )
    source_priority: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            _split_csv(os.environ.get("SOURCE_PRIORITY", "tidal,spotify,apple_music"))
        )
    )


settings = Settings()
