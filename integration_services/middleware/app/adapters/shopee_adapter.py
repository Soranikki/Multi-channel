from typing import Any


def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    address = payload.get("recipient_address") or {}
    items = []
    for item in payload.get("items", []):
        items.append({
            "external_sku": str(item.get("item_sku") or "").strip(),
            "product_name": str(item.get("item_name") or "").strip(),
            "quantity": float(item.get("quantity_purchased") or 0),
            "unit_price": float(item.get("item_price") or 0),
        })
    return {
        "source_platform": "shopee",
        "channel_code": "shopee",
        "external_order_id": str(payload.get("order_sn") or "").strip(),
        "customer_name": str(address.get("name") or payload.get("buyer_username") or "").strip(),
        "customer_phone": str(address.get("phone") or "").strip(),
        "customer_email": str(payload.get("buyer_email") or "").strip(),
        "shipping_address": str(address.get("full_address") or "").strip(),
        "order_date": payload.get("create_time"),
        "total_amount": float(payload.get("total_amount") or 0),
        "currency": str(payload.get("currency") or "VND").strip(),
        "items": items,
    }
