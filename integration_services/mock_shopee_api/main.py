import asyncio
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI(title="Mock Shopee API")
orders_path = Path(__file__).parent / "data" / "orders.json"
status: dict[str, Any] = {"webhook_enabled": True, "sent_events": 0, "last_ack": None, "last_error": None}

# In-memory inventory store for mock platform
_inventory_store: dict[str, float] = {}

class InventoryUpdate(BaseModel):
    qty: float


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_orders() -> list[dict[str, Any]]:
    return json.loads(orders_path.read_text(encoding="utf-8"))


def sign_payload(timestamp: str, body: bytes) -> str:
    secret = os.getenv("WEBHOOK_SECRET_SHOPEE", os.getenv("WEBHOOK_SECRET", "dev-webhook-secret"))
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def send_order_webhooks() -> None:
    middleware_url = os.getenv("MIDDLEWARE_WEBHOOK_URL", "http://middleware:8020/webhook/shopee")
    interval = float(os.getenv("EVENT_INTERVAL_SECONDS", "2"))
    replay_interval = float(os.getenv("REPLAY_INTERVAL_SECONDS", "0"))
    while True:
        try:
            async with httpx.AsyncClient() as client:
                status.update({"last_error": None})
                while True:
                    for index, order in enumerate(load_orders(), start=1):
                        event = {
                            "event_id": f"shopee-{order['order_sn']}",
                            "platform": "shopee",
                            "event_type": "order.created",
                            "sent_at": utc_now(),
                            "payload": order,
                        }
                        body = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                        timestamp = utc_now()
                        headers = {
                            "Content-Type": "application/json",
                            "X-MC-Timestamp": timestamp,
                            "X-MC-Signature": sign_payload(timestamp, body),
                        }
                        resp = await client.post(middleware_url, content=body, headers=headers, timeout=10.0)
                        resp.raise_for_status()
                        ack = resp.text
                        status.update({"sent_events": status["sent_events"] + 1, "last_ack": ack})
                        print(f"[Shopee] sent event #{index}: {order['order_sn']} -> {ack}")
                        await asyncio.sleep(interval)
                    if replay_interval <= 0:
                        await asyncio.sleep(3600)
                    else:
                        await asyncio.sleep(replay_interval)
        except Exception as exc:
            status.update({"last_error": str(exc)})
            print(f"[Shopee] webhook dispatch failed: {exc}")
            await asyncio.sleep(3)


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(send_order_webhooks())


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "mock-shopee-api", **status}


@app.get("/orders")
def orders() -> list[dict[str, Any]]:
    return load_orders()

@app.put("/api/v1/products/{sku}/inventory")
def update_inventory(sku: str, update: InventoryUpdate) -> dict[str, Any]:
    _inventory_store[sku] = update.qty
    print(f"[Shopee] Mock API: Received stock update SKU={sku} -> Qty={update.qty}")
    return {"status": "success", "sku": sku, "updated_qty": update.qty}

@app.get("/api/v1/products/{sku}/inventory")
def get_inventory(sku: str) -> dict[str, Any]:
    qty = _inventory_store.get(sku, 0.0)
    return {"status": "ok", "sku": sku, "current_qty": qty}
