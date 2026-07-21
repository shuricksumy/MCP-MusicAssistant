"""Thin, lazily-connected wrapper around the official `music-assistant-client`.

Every other module talks to Music Assistant only through `send()` here. Verified
against a live schema-31 server - see README "Verified against a real server" for the
connection race and command-name bugs that were found and fixed along the way.
"""

from __future__ import annotations

import asyncio
import logging

from music_assistant_client.client import MusicAssistantClient

from .config import settings

logger = logging.getLogger(__name__)

_RETRYABLE_ERRORS = (ConnectionError, ConnectionResetError, BrokenPipeError, OSError)


class MAClientError(RuntimeError):
    """Raised when Music Assistant can't be reached or a command fails."""


class MAClient:
    def __init__(self) -> None:
        self._client: MusicAssistantClient | None = None
        self._listen_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def _ensure_connected(self) -> MusicAssistantClient:
        if self._client is not None:
            return self._client

        async with self._lock:
            if self._client is not None:
                return self._client

            if not settings.ma_server_url:
                raise MAClientError(
                    "MA_SERVER_URL is not configured - set it in the environment/.env file"
                )

            client = MusicAssistantClient(
                settings.ma_server_url, aiohttp_session=None, token=settings.ma_token
            )
            # connect() raises directly here on auth/connection failure, synchronously,
            # before any background reader exists to race with it.
            await client.connect()

            # start_listening() re-enters connect() (a no-op, already connected) then
            # runs the read loop that dispatches responses to send_command()'s futures.
            # Without waiting for init_ready, a send() issued right after create_task()
            # could race the still-not-yet-listening client onto the old direct-read
            # fallback path, causing two concurrent readers on the same socket
            # (observed as ConnectionClosed) - so we block here until it's really live.
            init_ready = asyncio.Event()
            self._listen_task = asyncio.create_task(self._listen_forever(client, init_ready))
            try:
                await asyncio.wait_for(init_ready.wait(), timeout=15)
            except asyncio.TimeoutError as err:
                raise MAClientError("Timed out waiting for Music Assistant listen loop to start") from err

            self._client = client
            return client

    async def _listen_forever(self, client: MusicAssistantClient, init_ready: asyncio.Event) -> None:
        try:
            await client.start_listening(init_ready=init_ready)
        except Exception:  # noqa: BLE001 - background task, just drop the stale connection
            logger.exception("Music Assistant listen loop ended, will reconnect on next call")
        finally:
            if self._client is client:
                self._client = None

    async def send(self, command: str, **kwargs) -> object:
        """Send a raw Music Assistant WS command (e.g. "players/all"), one retry on drop."""
        client = await self._ensure_connected()
        try:
            return await client.send_command(command, **kwargs)
        except _RETRYABLE_ERRORS:
            logger.warning("Music Assistant connection dropped, reconnecting once for %s", command)
            self._client = None
            client = await self._ensure_connected()
            return await client.send_command(command, **kwargs)

    async def close(self) -> None:
        if self._listen_task is not None:
            self._listen_task.cancel()
        if self._client is not None:
            await self._client.disconnect()
        self._client = None


_ma_client = MAClient()


async def get_client() -> MAClient:
    return _ma_client
