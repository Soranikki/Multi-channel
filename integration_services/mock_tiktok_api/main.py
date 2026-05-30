import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import websockets
from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI(title="Mock TikTok Shop API")
orders_path = Path(__file__).parent / "data" / "orders.json"
status: dict[str, Any] = {"connected": False, "sent_events": 0, "last_ack": None, "last_error": None}

# In-memory inventory store for mock platform
_inventory_store: dict[str, float] = {}

class InventoryUpdate(BaseModel):
    qty: float


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_orders() -> list[dict[str, Any]]:
    return json.loads(orders_path.read_text(encoding="utf-8"))


async def stream_orders() -> None:
    middleware_url = os.getenv("MIDDLEWARE_WS_URL", "ws://middleware:8020/ws/platform/tiktok")
    interval = float(os.getenv("EVENT_INTERVAL_SECONDS", "2"))
    replay_interval = float(os.getenv("REPLAY_INTERVAL_SECONDS", "0"))
    while True:
        try:
            async with websockets.connect(middleware_url) as websocket:
                status.update({"connected": True, "last_error": None})
                await websocket.recv()  # connected message
                while True:
                    for index, order in enumerate(load_orders(), start=1):
                        event = {
                            "event_id": f"tiktok-{order['id']}",
                            "platform": "tiktok",
                            "event_type": "order.created",
                            "sent_at": utc_now(),
                            "payload": order,
                        }
                        await websocket.send(json.dumps(event, ensure_ascii=False))
                        ack = await websocket.recv()
                        status.update({"sent_events": status["sent_events"] + 1, "last_ack": ack})
                        print(f"[TikTok] sent event #{index}: {order['id']} -> {ack}")
                        await asyncio.sleep(interval)
                    if replay_interval <= 0:
                        await asyncio.sleep(3600)
                    else:
                        await asyncio.sleep(replay_interval)
        except Exception as exc:
            status.update({"connected": False, "last_error": str(exc)})
            print(f"[TikTok] websocket disconnected: {exc}")
            await asyncio.sleep(3)


@app.on_event("startup")
async def startup() -> None:
    asyncio.create_task(stream_orders())


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "mock-tiktok-api", **status}


@app.get("/orders")
def orders() -> list[dict[str, Any]]:
    return load_orders()

@app.put("/api/v1/products/{sku}/inventory")
def update_inventory(sku: str, update: InventoryUpdate) -> dict[str, Any]:
    _inventory_store[sku] = update.qty
    print(f"[TikTok] Mock API: Received stock update SKU={sku} -> Qty={update.qty}")
    return {"status": "success", "sku": sku, "updated_qty": update.qty}

@app.get("/api/v1/products/{sku}/inventory")
def get_inventory(sku: str) -> dict[str, Any]:
    qty = _inventory_store.get(sku, 0.0)
    return {"status": "ok", "sku": sku, "current_qty": qty}
