# Music Assistant MCP

> Talk to your home audio system like a person, not an API.

| You say | What happens |
|---|---|
| "Play something relaxing" | Searches streaming playlists, picks the best match, plays it on the default player - no player id, no source picking |
| "Play some jazz for a romantic dinner" | Mood/occasion query → finds a fitting playlist automatically, same as a human browsing Spotify would |
| "Play The Prodigy in radio mode" | Resolves the artist, checks the *actual* provider can generate a mix before starting one, so it never silently no-ops |
| "Play Coldplay from my local files" | Scopes the search to just the local/NAS library, skipping streaming entirely |
| "Surprise me" | Builds an ad-hoc mix straight from the library - no search query needed at all |
| "Join the LedFX player while this plays, then take it back out" | Groups/ungroups players on request |

One line of natural language in, the right thing playing out - every scenario above is
tested against a real Music Assistant server, not just plausible-sounding docs (see
[Verified against a real server](#verified-against-a-real-server-schema-version-31)
below for the bugs that were actually found and fixed getting there).

A from-scratch MCP server for [Music Assistant](https://music-assistant.io/), designed
so an LLM agent needs almost no system prompt to drive it. Unlike raw/low-level MCP
tool sets, the orchestration an agent would otherwise have to be told to do every turn
(resolve a player, remember it, search before playing, apply a provider tiebreak, etc.)
is baked into the tools themselves:

- **`play`** — search + resolve player + provider tiebreak + play, in one call. Supports
  `scope="online"|"local"|"all"` to restrict to streaming providers (Spotify/Tidal/Apple
  - rich thematic/"vibe" search) vs local file providers (SMB/WebDAV/local dir - literal
  matching), or `source="tidal"`/`"my-nas-share"` to force one specific provider. Omitted
  `scope` defaults to "online" (broadening to everything if nothing turns up there), and
  `media_types` defaults to `["playlist"]` - so "play something relaxing"/"play jazz"
  naturally searches streaming playlists first, same as a human would.
  `radio_mode=true` starts a continuous radio mix seeded from the match instead of
  playing it once. If the top match turns out unplayable (e.g. an empty playlist), it
  automatically tries the next candidate before giving up.
- **`play_random`** — build and play a random mix straight from the library, no search
  query needed - for "play something"/"surprise me"/"random mix from my local files"
  requests. Same `scope`/`source` params as `play` (default `scope="all"` here, since
  there's no query to search "online" against - the point is usually to surface your
  own library).
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
cp .env.example .env   # fill in MA_SERVER_URL, MCP_BEARER_TOKEN, DEFAULT_PLAYER_NAME, etc.
uv sync                # or: pip install -e ".[dev]"
uv run music-assistant-mcp
```

`DEFAULT_PLAYER_NAME` isn't optional in practice - leave it unset and any tool call that
doesn't explicitly name a player fails with `No default player configured and none
could be resolved` (confirmed live). Set it to a name from `list_players`' output (e.g.
`"Living Room"`), not a player id.

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
| `MCP_TRANSPORT` | `streamable-http` (default, for n8n etc.) or `stdio` (for hosts that spawn this as a local subprocess - see below); `MCP_HOST`/`MCP_PORT`/`MCP_BEARER_TOKEN` are ignored in `stdio` mode |

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
`192.168.1.50:8005`) and `<MCP_BEARER_TOKEN>` with the value from your `.env`. This
requires the server to already be running (`uv run music-assistant-mcp`, or in Docker
below) - unlike the `command`/`args`/`env` style below, nothing gets spawned here.

### Running via uvx straight from GitHub (stdio)

If your MCP host only supports the `command`/`args`/`env`, stdio-launched style of
config (the same shape the old community server used), set `MCP_TRANSPORT=stdio` and
it works the same way - no bearer token needed, since the host owns the process's
stdio pipes directly instead of talking to it over the network:

```json
{
  "mcpServers": {
    "music-assistant": {
      "enabled": true,
      "timeout": 60,
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/shuricksumy/MCP-MusicAssistant",
        "music-assistant-mcp"
      ],
      "env": {
        "MA_SERVER_URL": "http://<MA_SERVER_IP>:8095",
        "MA_TOKEN": "<your-ma-token>",
        "MCP_TRANSPORT": "stdio",
        "DEFAULT_PLAYER_NAME": "<your-default-player-name>",
        "SOURCE_PRIORITY": "tidal,spotify,apple_music"
      },
      "transportType": "stdio"
    }
  }
}
```

`DEFAULT_PLAYER_NAME` matters here more than it does for n8n: without it, every `play`/
`control`/`volume`/etc. call that doesn't explicitly name a player fails with `No
default player configured and none could be resolved` (confirmed live) - the whole
point of the tools resolving players themselves falls apart if there's nothing to fall
back to. Set it to one of the names `list_players` returns (e.g. `"Living Room"`, not a
player id). `SOURCE_PRIORITY` is optional but worth setting explicitly since its
built-in default (`tidal,spotify,apple_music`) may not match the providers you actually
have configured.

Confirmed working locally: piping a real `initialize` request into
`MCP_TRANSPORT=stdio uv run music-assistant-mcp` returns a clean JSON-RPC response on
stdout with nothing else mixed in (logging goes to stderr, so it won't corrupt the
protocol stream).

### Running in Docker

```bash
docker build -t music-assistant-mcp .
docker run -d --name music-assistant-mcp -p 8005:8005 \
  -e MA_SERVER_URL=http://192.168.1.50:8095 \
  -e MA_TOKEN=<your-ma-token> \
  -e MCP_BEARER_TOKEN=<your-mcp-bearer-token> \
  -e DEFAULT_PLAYER_NAME=<your-default-player-name> \
  music-assistant-mcp
```

Built and run-tested (`docker build` + `docker run` + a bearer-authed MCP `initialize`
call) as part of this repo's verification.

### Using mcp-proxy (for hosts that only support stdio-launched servers)

Some MCP hosts only support the `command`/`args`/`env`, stdio-launch style of config
(like the old community server's `uvx --from git+...` entry) and can't point at a
remote HTTP URL directly. For those, use [`mcp-proxy`](https://github.com/sparfenyuk/mcp-proxy)
as a local stdio↔HTTP bridge in front of this server running in its container:

```json
{
  "mcpServers": {
    "music-assistant": {
      "enabled": true,
      "timeout": 60,
      "command": "uvx",
      "args": [
        "mcp-proxy",
        "--transport",
        "streamablehttp",
        "--headers",
        "Authorization",
        "Bearer <MCP_BEARER_TOKEN>",
        "http://<MCP_HOST>:<MCP_PORT>/mcp"
      ],
      "transportType": "stdio"
    }
  }
}
```

The container (or `uv run music-assistant-mcp` on bare metal) still has to be running
and reachable at `<MCP_HOST>:<MCP_PORT>` - `mcp-proxy` only bridges the host's stdio
expectation to it, it doesn't start the server itself.

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

### radio_mode capability gating

Checked live against each configured provider's actual `supported_features`: only
providers reporting `similar_tracks`/`similar_artists` (Spotify, Tidal, Apple Music on
this server) can generate an actual radio mix - `webdav` (the only local/offline
provider here) reports neither. Requesting `radio_mode=True` for something MA can't
generate a mix for (a local-only pick, or any playlist/album/radio-station media type,
since those have no "similar tracks" concept at all) used to silently send the flag
anyway and just play normally with no indication anything was skipped. `play()` now
checks `providers_logic.supports_radio()` before honoring the flag and returns
`radio_mode: false` plus an explanatory `note` when it had to fall back, instead of
quietly no-op'ing. Verified live: stays `true` for a Spotify artist, correctly falls
back with a note for a Tidal playlist and for a local/webdav-backed artist.

### Lenient defaults (agent-mistake tolerant)

Per a request to make sure a forgotten/wrong parameter never turns into a hard "bad
request" - audited every tool for this and fixed the gaps:
- `play`/`search`: unrecognized `media_types` entries (plurals, "song", typos) are
  mapped to the right value or dropped, falling back to `["playlist"]` if nothing valid
  remains; `option` falls back to `"play"` if not one of the four valid values.
- `control`: `command` is case-insensitive and accepts a few synonyms (`resume`, `skip`,
  `prev`, ...); anything still unrecognized falls back to `"play"` (with a `note`)
  instead of raising. `seek_seconds` is clamped to ≥ 0.
- `volume`: calling with none of `level`/`adjust`/`mute` set now just reports the
  current level instead of erroring; `level` is clamped to 0-100; `adjust` is
  case-insensitive and accepts synonyms (`louder`, `quieter`, ...); `group=true` with
  `mute` no longer errors - it just mutes the single player and notes why.
- `queue`: an unrecognized `action` falls back to `"get"` (with a `note`) instead of
  raising; `action="shuffle"` without a `shuffle` bool defaults to `True`;
  `action="repeat"` without a valid `repeat` value defaults to `"all"`; `action` is
  case-insensitive.
- `group`: `action` is case-insensitive.

Left as hard errors (genuinely ambiguous, no safe default exists): `volume` given more
than one of `level`/`adjust`/`mute` at once; `queue`'s `move_up`/`move_down`/
`move_next`/`remove` without `item_id` (no safe guess for *which* item); `group`'s
`action` if it's neither `join` nor `leave` (opposite operations, shouldn't guess).

### Human-request simulation (default scope + quality fixes)

Simulated realistic requests live against the real server - mood/occasion queries
("relaxing", "romantic evening", "dinner vibe", "jazz"), specific artist/track/album
lookups, explicit `source`/`scope`, and a query-less "surprise me" - to check how the
tools actually behave for a human, not just whether they run without erroring. Found
and fixed:

- **Default scope was "all" (online + local mixed together)**, which doesn't match how
  a human expects "play something"/"play `<artist>`" to behave (reach for a streaming
  service first). Changed the default to **"online"**, automatically broadening to
  everything (`scope="all"` semantics) if nothing turns up there - so a local-only match
  still gets found without asking for it by name, but a home NAS full of oddly-named
  files doesn't get preferred over Spotify/Tidal by default. Explicit `scope="all"` /
  `"local"` / `"online"` is still respected exactly, no fallback applied.
- **A nonsense query could still "confidently" play something unrelated** - e.g.
  searching the literal gibberish `"asdkfjhqwoeiuasdf"` as an artist returned an
  unrelated real artist, because the Tidal/Spotify/Apple priority tiebreak among
  *equally unmatched* candidates always picks one of them. `pick_best()` now returns no
  match at all (not just "wrong match") for artist/track/album lookups where nothing
  genuinely matched the query by name, so `play()` correctly reports "no results" instead
  of playing something wrong.
- **An empty/blank `query` returned garbage** (a local playlist's raw file listing, not
  a real search result) instead of failing clearly. `play`/`search` now reject an
  empty query outright, and `play`'s error message points at `play_random` for the
  query-less "surprise me" case.
- **A matched item could still be genuinely unplayable** (confirmed live: a same-named
  local "Jazz" playlist that turned out to be empty) - `player_queues/play_media`
  raising `MediaNotFoundError`/`UnplayableMediaError` used to fail the whole call.
  `play()` now automatically tries the next candidate (up to 3) before giving up, and
  reports which ones got skipped in a `note`.
- **New `play_random` tool**, backed by `music/tracks/library_items` with
  `order_by="random"` (a real server-side capability, confirmed - not client-side
  shuffling of a search result) - lets "play something from my local library"/"surprise
  me" build an ad-hoc mix without needing any search query at all.

### Still unverified
- `transfer` (`player_queues/transfer`) wasn't exercised in the live scenarios above.
- Local/offline scope was only tested against a `webdav` provider (this server's only
  non-streaming one) - a `filesystem_local`/`filesystem_smb`/`filesystem_nfs` share
  should classify the same way (`is_streaming_provider=False`) but wasn't tried directly.
