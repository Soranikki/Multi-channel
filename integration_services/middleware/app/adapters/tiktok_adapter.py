import os
from typing import Any
import httpx


def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    buyer = payload.get("buyer") or {}
    payment = payload.get("payment") or {}
    items = []
    for item in payload.get("line_items", []):
        items.append({
            "external_sku": str(item.get("seller_sku") or "").strip(),
            "product_name": str(item.get("title") or "").strip(),
            "quantity": float(item.get("qty") or 0),
            "unit_price": float(item.get("sale_price") or 0),
        })
    return {
        "source_platform": "tiktok",
        "channel_code": "tiktok",
        "external_order_id": str(payload.get("id") or "").strip(),
        "platform_order_status": str(payload.get("order_status") or payload.get("fulfillment_status") or "").strip(),
        "platform_payment_status": str(payload.get("payment_status") or payment.get("status") or "").strip(),
        "platform_status_updated_at": payload.get("status_updated_at") or payload.get("updated_at"),
        "customer_name": str(buyer.get("name") or "").strip(),
        "customer_phone": str(buyer.get("phone") or "").strip(),
        "customer_email": str(buyer.get("email") or "").strip(),
        "shipping_address": str(payload.get("shipping_address") or "").strip(),
        "order_date": payload.get("created_at"),
        "total_amount": float(payment.get("total") or 0),
        "currency": str(payment.get("currency") or "VND").strip(),
        "items": items,
    }


async def push_inventory(sku: str, qty: float) -> None:
    api_url = os.getenv("MOCK_TIKTOK_API_URL", "http://mock-tiktok-api:8012")
    endpoint = f"{api_url}/api/v1/products/{sku}/inventory"
    async with httpx.AsyncClient() as client:
        resp = await client.put(endpoint, json={"qty": qty}, timeout=10.0)
        resp.raise_for_status()

