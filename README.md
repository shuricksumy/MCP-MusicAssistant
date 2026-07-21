# Music Assistant MCP

A from-scratch MCP server for [Music Assistant](https://music-assistant.io/), designed
so an LLM agent needs almost no system prompt to drive it. Unlike raw/low-level MCP
tool sets, the orchestration an agent would otherwise have to be told to do every turn
(resolve a player, remember it, search before playing, apply a provider tiebreak, etc.)
is baked into the tools themselves:

- **`play`** — search + resolve player + provider tiebreak + play, in one call. Supports
  `scope="online"|"local"|"all"` to restrict to streaming providers (Spotify/Tidal/Apple
  - rich thematic/"vibe" search) vs local file providers (SMB/WebDAV/local dir - literal
  matching), or `source="tidal"`/`"my-nas-share"` to force one specific provider.
  `radio_mode=true` starts a continuous radio mix seeded from the match instead of
  playing it once.
- **`control`** — play/pause/stop/toggle/next/previous/seek.
- **`volume`** — level / relative adjust / mute, optionally group-wide.
- **`queue`** — get/shuffle/repeat/clear/move/remove, keyed off one player.
- **`transfer`** — move playback from one player to another.
- **`browse`** — walk a provider's library hierarchy.
- **`group`** — join/leave player groups (e.g. syncing a LedFX visualizer).
- **`search`** — raw lookup without playing (same `scope`/`source` params as `play`),
  for "what do you have for X" questions.
- **`list_players`** / **`list_providers`** — diagnostic/fallback only; other tools
  resolve players and providers themselves.

Serves over **Streamable HTTP** with a static bearer token, so it drops straight into
an MCP Client HTTP node (e.g. n8n) the same way the previous stdio-only community
server had to be bridged to get there.

## Setup

```bash
cp .env.example .env   # fill in MA_SERVER_URL, MCP_BEARER_TOKEN, etc.
uv sync                # or: pip install -e ".[dev]"
uv run music-assistant-mcp
```

The server listens on `MCP_HOST:MCP_PORT` (default `0.0.0.0:8005`) and exposes the MCP
endpoint at `/mcp`, requiring `Authorization: Bearer <MCP_BEARER_TOKEN>`.

### Config (`.env`)

| Variable | Purpose |
|---|---|
| `MA_SERVER_URL` | Music Assistant server, e.g. `http://192.168.1.50:8095` |
| `MA_TOKEN` | Music Assistant auth token (required on schema ≥ 28 servers) |
| `MCP_HOST` / `MCP_PORT` | This server's own bind address |
| `MCP_BEARER_TOKEN` | Shared secret clients must send as `Authorization: Bearer <token>` |
| `DEFAULT_PLAYER_NAME` | Used when a tool call doesn't name a player |
| `SOURCE_PRIORITY` | Comma-separated provider tiebreak order, e.g. `tidal,spotify,apple_music` |

### Adding to an MCP client config

Unlike the old community server (stdio-only, spawned per-connection via `uvx`), this
server is a standalone long-running HTTP service - the client connects to it over the
network instead of launching it. For any MCP host config that supports a remote/HTTP
server entry (Claude Desktop, Cursor, etc.), that looks like:

```json
{
  "mcpServers": {
    "music-assistant": {
      "enabled": true,
      "timeout": 60,
      "transportType": "http",
      "url": "http://<MCP_HOST>:<MCP_PORT>/mcp",
      "headers": {
        "Authorization": "Bearer <MCP_BEARER_TOKEN>"
      }
    }
  }
}
```

Replace `<MCP_HOST>:<MCP_PORT>` with wherever you're running this server (e.g.
`192.168.1.50:8005`) and `<MCP_BEARER_TOKEN>` with the value from your `.env`. There's
no `command`/`args`/`env` block like the old stdio config - the server must already be
running (`uv run music-assistant-mcp`) for the client to connect to.

