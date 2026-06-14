from typing import Any

from app.channel_config import config_store
from app.resolver import resolve_all


def normalize_event(platform: str, event: dict[str, Any]) -> dict[str, Any]:
    config = config_store.get(platform)
    if not config:
        raise ValueError(
            f"Unknown platform: '{platform}'. "
            f"Create a channel config first at POST /api/channel-configs "
            f"(see /docs for Swagger UI)."
        )
    payload = event.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("Event payload must be a JSON object")
    normalized = resolve_all(
        payload,
        config.field_mappings,
        config.items_root,
        config.item_mappings,
    )
    normalized["channel_code"] = platform
    if not normalized.get("external_order_id"):
        raise ValueError("Normalized order is missing external_order_id")
    if not normalized.get("items"):
        raise ValueError("Normalized order is missing items")
    return normalized
