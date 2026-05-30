from typing import Any


def resolve_path(obj: dict[str, Any], path: str) -> Any:
    if not path:
        return ""
    keys = path.split(".")
    current: Any = obj
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return ""
        current = current[key]
    return current


def resolve_item(item: dict[str, Any], item_mappings: dict[str, str]) -> dict[str, Any]:
    return {
        "external_sku": str(resolve_path(item, item_mappings.get("external_sku", "")) or "").strip(),
        "product_name": str(resolve_path(item, item_mappings.get("product_name", "")) or "").strip(),
        "quantity": float(resolve_path(item, item_mappings.get("quantity", "")) or 0),
        "unit_price": float(resolve_path(item, item_mappings.get("unit_price", "")) or 0),
    }


def resolve_all(payload: dict[str, Any], field_mappings: dict[str, str], items_root: str, item_mappings: dict[str, str]) -> dict[str, Any]:
    items_raw = resolve_path(payload, items_root)
    if not isinstance(items_raw, list):
        items_raw = []
    return {
        "external_order_id": str(resolve_path(payload, field_mappings.get("external_order_id", "")) or "").strip(),
        "platform_order_status": str(resolve_path(payload, field_mappings.get("platform_order_status", "")) or "").strip(),
        "platform_payment_status": str(resolve_path(payload, field_mappings.get("platform_payment_status", "")) or "").strip(),
        "platform_status_updated_at": resolve_path(payload, field_mappings.get("platform_status_updated_at", "")),
        "customer_name": str(resolve_path(payload, field_mappings.get("customer_name", "")) or "").strip(),
        "customer_phone": str(resolve_path(payload, field_mappings.get("customer_phone", "")) or "").strip(),
        "customer_email": str(resolve_path(payload, field_mappings.get("customer_email", "")) or "").strip(),
        "shipping_address": str(resolve_path(payload, field_mappings.get("shipping_address", "")) or "").strip(),
        "order_date": resolve_path(payload, field_mappings.get("order_date", "")),
        "total_amount": float(resolve_path(payload, field_mappings.get("total_amount", "")) or 0),
        "currency": str(resolve_path(payload, field_mappings.get("currency", "")) or "VND").strip(),
        "items": [resolve_item(item, item_mappings) for item in items_raw],
    }