## Wiring into n8n

Point the existing "Music MCP Client" node's endpoint at this server's `/mcp` URL with
the bearer credential set to `MCP_BEARER_TOKEN`. Because player resolution and the
provider tiebreak now live in the tools, the AI Agent's system prompt can shrink
drastically - no STEP-by-STEP sequencing, player-id tracking, or source-tiebreak rules
needed. See [PROMPT.md](PROMPT.md) for a suggested replacement (persona + the one policy,
confirming before a queue clear, that the tools don't enforce on their own).

## Development

```bash
uv run pytest
```

Tests cover the pure logic (player/provider resolution, source/scope tiebreak, queue
action dispatch) against a fake Music Assistant client.

### Verified against a real server (schema version 31)

All four end-to-end scenarios below were run against a live server and fixed until
green - the bugs found along the way are worth knowing about if you extend this further:

- **`play(query="Relaxing music", player="Living Room")`** — works.
- **`play(query="The Prodigy", player="Living Room", media_types=["artist"], radio_mode=True)`**
  — works. Found and fixed: a provider can return an irrelevant top "match" for an
  identity lookup (Tidal returned "Fatboy Slim" for "The Prodigy") - `pick_best()` now
  requires a name-match to the query for `artist`/`track`/`album` before applying source
  priority; playlists/radio stay priority-only since themed queries (e.g. "jazz vibes")
  legitimately won't literally match a provider's own curated name.
- **`play(query="Coldplay", player="Living Room", media_types=["artist"], scope="local")`**
  — works. Found and fixed: `music/search`'s `providers=` restriction is unreliable on
  this server (repeat identical requests sometimes returned every provider's results
  regardless of the filter) - `filter_by_providers()` now re-checks client-side, including
  matching a merged "library" item (`provider="library"`) via its `provider_mappings`.
- **`group(action="join", players=["LedFX"], target_player="Living Room")` then
  `group(action="leave", players=["LedFX"])`** — works. Found and fixed:
  `players/cmd/group_many` takes `child_player_ids`, not `player_ids`.

Other bugs found and fixed by cross-checking `music-assistant-client`'s source directly
(not just live-called): `music/search` groups results under **plural** keys
(`playlists`/`tracks`/`albums`/`artists`, `radio` stays singular) that don't match the
singular `media_types` request values; a search result's `provider` field is an
**instance id** like `spotify--9hcJiXgW`, not a plain domain, so the domain is now
derived via `provider.split("--", 1)[0]`; `player_queues/delete_item` takes
`item_id_or_index`, not `queue_item_id`; there's no `player_queues/get` command (`queue`'s
`"get"` action now fetches `player_queues/all` and filters); `music/browse` only takes
`path`, no `limit`/`offset` (removed from the `browse` tool); `MusicAssistantClient(...)`
requires `aiohttp_session` as a positional arg (pass `None`); and a startup race between
the background `start_listening()` read loop and the direct-read auth handshake caused
`ConnectionClosed` - `ma_client.py` now waits for `start_listening(init_ready=...)` to
signal ready before considering the client connected.

`radio_mode=True` is passed straight through as the `player_queues/play_media` flag
(not wrapped into a `radio_playlist://` URI) - confirmed live that this server's schema
(31) predates the schema-34 `radio_playlist` translation the client library does
internally, so the flag is what actually works here. If you're on schema ≥ 34, the flag
may no longer be honored and enqueuing `radio_playlist://playlist/<uri>` directly (per
`music_assistant_client.player_queues.radio_playlist_uri`) would be the thing to try.

### Still unverified
- `transfer` (`player_queues/transfer`) wasn't exercised in the live scenarios above.
- Local/offline scope was only tested against a `webdav` provider (this server's only
  non-streaming one) - a `filesystem_local`/`filesystem_smb`/`filesystem_nfs` share
  should classify the same way (`is_streaming_provider=False`) but wasn't tried directly.
