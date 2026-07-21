from mcp.server.fastmcp import FastMCP

from ..ma_client import get_client
from ..players import resolve_player

# pos_shift for player_queues/move_item: negative = up, positive = down, 0 = "play next"
# (confirmed against the music-assistant-client source, not just the WS command name).
_MOVE_SHIFT = {"move_up": -1, "move_down": 1, "move_next": 0}


async def queue(
    player: str | None = None,
    action: str = "get",
    shuffle: bool | None = None,
    repeat: str | None = None,
    item_id: str | None = None,
) -> dict:
    """Queue inspection and management for one player's queue.

    action:
      "get"        - return queue items and settings (default)
      "shuffle"    - set shuffle on/off, requires `shuffle` bool
      "repeat"     - set repeat mode, requires `repeat` in "off"|"one"|"all"
      "clear"      - clear the queue (confirm with the user first)
      "move_up" | "move_down" | "move_next" | "remove" - requires `item_id`
        (get it from action="get")
    """
    client = await get_client()
    resolved_player = await resolve_player(client, player)
    queue_id = resolved_player.player_id

    if action == "get":
        # there is no "player_queues/get" WS command - fetch all queues and pick ours.
        all_queues = await client.send("player_queues/all")
        queue_state = next((q for q in all_queues or [] if q.get("queue_id") == queue_id), None)
        items = await client.send("player_queues/items", queue_id=queue_id, limit=50)
        return {"player": resolved_player.name, "queue": queue_state, "items": items}

    if action == "shuffle":
        if shuffle is None:
            raise ValueError("action=shuffle requires the `shuffle` bool parameter")
        await client.send("player_queues/shuffle", queue_id=queue_id, shuffle_enabled=shuffle)
        return {"player": resolved_player.name, "shuffle": shuffle}

    if action == "repeat":
        if repeat not in ("off", "one", "all"):
            raise ValueError("action=repeat requires `repeat` in 'off'|'one'|'all'")
        await client.send("player_queues/repeat", queue_id=queue_id, repeat_mode=repeat)
        return {"player": resolved_player.name, "repeat": repeat}

    if action == "clear":
        await client.send("player_queues/clear", queue_id=queue_id)
        return {"player": resolved_player.name, "cleared": True}

    if action in _MOVE_SHIFT:
        if not item_id:
            raise ValueError(f"action={action} requires `item_id`")
        await client.send(
            "player_queues/move_item",
            queue_id=queue_id,
            queue_item_id=item_id,
            pos_shift=_MOVE_SHIFT[action],
        )
        return {"player": resolved_player.name, "action": action, "item_id": item_id}

    if action == "remove":
        if not item_id:
            raise ValueError("action=remove requires `item_id`")
        await client.send("player_queues/delete_item", queue_id=queue_id, item_id_or_index=item_id)
        return {"player": resolved_player.name, "removed": item_id}

    raise ValueError(
        f"Unknown action '{action}', expected one of: get, shuffle, repeat, clear, "
        "move_up, move_down, move_next, remove"
    )


def register(mcp: FastMCP) -> None:
    mcp.tool()(queue)
