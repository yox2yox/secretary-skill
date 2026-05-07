"""Collection planning and saving commands for agent-mediated MCP imports."""

import json
from datetime import datetime, timezone

from db import get_connection, ensure_schema, seed_defaults
from items_mod import _insert_item


SERVICES = ("notion", "slack")
STREAMS = ("own_posts", "mentions")
DEFAULT_LIMIT = 50


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_dt(value):
    if not value:
        return None
    if not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _timestamp_sort_key(value):
    dt = _parse_dt(value)
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _max_timestamp(*values):
    present = [value for value in values if value]
    if not present:
        return None

    parsed = [(value, _timestamp_sort_key(value)) for value in present]
    parseable = [(value, dt) for value, dt in parsed if dt is not None]
    if not parseable:
        return None
    return max(parseable, key=lambda pair: pair[1])[0]


def _validate_service(value):
    if value == "all":
        return SERVICES
    if value in SERVICES:
        return (value,)
    raise ValueError(f"Unsupported collect service: {value}")


def _load_payload(data_json):
    data = json.loads(data_json)
    if isinstance(data, list):
        return {"items": data}
    if not isinstance(data, dict):
        raise ValueError("collect save payload must be a JSON object or array")
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("collect save payload must include an items array")
    return data


def _validate_item(item):
    if not isinstance(item, dict):
        raise ValueError("Each collected item must be a JSON object")

    service = item.get("service")
    stream = item.get("stream")
    source_id = item.get("source_id")

    if service not in SERVICES:
        raise ValueError(f"Unsupported collect service: {service}")
    if stream not in STREAMS:
        raise ValueError(f"Unsupported collect stream: {stream}")
    if not source_id or not isinstance(source_id, str):
        raise ValueError("Collected item is missing required string field: source_id")
    if not item.get("title") and not item.get("content"):
        raise ValueError("Collected item must include title or content")
    for field in ("source_created_at", "source_updated_at"):
        value = item.get(field)
        if value in (None, ""):
            continue
        if not isinstance(value, str) or _timestamp_sort_key(value) is None:
            raise ValueError(f"Collected item field {field} must be a parseable ISO 8601 timestamp")


def _source_timestamp(item):
    return item.get("source_updated_at") or item.get("source_created_at")


def _item_data(item):
    data = {
        "service": item["service"],
        "stream": item["stream"],
        "source_id": item["source_id"],
        "source_url": item.get("source_url", ""),
        "source_created_at": item.get("source_created_at", ""),
        "source_updated_at": item.get("source_updated_at", ""),
        "author": item.get("author", ""),
        "channel_or_workspace": item.get("channel_or_workspace") or item.get("location", ""),
        "mentioned_user": item.get("mentioned_user", ""),
    }
    if "raw_payload" in item:
        raw_payload = item["raw_payload"]
        if isinstance(raw_payload, str):
            data["raw_payload"] = raw_payload
        else:
            data["raw_payload"] = json.dumps(raw_payload, ensure_ascii=False)
    return data


def _to_item_payload(item):
    title = item.get("title") or item.get("content", "")[:80] or f"{item['service']} {item['stream']} {item['source_id']}"
    return {
        "type": "collected_message",
        "title": title,
        "content": item.get("content", ""),
        "data": _item_data(item),
        "status": item.get("status", "active"),
    }


def _update_state(conn, service, stream, seen_timestamp, now):
    row = conn.execute(
        """SELECT last_source_timestamp FROM collection_state
           WHERE service = ? AND stream = ?""",
        (service, stream),
    ).fetchone()
    last_source_timestamp = row["last_source_timestamp"] if row else None
    next_source_timestamp = _max_timestamp(last_source_timestamp, seen_timestamp)
    conn.execute(
        """INSERT INTO collection_state (
               service, stream, last_collected_at, last_source_timestamp,
               last_success_at, last_error, updated_at
           )
           VALUES (?, ?, ?, ?, ?, NULL, ?)
           ON CONFLICT(service, stream)
           DO UPDATE SET last_collected_at = excluded.last_collected_at,
                         last_source_timestamp = excluded.last_source_timestamp,
                         last_success_at = excluded.last_success_at,
                         last_error = NULL,
                         updated_at = excluded.updated_at""",
        (service, stream, now, next_source_timestamp, now, now),
    )
    return {
        "service": service,
        "stream": stream,
        "last_collected_at": now,
        "last_source_timestamp": next_source_timestamp,
    }


def cmd_collect(args):
    subcommand = args[0] if args else "plan"
    if subcommand == "plan":
        service = args[1] if len(args) > 1 else "all"
        cmd_collect_plan(service)
        return
    if subcommand == "save":
        if len(args) < 2:
            raise ValueError("collect save requires a JSON payload")
        cmd_collect_save(args[1])
        return
    raise ValueError(f"Unknown collect subcommand: {subcommand}")


def cmd_collect_plan(service="all"):
    services = _validate_service(service)
    conn = get_connection()
    ensure_schema(conn)
    seed_defaults(conn)

    plans = []
    for svc in services:
        for stream in STREAMS:
            row = conn.execute(
                """SELECT last_collected_at, last_source_timestamp, last_source_cursor, last_error
                   FROM collection_state WHERE service = ? AND stream = ?""",
                (svc, stream),
            ).fetchone()
            since = None
            cursor = None
            last_error = None
            if row:
                since = _max_timestamp(row["last_source_timestamp"], row["last_collected_at"])
                cursor = row["last_source_cursor"]
                last_error = row["last_error"]
            plans.append({
                "service": svc,
                "stream": stream,
                "collection_key": f"{svc}:{stream}",
                "since": since,
                "limit": DEFAULT_LIMIT,
                "cursor": cursor,
                "last_error": last_error,
            })

    conn.close()
    print(json.dumps({"status": "ok", "plans": plans}, ensure_ascii=False, indent=2))


def cmd_collect_save(data_json):
    payload = _load_payload(data_json)
    items = payload["items"]
    for item in items:
        _validate_item(item)

    conn = get_connection()
    ensure_schema(conn)
    seed_defaults(conn)

    saved = 0
    skipped = 0
    saved_ids = []
    seen_timestamps = {}
    now = _utc_now()

    try:
        for item in items:
            service = item["service"]
            stream = item["stream"]
            source_id = item["source_id"]
            source_timestamp = _source_timestamp(item)
            key = (service, stream)
            seen_timestamps[key] = _max_timestamp(seen_timestamps.get(key), source_timestamp)

            existing = conn.execute(
                """SELECT item_id FROM collected_items
                   WHERE service = ? AND stream = ? AND source_id = ?""",
                (service, stream, source_id),
            ).fetchone()
            if existing:
                skipped += 1
                continue

            item_id = _insert_item(conn, _to_item_payload(item))
            conn.execute(
                """INSERT INTO collected_items (
                       service, stream, source_id, item_id, source_url, source_timestamp
                   )
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (service, stream, source_id, item_id, item.get("source_url", ""), source_timestamp),
            )
            saved += 1
            saved_ids.append(item_id)

        state_updated = []
        for (service, stream), seen_timestamp in sorted(seen_timestamps.items()):
            state_updated.append(_update_state(conn, service, stream, seen_timestamp, now))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(json.dumps({
        "status": "ok",
        "saved": saved,
        "skipped": skipped,
        "ids": saved_ids,
        "state_updated": state_updated,
    }, ensure_ascii=False, indent=2))
