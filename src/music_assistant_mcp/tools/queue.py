from mcp.server.fastmcp import FastMCP

from ..ma_client import get_client
from ..players import resolve_player

# pos_shift for player_queues/move_item: negative = up, positive = down, 0 = "play next"
# (confirmed against the music-assistant-client source, not just the WS command name).
_MOVE_SHIFT = {"move_up": -1, "move_down": 1, "move_next": 0}
_VALID_REPEAT = {"off", "one", "all"}
_KNOWN_ACTIONS = {"get", "shuffle", "repeat", "clear", "remove", *_MOVE_SHIFT}


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
      "shuffle"    - set shuffle on/off; `shuffle` bool omitted -> defaults to True (on)
      "repeat"     - set repeat mode; `repeat` in "off"|"one"|"all", omitted/unrecognized
        -> defaults to "all"
      "clear"      - clear the queue (confirm with the user first)
      "move_up" | "move_down" | "move_next" | "remove" - requires `item_id`
        (get it from action="get")

    An unrecognized `action` falls back to "get" rather than failing.
    """
    client = await get_client()
    resolved_player = await resolve_player(client, player)
    queue_id = resolved_player.player_id

    normalized_action = (action or "get").strip().lower()

    if normalized_action == "get" or normalized_action not in _KNOWN_ACTIONS:
        # there is no "player_queues/get" WS command - fetch all queues and pick ours.
        all_queues = await client.send("player_queues/all")
        queue_state = next((q for q in all_queues or [] if q.get("queue_id") == queue_id), None)
        items = await client.send("player_queues/items", queue_id=queue_id, limit=50)
        result = {"player": resolved_player.name, "queue": queue_state, "items": items}
        if normalized_action not in _KNOWN_ACTIONS:
            result["note"] = f"unrecognized action '{action}', returned queue state instead"
        return result

    if normalized_action == "shuffle":
        shuffle_enabled = True if shuffle is None else shuffle
        await client.send(
            "player_queues/shuffle", queue_id=queue_id, shuffle_enabled=shuffle_enabled
        )
        return {"player": resolved_player.name, "shuffle": shuffle_enabled}

    if normalized_action == "repeat":
        normalized_repeat = (repeat or "all").strip().lower()
        if normalized_repeat not in _VALID_REPEAT:
            normalized_repeat = "all"
        await client.send("player_queues/repeat", queue_id=queue_id, repeat_mode=normalized_repeat)
        return {"player": resolved_player.name, "repeat": normalized_repeat}

    if normalized_action == "clear":
        await client.send("player_queues/clear", queue_id=queue_id)
        return {"player": resolved_player.name, "cleared": True}

    if normalized_action in _MOVE_SHIFT:
        if not item_id:
            raise ValueError(f"action={normalized_action} requires `item_id`")
        await client.send(
            "player_queues/move_item",
            queue_id=queue_id,
            queue_item_id=item_id,
            pos_shift=_MOVE_SHIFT[normalized_action],
        )
        return {"player": resolved_player.name, "action": normalized_action, "item_id": item_id}

    if not item_id:
        raise ValueError("action=remove requires `item_id`")
    await client.send("player_queues/delete_item", queue_id=queue_id, item_id_or_index=item_id)
    return {"player": resolved_player.name, "removed": item_id}


def register(mcp: FastMCP) -> None:
    mcp.tool()(queue)
