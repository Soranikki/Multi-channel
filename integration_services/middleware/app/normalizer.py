from typing import Any

from app.adapters import shopee_adapter, tiktok_adapter


ADAPTERS = {
    "shopee": shopee_adapter.normalize,
    "tiktok": tiktok_adapter.normalize,
}


def normalize_event(platform: str, event: dict[str, Any]) -> dict[str, Any]:
    adapter = ADAPTERS.get(platform)
    if not adapter:
        raise ValueError(f"Unsupported platform: {platform}")
    payload = event.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("Event payload must be a JSON object")
    normalized = adapter(payload)
    if not normalized.get("external_order_id"):
        raise ValueError("Normalized order is missing external_order_id")
    if not normalized.get("items"):
        raise ValueError("Normalized order is missing items")
    return normalized
